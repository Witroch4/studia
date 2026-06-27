import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.tasks.ledger import (
    ensure_ledger_schema, upsert_comentario_job, lease_comentario_unit,
    is_comentario_paused, release_comentario_unit_to_pending, set_caderno_job_paused,
)

@pytest.mark.asyncio
async def test_pause_release_comentarios():
    eng = create_async_engine(get_settings().database_url)
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
            await c.execute(text("DELETE FROM tc_jobs WHERE kind='comentarios' AND external_id='999500'"))
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S.begin() as s:
            job = await upsert_comentario_job(s, caderno_id=999500, questao_ids=[1, 2], requested_by=None)
        # set_caderno_job_paused funciona p/ job de comentários (era kind=caderno só)
        async with S.begin() as s:
            ok = await set_caderno_job_paused(s, job_id=job.id, paused=True)
        assert ok is True
        async with S.begin() as s:
            assert await is_comentario_paused(s, caderno_id=999500) is True
        # lease + release volta pra pending
        async with S.begin() as s:
            leased = await lease_comentario_unit(s, caderno_id=999500, questao_id=1, ack_wait_seconds=300)
        async with S.begin() as s:
            await release_comentario_unit_to_pending(s, unit_id=leased["unit_id"])
        async with S.begin() as s:
            st = (await s.execute(text("SELECT status FROM tc_comentario_units WHERE id=:i"),
                                  {"i": leased["unit_id"]})).scalar_one()
        assert st == "pending"
    finally:
        await eng.dispose()
