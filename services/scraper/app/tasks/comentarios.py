"""Worker da coleta em massa de comentários: 1 unit = 1 questão (2 quadros).
Reusa o endpoint da Fase 1 no backend (não reimplementa upsert/re-host).

Hooks substituíveis (_lease/_mark_done/_enqueue_next) + parâmetros sleep/post
permitem testes sem DB/broker (monkeypatch nos atributos do módulo).
"""
from __future__ import annotations

import asyncio
import inspect
import random
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.observability import get_logger
from app.tasks.brokers.studia import broker_studia_default
from app.tasks.enqueue import enqueue
from app.tasks.ledger import (
    ensure_ledger_schema,
    is_comentario_paused,
    lease_comentario_unit,
    list_enqueueable_comentario_units,
    mark_comentario_unit_done,
    mark_comentario_unit_failed,
    release_comentario_unit_to_pending,
)

log = get_logger(__name__)
QUADROS = ("alunos", "professores")


# ─── helpers de I/O (substituíveis em testes via monkeypatch) ─────────────────

async def _post_import(questao_id: int, quadro: str, *, _sleep: Any = asyncio.sleep) -> dict[str, Any]:
    s = get_settings()
    url = (
        f"{s.backend_url}/api/q/questoes/{questao_id}"
        f"/importar-comentarios-tc?quadro={quadro}&task=forum_mass"
    )
    headers = {"X-Internal-Token": s.studia_internal_token}
    ultimo: Exception | None = None
    for tentativa in range(3):  # 1 + 2 retries
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=180, write=10, pool=185)
        ) as c:
            r = await c.post(url, headers=headers)
            if r.status_code < 500:
                r.raise_for_status()  # 4xx → falha imediata
                return r.json()
            ultimo = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
        if tentativa < 2:
            r = _sleep(3.0)
            if inspect.isawaitable(r):
                await r
    raise ultimo  # 5xx persistente após retries


def _engine_session():
    eng = create_async_engine(get_settings().database_url)
    return eng, async_sessionmaker(eng, expire_on_commit=False)


# ─── hooks do ledger (substituíveis em testes) ────────────────────────────────

async def _lease(*, caderno_id: int, questao_id: int) -> dict | None:
    eng, S = _engine_session()
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
        async with S.begin() as s:
            return await lease_comentario_unit(
                s, caderno_id=caderno_id, questao_id=questao_id, ack_wait_seconds=600
            )
    finally:
        await eng.dispose()


async def _mark_done(
    *, unit_id: int, job_id: int, coments_alunos: int, coments_professores: int
) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await mark_comentario_unit_done(
                s,
                unit_id=unit_id,
                job_id=job_id,
                coments_alunos=coments_alunos,
                coments_professores=coments_professores,
            )
    finally:
        await eng.dispose()


async def _mark_failed(*, unit_id: int, job_id: int, error: str) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await mark_comentario_unit_failed(
                s, unit_id=unit_id, job_id=job_id, error=error
            )
    finally:
        await eng.dispose()


async def _is_paused(*, caderno_id: int) -> bool:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            return await is_comentario_paused(s, caderno_id=caderno_id)
    finally:
        await eng.dispose()


async def _release(*, unit_id: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await release_comentario_unit_to_pending(s, unit_id=unit_id)
    finally:
        await eng.dispose()


async def _enqueue_next(*, caderno_id: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            units = await list_enqueueable_comentario_units(
                s, caderno_id=caderno_id, limit=1
            )
        for u in units:
            # isolated_broker: enfileirar de DENTRO da task do worker exige um broker
            # próprio (a conexão de consumo não publica → ConnectionClosedError mata o
            # worker e a cadeia só anda por redelivery ~ack_wait). Espelha o worker de
            # caderno (caderno.py _enqueue_next_caderno_unit).
            await enqueue(
                coletar_comentarios_questao,
                priority="default",
                isolated_broker=True,
                questao_id=u["questao_id"],
                caderno_id=caderno_id,
            )
    finally:
        await eng.dispose()


# ─── núcleo testável ──────────────────────────────────────────────────────────

async def _call(fn: Any, **kw: Any) -> Any:
    """Chama fn(**kw) e awaita se for coroutine (suporta hooks sync em testes)."""
    r = fn(**kw)
    return (await r) if inspect.isawaitable(r) else r


async def _processar_unit_comentarios(
    questao_id: int,
    caderno_id: int,
    *,
    sleep: Any = asyncio.sleep,
    post: Any = None,
) -> dict[str, Any]:
    """Processa 1 unit (questão): faz POST ao backend para cada quadro,
    dorme 5-15s apenas quando bate de verdade no TC (ja_importado=false)."""
    if post is None:
        post = _post_import

    # Usa lookup no módulo para que monkeypatch funcione nos hooks
    import app.tasks.comentarios as _self  # noqa: PLC0415

    leased = await _call(_self._lease, caderno_id=caderno_id, questao_id=questao_id)
    if leased is None:
        return {"status": "skipped"}

    if await _call(_self._is_paused, caderno_id=caderno_id):
        await _call(_self._release, unit_id=leased["unit_id"])
        return {"status": "paused"}  # solta a unit e NÃO encadeia

    s = get_settings()
    counts: dict[str, int] = {"alunos": 0, "professores": 0}
    try:
        for quadro in QUADROS:
            res = await post(questao_id, quadro)
            counts[quadro] = int(res.get("importados") or 0)
            if not res.get("ja_importado"):  # bateu no TC → humaniza
                await sleep(
                    random.uniform(s.comentario_pause_min, s.comentario_pause_max)
                )
    except Exception as exc:  # noqa: BLE001 — registra e segue o chain
        await _call(
            _self._mark_failed,
            unit_id=leased["unit_id"],
            job_id=leased["job_id"],
            error=str(exc)[:300],
        )
        await _call(_self._enqueue_next, caderno_id=caderno_id)
        log.warning("comentarios.unit.failed", questao_id=questao_id, erro=str(exc)[:120])
        return {"status": "failed"}

    await _call(
        _self._mark_done,
        unit_id=leased["unit_id"],
        job_id=leased["job_id"],
        coments_alunos=counts["alunos"],
        coments_professores=counts["professores"],
    )
    await _call(_self._enqueue_next, caderno_id=caderno_id)
    return {
        "status": "done",
        "coments_alunos": counts["alunos"],
        "coments_professores": counts["professores"],
    }


# ─── task Taskiq ─────────────────────────────────────────────────────────────

@broker_studia_default.task
async def coletar_comentarios_questao(
    questao_id: int, caderno_id: int
) -> dict[str, Any]:
    return await _processar_unit_comentarios(questao_id, caderno_id)
