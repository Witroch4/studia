import pytest
from sqlalchemy import text


async def _ledger(db):
    await db.execute(text("CREATE TABLE IF NOT EXISTS tc_jobs (id BIGINT PRIMARY KEY, kind TEXT, status TEXT, source TEXT, external_id TEXT, total_units INT DEFAULT 0, done_units INT DEFAULT 0, failed_units INT DEFAULT 0, blocked_units INT DEFAULT 0, paused_by_user BOOLEAN DEFAULT false, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())"))
    await db.execute(text("CREATE TABLE IF NOT EXISTS tc_comentario_units (id BIGSERIAL PRIMARY KEY, job_id BIGINT, caderno_id BIGINT, questao_id BIGINT, status TEXT, coments_alunos INT DEFAULT 0, coments_professores INT DEFAULT 0, block_reason TEXT, last_error TEXT, updated_at TIMESTAMPTZ DEFAULT now())"))

@pytest.mark.asyncio
async def test_eventos_e_questao_atual(db_session, client):
    await _ledger(db_session)
    await db_session.execute(text("INSERT INTO tc_jobs (id,kind,status,source,external_id,total_units,done_units) VALUES (7001,'comentarios','running','tc','74',2,1)"))
    await db_session.execute(text("INSERT INTO tc_comentario_units (job_id,caderno_id,questao_id,status,coments_alunos) VALUES (7001,74,1934,'done',5),(7001,74,1935,'running',0)"))
    await db_session.commit()
    j = next(x for x in (await client.get("/api/q/coletar/comentario-jobs")).json()["jobs"] if x["job_id"] == 7001)
    assert j["questao_atual"] == 1935 and j["updated_at"] is not None
    ev = (await client.get("/api/q/coletar/comentario-jobs/7001/eventos?limit=10")).json()["eventos"]
    assert any(e["questao_id"] == 1934 and e["coments_alunos"] == 5 for e in ev)
