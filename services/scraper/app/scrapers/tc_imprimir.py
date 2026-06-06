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

from app.auth import load_cookies_for_httpx
from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger
from app.persistir import upsert_questao
from app.schemas import QuestaoApi
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


async def fetch_pagina(
    client: TcClient, caderno_id: int, inicio: int, quantidade: int = 200
) -> list[dict[str, Any]]:
    """Retorna a `list` de questões da página (inicio é 0-indexed)."""
    body = _build_body(caderno_id, inicio, quantidade)
    referer = f"{get_settings().tc_base}/questoes/cadernos/{caderno_id}/imprimir"

    # bypass do throttle humano: warm-up apenas, depois paginação em série rápida
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
    client._check(r)  # noqa: SLF001
    r.raise_for_status()
    data = r.json()
    return data.get("list", [])


async def scrape_caderno_imprimir(
    caderno_id: int,
    *,
    total: int | None = None,
    page_size: int = 200,
    state: ScrapeState | None = None,
) -> dict[str, int]:
    """Coleta caderno inteiro paginando o endpoint de impressão.

    Se `total` é None, descobre pulando até receber página vazia.
    Persiste cada questão via `upsert_questao` (idempotente).
    """
    state = state or ScrapeState()
    cookies = load_cookies_for_httpx()
    contadores = {"ok": 0, "erro": 0, "paginas": 0}

    async with TcClient(cookies) as client:
        # Warm-up: aquece sessão visitando a página de imprimir form
        warm = await client._client.get(  # noqa: SLF001
            f"/questoes/cadernos/{caderno_id}",
            headers={"Accept": "text/html"},
        )
        log.info("warmup", status=warm.status_code)

        inicio = 0
        while True:
            log.info("page.fetch", caderno=caderno_id, inicio=inicio, page_size=page_size)
            try:
                questoes_raw = await fetch_pagina(client, caderno_id, inicio, page_size)
            except Exception as e:  # noqa: BLE001
                log.error("page.fail", inicio=inicio, err=str(e))
                contadores["erro"] += 1
                break

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
            # delay curto entre páginas (não precisa modo humano — é fluxo legítimo)
            await asyncio.sleep(2.5)

    log.info("scrape.done", caderno=caderno_id, **contadores)
    return contadores
