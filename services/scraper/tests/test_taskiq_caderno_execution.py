from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)

from app.schemas import SessionExpired
import app.tasks.caderno as caderno_tasks
from app.tasks.caderno import execute_caderno_page_unit
from app.tasks.ledger import (
    ensure_ledger_schema,
    lease_caderno_unit,
    list_enqueueable_caderno_units,
    upsert_caderno_job,
)


async def _prepare_job(caderno_id: int) -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(
                text("DELETE FROM tc_jobs WHERE kind = 'caderno' AND external_id = :external_id"),
                {"external_id": str(caderno_id)},
            )

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            await upsert_caderno_job(
                session,
                caderno_id=caderno_id,
                expected_total=600,
                page_size=200,
            )
    finally:
        await engine.dispose()


async def _unit_rows(caderno_id: int) -> list[dict]:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT inicio, status, attempts, questoes_ok, block_reason,
                               blocked_until, last_error
                        FROM tc_caderno_units
                        WHERE caderno_id = :caderno_id
                        ORDER BY inicio
                        """
                    ),
                    {"caderno_id": caderno_id},
                )
            ).mappings().all()
            return [dict(row) for row in rows]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execute_caderno_page_unit_marks_only_requested_range_done(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000001
    calls: list[tuple[int, int, int]] = []
    persisted: list[int] = []
    await _prepare_job(caderno_id)

    async def fetcher(caderno_id: int, inicio: int, page_size: int) -> list[dict]:
        calls.append((caderno_id, inicio, page_size))
        return [{"idQuestao": 123456, "numeroQuestaoAtual": inicio + 1}]

    async def upserter(q, raw: dict) -> int:
        persisted.append(q.idQuestao)
        return 1

    result = await execute_caderno_page_unit(
        caderno_id=caderno_id,
        inicio=200,
        page_size=200,
        fetcher=fetcher,
        upserter=upserter,
        pause_after=False,
        chain_next=False,
    )

    assert result.status == "done"
    assert result.inicio == 200
    assert result.questoes_ok == 1
    assert calls == [(caderno_id, 200, 200)]
    assert persisted == [123456]

    rows = await _unit_rows(caderno_id)
    assert [(row["inicio"], row["status"], row["attempts"]) for row in rows] == [
        (0, "pending", 0),
        (200, "done", 1),
        (400, "pending", 0),
    ]


@pytest.mark.asyncio
async def test_execute_caderno_page_unit_blocks_same_range_without_touching_previous(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000002
    calls: list[tuple[int, int, int]] = []
    await _prepare_job(caderno_id)

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE tc_caderno_units
                    SET status = 'done', attempts = 1, questoes_ok = 200
                    WHERE caderno_id = :caderno_id AND inicio = 0
                    """
                ),
                {"caderno_id": caderno_id},
            )
    finally:
        await engine.dispose()

    async def fetcher(caderno_id: int, inicio: int, page_size: int) -> list[dict]:
        calls.append((caderno_id, inicio, page_size))
        raise SessionExpired("sessao queimada")

    result = await execute_caderno_page_unit(
        caderno_id=caderno_id,
        inicio=200,
        page_size=200,
        fetcher=fetcher,
        pause_after=False,
        chain_next=False,
    )

    assert result.status == "blocked"
    assert result.inicio == 200
    assert calls == [(caderno_id, 200, 200)]

    rows = await _unit_rows(caderno_id)
    assert [(row["inicio"], row["status"], row["attempts"]) for row in rows] == [
        (0, "done", 1),
        (200, "blocked", 1),
        (400, "pending", 0),
    ]
    blocked = rows[1]
    assert blocked["block_reason"] == "session_expired"
    assert blocked["blocked_until"] is not None
    assert "sessao queimada" in blocked["last_error"]


@pytest.mark.asyncio
async def test_execute_caderno_page_unit_marks_requested_range_failed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000003
    await _prepare_job(caderno_id)

    async def fetcher(caderno_id: int, inicio: int, page_size: int) -> list[dict]:
        raise RuntimeError(f"boom at {inicio}")

    result = await execute_caderno_page_unit(
        caderno_id=caderno_id,
        inicio=400,
        page_size=200,
        fetcher=fetcher,
        pause_after=False,
        chain_next=False,
    )

    assert result.status == "failed"
    assert result.inicio == 400

    rows = await _unit_rows(caderno_id)
    assert [(row["inicio"], row["status"], row["attempts"]) for row in rows] == [
        (0, "pending", 0),
        (200, "pending", 0),
        (400, "failed", 1),
    ]
    assert "boom at 400" in rows[2]["last_error"]


@pytest.mark.asyncio
async def test_active_blocked_range_prevents_later_range_enqueue_and_lease(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000007
    await _prepare_job(caderno_id)

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            await session.execute(
                text(
                    """
                    UPDATE tc_caderno_units
                    SET status = CASE
                          WHEN inicio = 0 THEN 'done'
                          WHEN inicio = 200 THEN 'blocked'
                          ELSE status
                        END,
                        blocked_until = CASE
                          WHEN inicio = 200 THEN now() + interval '2 hours'
                          ELSE blocked_until
                        END
                    WHERE caderno_id = :caderno_id
                    """
                ),
                {"caderno_id": caderno_id},
            )

        async with Session.begin() as session:
            enqueueable = await list_enqueueable_caderno_units(
                session,
                caderno_id=caderno_id,
            )
            leased = await lease_caderno_unit(
                session,
                caderno_id=caderno_id,
                inicio=400,
                page_size=200,
                task_id="old-message",
                lease_seconds=600,
            )

        assert enqueueable == []
        assert leased is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_caderno_job_reuses_failed_job_for_range_retry(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000004
    await _prepare_job(caderno_id)

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            first = await upsert_caderno_job(
                session,
                caderno_id=caderno_id,
                expected_total=600,
                page_size=200,
            )
            await session.execute(
                text("UPDATE tc_jobs SET status = 'failed' WHERE id = :job_id"),
                {"job_id": first.id},
            )
            await session.execute(
                text(
                    """
                    UPDATE tc_caderno_units
                    SET status = CASE WHEN inicio = 200 THEN 'failed' ELSE 'done' END
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": first.id},
            )

        async with Session.begin() as session:
            second = await upsert_caderno_job(
                session,
                caderno_id=caderno_id,
                expected_total=600,
                page_size=200,
            )
            units = await list_enqueueable_caderno_units(
                session,
                caderno_id=caderno_id,
            )

        assert second.id == first.id
        assert [unit["inicio"] for unit in units] == [200]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execute_caderno_page_unit_enqueues_next_range_after_success(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000005
    enqueued: list[dict] = []
    await _prepare_job(caderno_id)

    async def fetcher(caderno_id: int, inicio: int, page_size: int) -> list[dict]:
        return [{"idQuestao": 555001, "numeroQuestaoAtual": inicio + 1}]

    async def upserter(q, raw: dict) -> int:
        return 1

    async def fake_enqueue(task, *, priority="default", labels=None, **kwargs):
        enqueued.append({"task": task, "priority": priority, "labels": labels, **kwargs})

    monkeypatch.setattr(caderno_tasks, "enqueue", fake_enqueue)

    result = await execute_caderno_page_unit(
        caderno_id=caderno_id,
        inicio=0,
        page_size=200,
        fetcher=fetcher,
        upserter=upserter,
        pause_after=False,
    )

    assert result.status == "done"
    assert result.enqueued_next_inicio == 200
    assert len(enqueued) == 1
    assert enqueued[0]["task"] is caderno_tasks.coletar_pagina_caderno_tc
    assert enqueued[0]["labels"] is None
    assert enqueued[0]["caderno_id"] == caderno_id
    assert enqueued[0]["inicio"] == 200
    assert enqueued[0]["page_size"] == 200
    assert enqueued[0]["relogin"] is False


@pytest.mark.asyncio
async def test_reenqueue_blocked_session_expired_range_requests_relogin(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000008
    enqueued: list[dict] = []
    await _prepare_job(caderno_id)

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE tc_caderno_units
                    SET status = CASE
                          WHEN inicio = 200 THEN 'blocked'
                          ELSE status
                        END,
                        block_reason = CASE
                          WHEN inicio = 200 THEN 'session_expired'
                          ELSE block_reason
                        END,
                        blocked_until = CASE
                          WHEN inicio = 200 THEN now() - interval '1 minute'
                          ELSE blocked_until
                        END
                    WHERE caderno_id = :caderno_id
                    """
                ),
                {"caderno_id": caderno_id},
            )
    finally:
        await engine.dispose()

    async def fetcher(caderno_id: int, inicio: int, page_size: int) -> list[dict]:
        return [{"idQuestao": 888001, "numeroQuestaoAtual": inicio + 1}]

    async def upserter(q, raw: dict) -> int:
        return 1

    async def fake_enqueue(task, *, priority="default", labels=None, **kwargs):
        enqueued.append({"task": task, "priority": priority, "labels": labels, **kwargs})

    monkeypatch.setattr(caderno_tasks, "enqueue", fake_enqueue)

    result = await execute_caderno_page_unit(
        caderno_id=caderno_id,
        inicio=0,
        page_size=200,
        fetcher=fetcher,
        upserter=upserter,
        pause_after=False,
    )

    assert result.status == "done"
    assert result.enqueued_next_inicio == 200
    assert len(enqueued) == 1
    assert enqueued[0]["inicio"] == 200
    assert enqueued[0]["relogin"] is True


@pytest.mark.asyncio
async def test_execute_caderno_page_unit_can_relogin_inside_worker(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990000006
    relogins: list[bool] = []
    fetch_calls: list[tuple[int, int, int]] = []
    await _prepare_job(caderno_id)

    async def fake_login_and_save_state(*, headless: bool = True):
        relogins.append(headless)
        return "/tmp/storage_state.json"

    async def fetcher(caderno_id: int, inicio: int, page_size: int) -> list[dict]:
        fetch_calls.append((caderno_id, inicio, page_size))
        return [{"idQuestao": 666001, "numeroQuestaoAtual": inicio + 1}]

    async def upserter(q, raw: dict) -> int:
        return 1

    async def fake_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr(caderno_tasks, "login_and_save_state", fake_login_and_save_state)
    monkeypatch.setattr(caderno_tasks, "enqueue", fake_enqueue)

    result = await execute_caderno_page_unit(
        caderno_id=caderno_id,
        inicio=0,
        page_size=200,
        fetcher=fetcher,
        upserter=upserter,
        pause_after=False,
        relogin=True,
    )

    assert result.status == "done"
    assert relogins == [True]
    assert fetch_calls == [(caderno_id, 0, 200)]
