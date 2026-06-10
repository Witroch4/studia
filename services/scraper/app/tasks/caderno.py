from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import load_cookies_for_httpx
from app.auth import login_and_save_state
from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger
from app.persistir import upsert_questao
from app.schemas import (
    AccessBlocked,
    CaptchaChallenge,
    QuestaoApi,
    RateLimited,
    SessionExpired,
)
from app.scrapers.tc_imprimir import fetch_pagina
from app.tasks.brokers.studia import broker_studia_default
from app.tasks.enqueue import enqueue
from app.tasks.ledger import (
    ensure_ledger_schema,
    lease_caderno_unit,
    list_enqueueable_caderno_units,
    mark_caderno_unit_blocked,
    mark_caderno_unit_done,
    mark_caderno_unit_failed,
    record_caderno_membership,
)

log = get_logger(__name__)

PageFetcher = Callable[[int, int, int], Awaitable[list[dict[str, Any]]]]
QuestaoUpserter = Callable[[QuestaoApi, dict[str, Any]], Awaitable[int]]


class EmptyCadernoPage(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CadernoUnitResult:
    status: str
    caderno_id: int
    inicio: int
    page_size: int
    questoes_ok: int = 0
    attempts: int = 0
    reason: str | None = None
    error: str | None = None
    enqueued_next_inicio: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def execute_caderno_page_unit(
    *,
    caderno_id: int,
    inicio: int,
    page_size: int,
    task_id: str | None = None,
    fetcher: PageFetcher | None = None,
    upserter: QuestaoUpserter | None = None,
    pause_after: bool = True,
    chain_next: bool = True,
    relogin: bool = False,
) -> CadernoUnitResult:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    fetch = fetcher or _fetch_page_from_tc
    persist = upserter or _upsert_questao_default

    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            unit = await lease_caderno_unit(
                session,
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                task_id=task_id,
                lease_seconds=settings.taskiq_studia_ack_wait_seconds,
            )

        if unit is None:
            log.info(
                "tc_unit.skip",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                reason="not_enqueueable_or_done",
            )
            return CadernoUnitResult(
                status="skipped",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
            )

        try:
            if relogin:
                await _ensure_fresh_session()

            questoes_raw = await fetch(caderno_id, inicio, page_size)
            if not questoes_raw:
                raise EmptyCadernoPage(
                    f"empty page for caderno={caderno_id} inicio={inicio}"
                )

            questoes_ok = 0
            persisted_pks: list[int] = []
            members: list[tuple[int, int]] = []  # (questao_pk, posicao_1based)
            for idx, q_raw in enumerate(questoes_raw):
                q = QuestaoApi.model_validate(q_raw)
                pk = await persist(q, q_raw)
                if isinstance(pk, int):
                    persisted_pks.append(pk)
                    members.append((pk, inicio + idx + 1))
                questoes_ok += 1

            async with Session.begin() as session:
                await mark_caderno_unit_done(
                    session,
                    unit_id=int(unit["id"]),
                    job_id=int(unit["job_id"]),
                    questoes_ok=questoes_ok,
                )
                await record_caderno_membership(
                    session,
                    caderno_id=caderno_id,
                    members=members,
                )

            # Auto-reindex: empurra a página recém-persistida pro Meili na hora,
            # pra busca/facetas ficarem em dia sem reindex manual. Best-effort —
            # falha aqui não derruba a página (Postgres é a fonte de verdade).
            await _index_meili_best_effort(Session, persisted_pks)

            enqueued_next_inicio = None
            if chain_next:
                try:
                    enqueued_next_inicio = await _enqueue_next_caderno_unit(
                        Session,
                        caderno_id=caderno_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error(
                        "tc_unit.chain_enqueue_failed",
                        caderno_id=caderno_id,
                        inicio=inicio,
                        page_size=page_size,
                        err=str(exc),
                    )

            if pause_after:
                await _pause_after_unit()

            log.info(
                "tc_unit.done",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                questoes_ok=questoes_ok,
                attempts=unit["attempts"],
            )
            return CadernoUnitResult(
                status="done",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                questoes_ok=questoes_ok,
                attempts=int(unit["attempts"]),
                enqueued_next_inicio=enqueued_next_inicio,
            )
        except (SessionExpired, CaptchaChallenge, AccessBlocked, RateLimited) as exc:
            reason, cooldown_seconds = _block_policy(exc)
            async with Session.begin() as session:
                await mark_caderno_unit_blocked(
                    session,
                    unit_id=int(unit["id"]),
                    job_id=int(unit["job_id"]),
                    reason=reason,
                    error=str(exc),
                    cooldown_seconds=cooldown_seconds,
                )
            log.warning(
                "tc_unit.blocked",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                reason=reason,
                cooldown_seconds=cooldown_seconds,
                err=str(exc),
            )
            return CadernoUnitResult(
                status="blocked",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                attempts=int(unit["attempts"]),
                reason=reason,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            async with Session.begin() as session:
                await mark_caderno_unit_failed(
                    session,
                    unit_id=int(unit["id"]),
                    job_id=int(unit["job_id"]),
                    error=str(exc),
                )
            log.error(
                "tc_unit.failed",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                err=str(exc),
            )
            return CadernoUnitResult(
                status="failed",
                caderno_id=caderno_id,
                inicio=inicio,
                page_size=page_size,
                attempts=int(unit["attempts"]),
                error=str(exc),
            )
    finally:
        await engine.dispose()


@broker_studia_default.task
async def coletar_pagina_caderno_tc(
    caderno_id: int, inicio: int, page_size: int = 200, relogin: bool = False
) -> dict[str, Any]:
    log.info(
        "tc_unit.task_received",
        caderno_id=caderno_id,
        inicio=inicio,
        page_size=page_size,
        relogin=relogin,
    )
    result = await execute_caderno_page_unit(
        caderno_id=caderno_id,
        inicio=inicio,
        page_size=page_size,
        relogin=relogin,
    )
    return result.to_dict()


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


async def _fetch_page_from_tc(
    caderno_id: int, inicio: int, page_size: int
) -> list[dict[str, Any]]:
    # Warmup redirect (302 → /login) = sessão morta. Reloga uma vez e retenta;
    # se continuar redirecionando, deixa o block policy aplicar o cooldown.
    for attempt in (1, 2):
        cookies = load_cookies_for_httpx()
        async with TcClient(cookies) as client:
            warm = await client._client.get(  # noqa: SLF001
                f"/questoes/cadernos/{caderno_id}",
                headers={"Accept": "text/html"},
            )
            log.info(
                "tc_unit.warmup",
                caderno_id=caderno_id,
                status=warm.status_code,
                attempt=attempt,
            )
            if warm.status_code in _REDIRECT_STATUSES:
                if attempt == 1:
                    await _ensure_fresh_session()
                    continue
                raise SessionExpired(
                    "warmup redirecionou para login mesmo após relogin"
                )
            return await fetch_pagina(client, caderno_id, inicio, page_size)
    raise SessionExpired("warmup esgotou tentativas")


async def _ensure_fresh_session(*, max_age_seconds: float = 60.0) -> None:
    """Reloga no TC, exceto se a sessão em disco acabou de ser renovada."""
    settings = get_settings()
    try:
        age = time.time() - settings.tc_storage_state_path.stat().st_mtime
    except OSError:
        age = None
    if age is not None and 0 <= age < max_age_seconds:
        log.info("tc_unit.relogin_skipped", storage_age_seconds=round(age, 1))
        return
    log.info("tc_unit.relogin_start", storage_age_seconds=age and round(age, 1))
    await login_and_save_state(headless=True)


async def _upsert_questao_default(q: QuestaoApi, raw: dict[str, Any]) -> int:
    return await upsert_questao(q, raw=raw)


async def _index_meili_best_effort(
    session_factory: async_sessionmaker, pks: list[int]
) -> None:
    settings = get_settings()
    if not (settings.meili_url and settings.meili_key and pks):
        return
    try:
        from meili_index import build_docs, push_docs_http

        async with session_factory() as session:
            docs = await build_docs(session, ids=pks)
        sent = await push_docs_http(
            docs,
            meili_url=settings.meili_url,
            meili_key=settings.meili_key,
        )
        log.info("tc_unit.meili_indexed", docs=sent)
    except Exception as exc:  # noqa: BLE001
        log.warning("tc_unit.meili_failed", err=str(exc), pks=len(pks))


async def _enqueue_next_caderno_unit(
    session_factory: async_sessionmaker,
    *,
    caderno_id: int,
) -> int | None:
    async with session_factory.begin() as session:
        units = await list_enqueueable_caderno_units(
            session,
            caderno_id=caderno_id,
            limit=1,
        )
    if not units:
        return None

    unit = units[0]
    await enqueue(
        coletar_pagina_caderno_tc,
        priority="default",
        caderno_id=caderno_id,
        inicio=unit["inicio"],
        page_size=unit["page_size"],
        relogin=_should_relogin_for_unit(unit),
        isolated_broker=True,
    )
    return int(unit["inicio"])


def _block_policy(exc: Exception) -> tuple[str, int]:
    settings = get_settings()
    if isinstance(exc, SessionExpired):
        return "session_expired", settings.tc_block_401_452_seconds
    if isinstance(exc, CaptchaChallenge):
        return "captcha", settings.tc_block_401_452_seconds
    if isinstance(exc, RateLimited):
        return "rate_limited", max(
            int(exc.retry_after), settings.tc_block_403_429_seconds
        )
    if isinstance(exc, AccessBlocked):
        return "access_blocked", settings.tc_block_403_429_seconds
    return "unknown_block", settings.tc_block_403_429_seconds


def _should_relogin_for_unit(unit: dict[str, Any]) -> bool:
    return unit.get("status") == "blocked" and unit.get("block_reason") == "session_expired"


async def _pause_after_unit() -> None:
    settings = get_settings()
    await asyncio.sleep(
        random.uniform(settings.imprimir_pause_min, settings.imprimir_pause_max)
    )
