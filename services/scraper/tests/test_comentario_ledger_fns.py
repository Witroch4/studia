import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.tasks.ledger import (
    ensure_ledger_schema, upsert_comentario_job,
    list_enqueueable_comentario_units, lease_comentario_unit,
    mark_comentario_unit_done, refresh_comentario_job_status,
)

_TEST_CADERNO_ID = 999001


@pytest.mark.asyncio
async def test_job_units_lifecycle():
    eng = create_async_engine(get_settings().database_url)
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
            # Limpa dados de execuções anteriores para garantir isolamento
            await c.execute(text(
                "DELETE FROM tc_jobs WHERE kind='comentarios' AND external_id=:eid"),
                {"eid": str(_TEST_CADERNO_ID)})
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S.begin() as s:
            job = await upsert_comentario_job(
                s, caderno_id=_TEST_CADERNO_ID, questao_ids=[11, 12, 13], requested_by=None)
        assert job.total_units == 3
        async with S.begin() as s:
            units = await list_enqueueable_comentario_units(s, caderno_id=_TEST_CADERNO_ID, limit=10)
        assert len(units) == 3
        async with S.begin() as s:
            leased = await lease_comentario_unit(
                s, caderno_id=_TEST_CADERNO_ID, questao_id=11, ack_wait_seconds=300)
        assert leased is not None
        async with S.begin() as s:
            await mark_comentario_unit_done(
                s, unit_id=leased["unit_id"], job_id=job.id,
                coments_alunos=2, coments_professores=1)
            await refresh_comentario_job_status(s, job_id=job.id)
        async with S.begin() as s:
            restantes = await list_enqueueable_comentario_units(s, caderno_id=_TEST_CADERNO_ID, limit=10)
        assert len(restantes) == 2  # uma concluída
    finally:
        await eng.dispose()
