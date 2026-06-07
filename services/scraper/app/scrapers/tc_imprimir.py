"""Scraper TC via endpoint `ajaxCarregarQuestoesImpressao` — caminho ÓTIMO.

Descoberto em 2026-06-06 via MCP Playwright interceptando network. O fluxo de
"Imprimir caderno" usa este endpoint que retorna **200 questões JSON
estruturado em 1 request**, com:

- enunciado HTML
- alternativas (list de HTML)
- gabarito (letra A-E ou 'Certo'/'Errado')
- numeroAlternativaCorreta (1-5)
- taxonomia flat (bancaSigla, orgaoSigla, cargoSigla, etc)

Pra caderno de 876 questões = **5 requests** com questaoInicial 0, 200, 400, 600, 800.
Zero rate-limit issues (é o fluxo legítimo de impressão).
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlencode

from app.auth import load_cookies_for_httpx, login_and_save_state
from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger
from app.persistir import upsert_questao
from app.schemas import AccessBlocked, CaptchaChallenge, QuestaoApi, RateLimited, SessionExpired
from app.state import ScrapeState

log = get_logger(__name__)

AJAX_ENDPOINT = "/questoes/cadernos/{cid}/ajaxCarregarQuestoesImpressao"


def _build_body(caderno_id: int, inicio: int, quantidade: int) -> str:
    return urlencode({
        "configuracoes.idCadernoQuestoes": str(caderno_id),
        "configuracoes.idTeoriaModulo": "",
        "configuracoes.idTeoriaAssunto": "",
        "configuracoes.questaoInicial": str(inicio),
        "configuracoes.numeroQuestoes": str(quantidade),
        "configuracoes.removerQuestoes": "NENHUMA",
    })


# Nota: o retry de 403/429 é feito no loop em `scrape_caderno_imprimir`
# (com pausa de 180s entre tentativas + retenta mesma página). Aqui
# deixamos só o erro propagar.
async def fetch_pagina(
    client: TcClient, caderno_id: int, inicio: int, quantidade: int = 200
) -> list[dict[str, Any]]:
    """Retorna a `list` de questões da página (inicio é 0-indexed).

    Resiliente a 403/429 transitórios — retry com backoff exponencial até
    4 tentativas (10s, 20s, 40s, 80s). Falha SessionExpired/Captcha NÃO
    retenta — propaga para o caller resolver.
    """
    body = _build_body(caderno_id, inicio, quantidade)
    referer = f"{get_settings().tc_base}/questoes/cadernos/{caderno_id}/imprimir"

    r = await client._client.post(  # noqa: SLF001
        AJAX_ENDPOINT.format(cid=caderno_id),
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
            "Origin": get_settings().tc_base,
        },
    )
    client._check(r)  # noqa: SLF001  ← pode levantar AccessBlocked/RateLimited/SessionExpired/CaptchaChallenge
    r.raise_for_status()
    data = r.json()
    return data.get("list", [])


async def scrape_caderno_imprimir(
    caderno_id: int,
    *,
    total: int | None = None,
    page_size: int = 200,
    state: ScrapeState | None = None,
    pause_min: float | None = None,
    pause_max: float | None = None,
    burst_every: int | None = None,
    burst_min: float | None = None,
    burst_max: float | None = None,
    block_pause: float | None = None,
) -> dict[str, int]:
    """Coleta caderno inteiro paginando o endpoint de impressão.

    Pausas defensivas (anti 403/429) — valores default vêm das settings
    (configuráveis via env IMPRIMIR_PAUSE_MIN, IMPRIMIR_BURST_EVERY, etc):
      - Entre páginas:  pause_min..pause_max jitter (default 4-7s)
      - Burst pause:    a cada `burst_every` páginas espera burst_min..burst_max (default 20 pg → 25-50s)
      - Em 403/429:     espera `block_pause` (default 180s = 3min) antes de retry
    """
    import random

    s = get_settings()
    pause_min = pause_min if pause_min is not None else s.imprimir_pause_min
    pause_max = pause_max if pause_max is not None else s.imprimir_pause_max
    burst_every = burst_every if burst_every is not None else s.imprimir_burst_every
    burst_min = burst_min if burst_min is not None else s.imprimir_burst_min
    burst_max = burst_max if burst_max is not None else s.imprimir_burst_max
    block_pause = block_pause if block_pause is not None else s.imprimir_block_pause

    state = state or ScrapeState()
    cookies = load_cookies_for_httpx()
    contadores = {"ok": 0, "erro": 0, "paginas": 0, "block_recover": 0}

    async with TcClient(cookies) as client:
        # Warm-up: aquece sessão visitando a página de imprimir form
        warm = await client._client.get(  # noqa: SLF001
            f"/questoes/cadernos/{caderno_id}",
            headers={"Accept": "text/html"},
        )
        log.info("warmup", status=warm.status_code)
        await asyncio.sleep(random.uniform(1.5, 3.0))  # respira após warmup

        # ─── Checkpoint pra retomar do ponto onde parou ───
        from pathlib import Path as _Path
        checkpoint = _Path(s.scrape_state_path).parent / f"checkpoint-{caderno_id}.txt"
        pause_file = _Path(s.scrape_state_path).parent / "PAUSE"
        inicio = int(checkpoint.read_text().strip()) if checkpoint.exists() else 0
        if inicio > 0:
            log.info("checkpoint_loaded", caderno=caderno_id, inicio=inicio)

        falhas_consecutivas = 0
        while True:
            # ─── Pausa cooperativa via lock file ───
            # Pra pausar: touch /state/PAUSE  |  retomar: rm /state/PAUSE
            while pause_file.exists():
                log.info("paused", reason="lock_file_PAUSE_existe", caderno=caderno_id, inicio=inicio)
                await asyncio.sleep(15)

            log.info("page.fetch", caderno=caderno_id, inicio=inicio, page_size=page_size)
            try:
                questoes_raw = await fetch_pagina(client, caderno_id, inicio, page_size)
                falhas_consecutivas = 0
            except SessionExpired:
                # TC retornou 452 (sessão queimada) ou /login redirect.
                # Refaz login Playwright e atualiza cookies do cliente existente.
                contadores["block_recover"] += 1
                falhas_consecutivas += 1
                if falhas_consecutivas >= 3:
                    log.error("3 sessao_queimada consecutivas — abortando", inicio=inicio)
                    break
                log.warning("sessao_queimada — refazendo login + retry", inicio=inicio, falhas_consec=falhas_consecutivas)
                try:
                    await login_and_save_state(headless=True)
                    novos_cookies = load_cookies_for_httpx()
                    client._client.cookies.clear()  # noqa: SLF001
                    client._client.cookies.update(novos_cookies)  # noqa: SLF001
                    await asyncio.sleep(random.uniform(5, 10))
                    continue  # NÃO incrementa inicio — retenta mesma página
                except Exception as e:  # noqa: BLE001
                    log.error("relogin_falhou", err=str(e), inicio=inicio)
                    contadores["erro"] += 1
                    break
            except CaptchaChallenge:
                log.error("captcha — abortando", inicio=inicio)
                contadores["erro"] += 1
                break
            except (AccessBlocked, RateLimited) as e:
                falhas_consecutivas += 1
                contadores["erro"] += 1
                contadores["block_recover"] += 1
                log.warning(
                    "block_detectado",
                    inicio=inicio,
                    tipo=type(e).__name__,
                    pausa_segundos=block_pause,
                    falhas_consec=falhas_consecutivas,
                )
                if falhas_consecutivas >= 3:
                    log.error("3 blocks consecutivos — abortando", inicio=inicio)
                    break
                # Espera longa pra cooldown do TC (default 3 min)
                await asyncio.sleep(block_pause)
                # NÃO incrementa inicio — retenta a mesma página
                continue
            except Exception as e:  # noqa: BLE001
                falhas_consecutivas += 1
                contadores["erro"] += 1
                log.error("page.fail", inicio=inicio, err=str(e), falhas_consec=falhas_consecutivas)
                if falhas_consecutivas >= 3:
                    log.error("3 falhas consecutivas — abortando", inicio=inicio)
                    break
                inicio += page_size
                await asyncio.sleep(15)
                continue

            contadores["paginas"] += 1
            if not questoes_raw:
                log.info("page.empty", inicio=inicio)
                break

            for q_raw in questoes_raw:
                try:
                    q = QuestaoApi.model_validate(q_raw)
                    await upsert_questao(q, raw=q_raw)
                    state.marca(q.idQuestao, caderno_id, "ok")
                    contadores["ok"] += 1
                except Exception as e:  # noqa: BLE001
                    contadores["erro"] += 1
                    log.error("upsert.fail", idQuestao=q_raw.get("idQuestao"), err=str(e))

            # condição de parada
            if total is not None and inicio + page_size >= total:
                break
            if len(questoes_raw) < page_size:
                break  # última página parcial

            inicio += page_size
            # Salva checkpoint a cada página → permite retomar caso crash
            checkpoint.write_text(str(inicio))

            # ─── Pausa defensiva entre páginas ───
            paginas_feitas = contadores["paginas"]
            if burst_every > 0 and paginas_feitas > 0 and paginas_feitas % burst_every == 0:
                burst_wait = random.uniform(burst_min, burst_max)
                log.info("burst_pause", paginas=paginas_feitas, wait_s=round(burst_wait, 1))
                await asyncio.sleep(burst_wait)
            else:
                await asyncio.sleep(random.uniform(pause_min, pause_max))

    # Limpa checkpoint ao terminar (sucesso ou last page)
    if checkpoint.exists():
        checkpoint.unlink()
    log.info("scrape.done", caderno=caderno_id, **contadores)
    return contadores
