from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)

from app.tasks.caderno import execute_caderno_page_unit
from app.tasks.ledger import ensure_ledger_schema, upsert_caderno_job


async def _prepare_job(caderno_id: int) -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(
                text("DELETE FROM tc_caderno_questoes WHERE caderno_id = :c"),
                {"c": caderno_id},
            )
            await conn.execute(
                text("DELETE FROM tc_jobs WHERE kind = 'caderno' AND external_id = :e"),
                {"e": str(caderno_id)},
            )
            # FK exige questões reais; cria stubs com PKs determinísticas.
            for pk in (501, 502):
                await conn.execute(
                    text(
                        "INSERT INTO questoes (id, id_externo, status) "
                        "VALUES (:id, :ext, 'ATIVA') ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": pk, "ext": 79000000 + pk},
                )
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            await upsert_caderno_job(
                session, caderno_id=caderno_id, expected_total=400, page_size=200
            )
    finally:
        await engine.dispose()


async def _membership(caderno_id: int) -> list[tuple[int, int]]:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT questao_id, posicao FROM tc_caderno_questoes "
                        "WHERE caderno_id = :c ORDER BY posicao"
                    ),
                    {"c": caderno_id},
                )
            ).all()
            return [(int(r[0]), int(r[1])) for r in rows]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_membership_registra_posicao_por_caderno(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    caderno_id = 990100001
    await _prepare_job(caderno_id)

    async def fetcher(caderno_id: int, inicio: int, page_size: int) -> list[dict]:
        return [
            {"idQuestao": 70000001, "numeroQuestaoAtual": inicio + 1},
            {"idQuestao": 70000002, "numeroQuestaoAtual": inicio + 2},
        ]

    pk_map = {70000001: 501, 70000002: 502}

    async def upserter(q, raw: dict) -> int:
        return pk_map[q.idQuestao]

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

    # posicao = inicio + idx + 1  -> 201, 202
    assert await _membership(caderno_id) == [(501, 201), (502, 202)]
