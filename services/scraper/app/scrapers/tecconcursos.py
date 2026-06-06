"""Orquestração do scrape TecConcursos.

Endpoint canônico (descoberto via DevTools-ao-vivo em 2026-05-27):

    GET /api/cadernos/{caderno_id}/questoes/{posicao}

`posicao` é 1-indexed e vai até `total` (descoberto via binary search,
porque a API não devolve total no payload). A partir de `total+1`,
o servidor satura na última questão (continua devolvendo o mesmo
idQuestao). Detectamos saturação observando idQuestao constante.

Cada response inclui a questão completa + gabarito (numeroAlternativaCorreta).
Zero IA pra extração.
"""

from __future__ import annotations

import asyncio

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.auth import load_cookies_for_httpx
from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger
from app.persistir import upsert_questao
from app.schemas import QuestaoApi, RateLimited, SessionExpired
from app.state import ScrapeState

log = get_logger(__name__)


async def descobrir_total(client: TcClient, caderno_id: int) -> int:
    """Binary search no endpoint /questoes/{N} pra descobrir total real."""
    referer = f"{get_settings().tc_base}/questoes/cadernos/{caderno_id}"
    # Pega o idQuestao em N gigante (sentinela saturado)
    r = await client.get(
        f"/api/cadernos/{caderno_id}/questoes/100000", referer=referer
    )
    r.raise_for_status()
    sat_id = r.json()["questao"]["idQuestao"]
    log.info("total.sentinela", caderno=caderno_id, idQuestao=sat_id)

    # phase 1: encontra hi tal que idQuestao == sat
    lo, hi = 1, 2
    while True:
        r = await client.get(
            f"/api/cadernos/{caderno_id}/questoes/{hi}", referer=referer
        )
        qid = r.json()["questao"]["idQuestao"]
        if qid == sat_id and hi > 50:  # cuidado: idQuestao saturada pode coincidir com a real
            break
        lo = hi
        hi *= 2
        if hi > 200_000:
            raise RuntimeError("caderno improvavelmente grande, abortando")

    # phase 2: binary inside lo (distinto) ↔ hi (saturado)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        r = await client.get(
            f"/api/cadernos/{caderno_id}/questoes/{mid}", referer=referer
        )
        qid = r.json()["questao"]["idQuestao"]
        if qid == sat_id:
            hi = mid
        else:
            lo = mid

    # `hi` pode ser o último (legítimo) — verifica:
    # se idQuestao(hi-1) != sat E idQuestao(hi) == sat, total = hi
    # se idQuestao(hi) != sat, total = hi e hi+1 satura
    r = await client.get(
        f"/api/cadernos/{caderno_id}/questoes/{hi}", referer=referer
    )
    if r.json()["questao"]["idQuestao"] != sat_id:
        total = hi
    else:
        total = lo
    log.info("total.found", caderno=caderno_id, total=total)
    return total


@retry(
    retry=retry_if_exception_type(RateLimited),
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=30, max=300),
)
async def fetch_questao_por_posicao(
    client: TcClient, caderno_id: int, posicao: int
) -> tuple[QuestaoApi, dict]:
    referer = f"{get_settings().tc_base}/questoes/cadernos/{caderno_id}"
    r = await client.get(
        f"/api/cadernos/{caderno_id}/questoes/{posicao}", referer=referer
    )
    r.raise_for_status()
    raw = r.json()["questao"]
    return QuestaoApi.model_validate(raw), raw


async def scrape_caderno(
    caderno_id: int,
    *,
    limite: int | None = None,
    total: int | None = None,
    state: ScrapeState | None = None,
) -> dict[str, int]:
    """Pipeline completo: descobre total (ou usa o fornecido) → itera → persiste.

    Passe `total=N` se já souber o tamanho (evita binary search inicial,
    que custa ~20 reqs extras e pode disparar anti-bot).
    """
    state = state or ScrapeState()
    cookies = load_cookies_for_httpx()

    contadores = {"ok": 0, "erro": 0, "missing": 0, "pulados": 0}

    async with TcClient(cookies) as client:
        if total is None:
            total = await descobrir_total(client, caderno_id)
        else:
            log.info("total.given", caderno=caderno_id, total=total)
        if limite:
            total = min(total, limite)
        log.info("scrape.start", caderno=caderno_id, total=total)

        async def worker(posicao: int) -> None:
            if state.posicao_ja_coletada(caderno_id, posicao):
                contadores["pulados"] += 1
                return
            try:
                q, raw = await fetch_questao_por_posicao(client, caderno_id, posicao)
                await upsert_questao(q, raw=raw)
                state.marca(q.idQuestao, caderno_id, "ok")
                state.marca_posicao(caderno_id, posicao, q.idQuestao)
                contadores["ok"] += 1
            except SessionExpired:
                log.error("sessao_expirou — refazer login")
                raise
            except Exception as e:  # noqa: BLE001
                contadores["erro"] += 1
                log.error("posicao.fail", posicao=posicao, err=str(e))

        await asyncio.gather(
            *(worker(n) for n in range(1, total + 1)),
            return_exceptions=False,
        )

    log.info("scrape.done", **contadores)
    return contadores


async def scrape_ids(
    ids: list[int],
    *,
    caderno_id: int | None = None,
    state: ScrapeState | None = None,
) -> dict[str, int]:
    """Não suportado para o endpoint atual (que indexa por posição, não id).

    Mantido como stub para compatibilidade com o CLI/API existentes.
    """
    raise NotImplementedError(
        "API TC indexa por posição de caderno, não por ID. "
        "Use `scrape_caderno(caderno_id, limite=N)`."
    )
