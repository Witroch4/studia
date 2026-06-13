from __future__ import annotations

import pytest
from sqlalchemy import text

from models import CadernoQuestoes


@pytest.mark.asyncio
async def test_coletar_enqueues_scraper_job(client, monkeypatch):
    import q_router

    calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = '{"job_id": 77}'

        def json(self):
            return {
                "job_id": 77,
                "status": "running",
                "total_units": 113,
                "enqueued_units": 1,
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "json": json})
            return FakeResponse()

    monkeypatch.setattr(q_router.httpx, "AsyncClient", FakeAsyncClient)

    response = await client.post(
        "/api/q/coletar",
        json={
            "url": "https://www.tecconcursos.com.br/questoes/cadernos/95872821",
            "relogin": True,
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "caderno_id": 95872821,
        "expected_total": 22455,
        "job_id": 77,
        "status": "running",
        "total_units": 113,
        "enqueued_units": 1,
        "message": "job registrado; primeira faixa enfileirada e UI liberada",
    }
    assert calls == [
        {
            "url": "http://scraper:8090/enqueue/caderno",
            "json": {
                "caderno_id": 95872821,
                "expected_total": 22455,
                "page_size": 200,
                "enqueue_limit": 1,
                "discover_total": False,
                "relogin": True,
            },
        }
    ]


@pytest.mark.asyncio
async def test_coletar_unknown_caderno_requires_expected_total(client, monkeypatch):
    response = await client.post(
        "/api/q/coletar",
        json={"url": "https://www.tecconcursos.com.br/questoes/cadernos/123456789"},
    )

    assert response.status_code == 422
    assert "total esperado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_coletar_blocked_job_is_accepted(client, monkeypatch):
    import q_router

    class FakeResponse:
        status_code = 200
        text = '{"job_id": 78}'

        def json(self):
            return {
                "job_id": 78,
                "status": "blocked",
                "total_units": 149,
                "enqueued_units": 0,
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr(q_router.httpx, "AsyncClient", FakeAsyncClient)

    response = await client.post(
        "/api/q/coletar",
        json={
            "url": "https://www.tecconcursos.com.br/questoes/cadernos/95872872",
            "expected_total": 29774,
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "blocked"
    assert response.json()["enqueued_units"] == 0
    assert "retomara a faixa exata automaticamente" in response.json()["message"]


@pytest.mark.asyncio
async def test_listar_jobs_coleta_returns_active_job_progress(client, db_session):
    await db_session.execute(
        text(
            """
            CREATE TABLE tc_jobs (
              id INTEGER PRIMARY KEY,
              kind TEXT NOT NULL,
              status TEXT NOT NULL,
              source TEXT NOT NULL,
              external_id TEXT,
              expected_total INTEGER,
              total_units INTEGER NOT NULL DEFAULT 0,
              done_units INTEGER NOT NULL DEFAULT 0,
              failed_units INTEGER NOT NULL DEFAULT 0,
              blocked_units INTEGER NOT NULL DEFAULT 0,
              paused_by_user INTEGER NOT NULL DEFAULT 0,
              params JSONB,
              updated_at TEXT
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            CREATE TABLE tc_caderno_units (
              id INTEGER PRIMARY KEY,
              job_id INTEGER NOT NULL,
              caderno_id INTEGER NOT NULL,
              inicio INTEGER NOT NULL,
              page_size INTEGER NOT NULL DEFAULT 200,
              status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              questoes_ok INTEGER NOT NULL DEFAULT 0,
              block_reason TEXT,
              blocked_until TEXT,
              leased_until TEXT
            )
            """
        )
    )
    # Tabela de membership do scraper (caderno→questões). A query usa um EXISTS
    # nela para `pode_montar`. Não é model SQLAlchemy, então create_all não a
    # cria no SQLite de teste — replicamos o mínimo (mesmas colunas do scraper).
    await db_session.execute(
        text(
            """
            CREATE TABLE tc_caderno_questoes (
              caderno_id INTEGER NOT NULL,
              questao_id INTEGER NOT NULL,
              posicao INTEGER NOT NULL,
              PRIMARY KEY (caderno_id, questao_id)
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO tc_jobs (
              id, kind, status, source, external_id, expected_total,
              total_units, done_units, failed_units, blocked_units, updated_at
            ) VALUES
              (11, 'caderno', 'blocked', 'tc', '95872821', 22455, 113, 22, 0, 2, '2026-06-09T21:40:00'),
              (12, 'caderno', 'done', 'tc', '99999999', 200, 1, 1, 0, 0, '2026-06-09T21:41:00')
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO tc_caderno_units (
              id, job_id, caderno_id, inicio, page_size, status, attempts,
              questoes_ok, block_reason, blocked_until, leased_until
            ) VALUES
              (101, 11, 95872821, 0, 200, 'done', 1, 200, NULL, NULL, NULL),
              (102, 11, 95872821, 200, 200, 'done', 1, 200, NULL, NULL, NULL),
              (103, 11, 95872821, 3400, 200, 'blocked', 1, 0, 'access_blocked', '2026-06-09T21:47:29', NULL),
              (104, 11, 95872821, 3600, 200, 'running', 2, 0, NULL, NULL, '2026-06-09T21:50:00'),
              (105, 11, 95872821, 3800, 200, 'queued', 0, 0, NULL, NULL, NULL),
              (106, 11, 95872821, 4000, 200, 'pending', 0, 0, NULL, NULL, NULL)
            """
        )
    )
    # Job 11 já tem questões coletadas (membership) → pode_montar = True.
    await db_session.execute(
        text("INSERT INTO tc_caderno_questoes (caderno_id, questao_id, posicao) VALUES (95872821, 1, 0)")
    )
    # Job 12 ('done') já foi materializado → sai da lista de jobs ativos
    # (o ramo `status='done' AND NOT EXISTS cadernos_questoes` só inclui done
    # ainda NÃO materializado, para o admin poder montar).
    db_session.add(CadernoQuestoes(nome="Caderno 99999999", tc_caderno_id=99999999, total=200))
    await db_session.commit()

    response = await client.get("/api/q/coletar/jobs")

    assert response.status_code == 200
    body = response.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["caderno_id"] == 95872821
    assert body["jobs"][0]["status"] == "blocked"
    assert body["jobs"][0]["pode_montar"] is True
    assert body["jobs"][0]["done_units"] == 22
    assert body["jobs"][0]["pending_units"] == 1
    assert body["jobs"][0]["queued_units"] == 1
    assert body["jobs"][0]["running_units"] == 1
    assert body["jobs"][0]["blocked_units"] == 2
    assert body["jobs"][0]["pct_units_done"] == pytest.approx(19.47, rel=0.001)
    assert body["jobs"][0]["blocked_ranges"][0]["inicio"] == 3400
    assert body["jobs"][0]["running_ranges"][0]["inicio"] == 3600
    assert body["jobs"][0]["queued_ranges"][0]["inicio"] == 3800
