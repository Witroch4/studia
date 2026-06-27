import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.tasks.ledger import ensure_ledger_schema, upsert_comentario_job
from app.main import _supervisor_tick_comentarios


@pytest.mark.asyncio
async def test_tick_enfileira_units_pendentes():
    eng = create_async_engine(get_settings().database_url)
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S.begin() as s:
            await upsert_comentario_job(s, caderno_id=999777, questao_ids=[1, 2], requested_by=None)
        chamadas = []

        async def fake_enqueue(questao_id, caderno_id):
            chamadas.append((questao_id, caderno_id))

        n = await _supervisor_tick_comentarios(S, fake_enqueue)
        assert n >= 1 and len(chamadas) >= 1
    finally:
        await eng.dispose()
