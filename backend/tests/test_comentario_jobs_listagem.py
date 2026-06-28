import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_lista_jobs_comentarios(db_session, client):
    # Cria tabelas do ledger (scraper-owned; não existem no schema ORM).
    # A transação do db_session faz rollback ao fim do teste — cada teste
    # é isolado mesmo sem IF NOT EXISTS.
    await db_session.execute(text(
        """
        CREATE TABLE tc_jobs (
          id BIGINT PRIMARY KEY,
          kind TEXT NOT NULL,
          status TEXT NOT NULL,
          source TEXT NOT NULL,
          external_id TEXT,
          total_units INTEGER NOT NULL DEFAULT 0,
          done_units INTEGER NOT NULL DEFAULT 0,
          failed_units INTEGER NOT NULL DEFAULT 0,
          blocked_units INTEGER NOT NULL DEFAULT 0,
          paused_by_user BOOLEAN NOT NULL DEFAULT FALSE,
          params JSONB,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ
        )
        """
    ))
    await db_session.execute(text(
        """
        CREATE TABLE tc_comentario_units (
          id BIGSERIAL PRIMARY KEY,
          job_id BIGINT NOT NULL,
          caderno_id BIGINT NOT NULL,
          questao_id BIGINT NOT NULL,
          status TEXT NOT NULL,
          coments_alunos INTEGER NOT NULL DEFAULT 0,
          coments_professores INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    ))

    # Semeia um job de comentários + units direto no ledger
    await db_session.execute(text(
        "INSERT INTO tc_jobs (id, kind, status, source, external_id, total_units, done_units) "
        "VALUES (5001,'comentarios','running','tc','42',2,1)"
    ))
    await db_session.execute(text(
        "INSERT INTO tc_comentario_units (job_id, caderno_id, questao_id, status, coments_alunos) "
        "VALUES (5001,42,11,'done',3),(5001,42,12,'pending',0)"
    ))
    await db_session.commit()

    r = await client.get("/api/q/coletar/comentario-jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    j = next(x for x in jobs if x["job_id"] == 5001)
    assert j["total_units"] == 2 and j["done_units"] == 1
    assert j["pending_units"] == 1 and j["pct_units_done"] == 50.0


@pytest.mark.asyncio
async def test_lista_jobs_comentarios_sem_jobs(db_session, client):
    """Retorna lista vazia quando não há jobs de comentários."""
    await db_session.execute(text(
        """
        CREATE TABLE tc_jobs (
          id BIGINT PRIMARY KEY,
          kind TEXT NOT NULL,
          status TEXT NOT NULL,
          source TEXT NOT NULL,
          external_id TEXT,
          total_units INTEGER NOT NULL DEFAULT 0,
          done_units INTEGER NOT NULL DEFAULT 0,
          failed_units INTEGER NOT NULL DEFAULT 0,
          blocked_units INTEGER NOT NULL DEFAULT 0,
          paused_by_user BOOLEAN NOT NULL DEFAULT FALSE,
          params JSONB,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ
        )
        """
    ))
    await db_session.execute(text(
        """
        CREATE TABLE tc_comentario_units (
          id BIGSERIAL PRIMARY KEY,
          job_id BIGINT NOT NULL,
          caderno_id BIGINT NOT NULL,
          questao_id BIGINT NOT NULL,
          status TEXT NOT NULL,
          coments_alunos INTEGER NOT NULL DEFAULT 0,
          coments_professores INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    ))
    await db_session.commit()

    r = await client.get("/api/q/coletar/comentario-jobs")
    assert r.status_code == 200
    assert r.json()["jobs"] == []


@pytest.mark.asyncio
async def test_lista_jobs_comentarios_pct_total_zero(db_session, client):
    """total_units=0 → pct_units_done=0.0 (sem divisão por zero)."""
    await db_session.execute(text(
        """
        CREATE TABLE tc_jobs (
          id BIGINT PRIMARY KEY,
          kind TEXT NOT NULL,
          status TEXT NOT NULL,
          source TEXT NOT NULL,
          external_id TEXT,
          total_units INTEGER NOT NULL DEFAULT 0,
          done_units INTEGER NOT NULL DEFAULT 0,
          failed_units INTEGER NOT NULL DEFAULT 0,
          blocked_units INTEGER NOT NULL DEFAULT 0,
          paused_by_user BOOLEAN NOT NULL DEFAULT FALSE,
          params JSONB,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ
        )
        """
    ))
    await db_session.execute(text(
        """
        CREATE TABLE tc_comentario_units (
          id BIGSERIAL PRIMARY KEY,
          job_id BIGINT NOT NULL,
          caderno_id BIGINT NOT NULL,
          questao_id BIGINT NOT NULL,
          status TEXT NOT NULL,
          coments_alunos INTEGER NOT NULL DEFAULT 0,
          coments_professores INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    ))
    await db_session.execute(text(
        "INSERT INTO tc_jobs (id, kind, status, source, external_id, total_units, done_units) "
        "VALUES (5002,'comentarios','pending','tc','99',0,0)"
    ))
    await db_session.commit()

    r = await client.get("/api/q/coletar/comentario-jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    j = next(x for x in jobs if x["job_id"] == 5002)
    assert j["pct_units_done"] == 0.0
