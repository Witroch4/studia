from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import concursos_router
from auth import get_current_user_opt
from database import get_db
from main import app

PAYLOAD = {
    "concurso": {
        "concurso_id_externo": 86869,
        "edital_id_externo": 19626,
        "nome_completo": "Analista (IPLANFOR)/2024",
        "url_concurso": "analista-iplanfor-2024",
        "banca_nome": "IDECAN",
        "orgao_sigla": "IPPLAN",
        "orgao_nome": "Instituto",
        "edital_nome": "01/2024",
        "ano": 2024,
        "data_aplicacao": "14/04/2024 00:00:00",
        "escolaridade": "Superior",
    },
    "arquivos": [
        {
            "tipo": "EDITAL",
            "arquivo_id_externo": 452178,
            "uuid": "u-ed",
            "nome_arquivo": "edital.pdf",
            "minio_object_key": "concursos/u-ed.pdf",
            "content_type": "application/pdf",
            "tamanho_bytes": 100,
        },
    ],
}


@pytest_asyncio.fixture
async def client_sem_auth(db_session):
    """Cliente HTTP sem sessão autenticada (user=None, sem override de auth).

    Mesmo padrão de tests/test_internal_token_auth.py: sobrescreve só get_db,
    não sobrescreve get_current_user_opt — assim o endpoint recebe user=None
    e o `require_user_or_service` cai no caminho do token de serviço.
    """

    async def override_get_db():
        yield db_session

    previous_db = app.dependency_overrides.get(get_db)
    previous_user = app.dependency_overrides.pop(get_current_user_opt, None)
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client
    finally:
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db
        if previous_user is not None:
            app.dependency_overrides[get_current_user_opt] = previous_user


@pytest.mark.asyncio
async def test_importar_idempotente(client):
    r1 = await client.post("/api/q/concursos/importar", json=PAYLOAD)
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["ok"] is True
    assert body1["arquivos"] == 1
    concurso_id = body1["concurso_id"]

    # Repetir NÃO duplica: mesmo concurso_id, mesma contagem de arquivos.
    r2 = await client.post("/api/q/concursos/importar", json=PAYLOAD)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["concurso_id"] == concurso_id
    assert body2["arquivos"] == 1

    lista = await client.get("/api/q/concursos")
    assert lista.status_code == 200
    data = lista.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["concurso_id_externo"] == 86869
    assert item["nome_completo"] == "Analista (IPLANFOR)/2024"
    assert item["data_aplicacao"] == "2024-04-14T00:00:00"
    assert item["ano"] == 2024
    assert len(item["arquivos"]) == 1
    assert item["arquivos"][0]["nome_arquivo"] == "edital.pdf"
    assert item["arquivos"][0]["tipo"] == "EDITAL"


@pytest.mark.asyncio
async def test_importar_atualiza_campos_em_reimport(client):
    await client.post("/api/q/concursos/importar", json=PAYLOAD)

    payload2 = {
        "concurso": {**PAYLOAD["concurso"], "banca_nome": "CESPE", "ano": 2025},
        "arquivos": PAYLOAD["arquivos"],
    }
    r2 = await client.post("/api/q/concursos/importar", json=payload2)
    assert r2.status_code == 200

    lista = await client.get("/api/q/concursos")
    item = lista.json()["items"][0]
    assert item["banca_nome"] == "CESPE"
    assert item["ano"] == 2025


@pytest.mark.asyncio
async def test_importar_sem_token_401(client_sem_auth):
    r = await client_sem_auth.post("/api/q/concursos/importar", json=PAYLOAD)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_importar_via_token_servico(client_sem_auth, monkeypatch):
    monkeypatch.setenv("STUDIA_INTERNAL_TOKEN", "segredo123")
    r = await client_sem_auth.post(
        "/api/q/concursos/importar",
        json=PAYLOAD,
        headers={"X-Internal-Token": "segredo123"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r_errado = await client_sem_auth.post(
        "/api/q/concursos/importar",
        json=PAYLOAD,
        headers={"X-Internal-Token": "errado"},
    )
    assert r_errado.status_code == 401


@pytest.mark.asyncio
async def test_listagem_paginacao_e_busca(client):
    for i in range(3):
        payload = {
            "concurso": {
                **PAYLOAD["concurso"],
                "concurso_id_externo": 90000 + i,
                "nome_completo": f"Concurso {i}",
                "ano": 2020 + i,
            },
            "arquivos": [],
        }
        r = await client.post("/api/q/concursos/importar", json=payload)
        assert r.status_code == 200

    # ano DESC, id DESC
    lista = await client.get("/api/q/concursos", params={"page_size": 2})
    data = lista.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert [it["ano"] for it in data["items"]] == [2022, 2021]

    pagina2 = await client.get("/api/q/concursos", params={"page": 2, "page_size": 2})
    assert len(pagina2.json()["items"]) == 1

    busca = await client.get("/api/q/concursos", params={"busca": "Concurso 1"})
    assert busca.json()["total"] == 1
    assert busca.json()["items"][0]["nome_completo"] == "Concurso 1"


@pytest.mark.asyncio
async def test_listagem_requer_admin(client, auth_state):
    from tests.conftest import USER_A

    auth_state["user"] = USER_A
    r = await client.get("/api/q/concursos")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_stream_arquivo(client, monkeypatch):
    await client.post("/api/q/concursos/importar", json=PAYLOAD)
    lista = await client.get("/api/q/concursos")
    arquivo_id = lista.json()["items"][0]["arquivos"][0]["id"]

    monkeypatch.setattr(concursos_router, "download_bytes", lambda key: b"%PDF-fake-bytes")

    r = await client.get(f"/api/q/concursos/arquivo/{arquivo_id}")
    assert r.status_code == 200
    assert r.content == b"%PDF-fake-bytes"
    assert r.headers["content-type"] == "application/pdf"
    assert 'attachment; filename="edital.pdf"' in r.headers["content-disposition"]


@pytest.mark.asyncio
async def test_stream_arquivo_inexistente_404(client):
    r = await client.get("/api/q/concursos/arquivo/999999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_coletar_proxy_scraper(client, monkeypatch):
    calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "job_id": 321,
                "status": "running",
                "total_units": 5,
                "enqueued_units": 5,
                "message": "ok",
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

    monkeypatch.setattr(concursos_router.httpx, "AsyncClient", FakeAsyncClient)

    r = await client.post(
        "/api/q/concursos/coletar",
        json={"filtros": [{"id": 1, "tipo": "banca"}]},
    )
    assert r.status_code == 202
    assert r.json() == {
        "job_id": 321,
        "status": "running",
        "total_units": 5,
        "enqueued_units": 5,
        "message": "ok",
    }
    assert calls == [
        {
            "url": "http://scraper:8090/enqueue/concursos",
            "json": {"filtros": [{"id": 1, "tipo": "banca"}]},
        }
    ]


@pytest.mark.asyncio
async def test_coletar_proxy_erro_scraper_mapeia_502(client, monkeypatch):
    class FakeResponse:
        status_code = 500
        text = "boom"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr(concursos_router.httpx, "AsyncClient", FakeAsyncClient)

    r = await client.post("/api/q/concursos/coletar", json={"filtros": []})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_filtros_proxy_scraper(client, monkeypatch):
    calls: list[str] = []

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"bancas": ["CESPE", "FGV"], "profissoes": ["Analista"]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(concursos_router.httpx, "AsyncClient", FakeAsyncClient)

    r = await client.get("/api/q/concursos/filtros")
    assert r.status_code == 200
    assert r.json() == {"bancas": ["CESPE", "FGV"], "profissoes": ["Analista"]}
    assert calls == ["http://scraper:8090/tc/concursos/filtros"]


@pytest.mark.asyncio
async def test_jobs_sem_tabela_ledger_retorna_vazio(client):
    """Antes de qualquer coleta, tc_jobs pode nem existir — sem 500."""
    r = await client.get("/api/q/concursos/jobs")
    assert r.status_code == 200
    assert r.json() == {"jobs": []}


@pytest.mark.asyncio
async def test_jobs_lista_progresso_do_ledger(db_session, client):
    # tc_jobs é criada/migrada pelo scraper (ledger); não existe no schema ORM.
    await db_session.execute(
        text(
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
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO tc_jobs
              (id, kind, status, source, external_id, total_units, done_units,
               failed_units, blocked_units, paused_by_user, params, updated_at)
            VALUES
              (8001, 'concursos', 'running', 'tc', NULL, 10, 3, 0, 1, false,
               '{"discovery": "pending", "filtros": [{"id": 1, "tipo": "banca"}]}'::jsonb,
               now())
            """
        )
    )
    await db_session.commit()

    r = await client.get("/api/q/concursos/jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    j = next(x for x in jobs if x["job_id"] == 8001)
    assert j["status"] == "running"
    assert j["paused"] is False
    assert j["total_units"] == 10
    assert j["done_units"] == 3
    assert j["blocked_units"] == 1
    assert j["discovery"] == "pending"
    assert j["filtros"] == [{"id": 1, "tipo": "banca"}]
    assert j["atualizado_em"] is not None
