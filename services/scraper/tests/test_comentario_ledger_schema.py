import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.tasks.ledger import ensure_ledger_schema

@pytest.mark.asyncio
async def test_cria_tc_comentario_units():
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            r = await conn.execute(text(
                "SELECT to_regclass('public.tc_comentario_units')"))
            assert r.scalar() is not None
            cols = (await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='tc_comentario_units'"))).scalars().all()
            assert {"job_id","caderno_id","questao_id","status",
                    "coments_alunos","coments_professores","blocked_until"} <= set(cols)
    finally:
        await engine.dispose()
