from __future__ import annotations

import pytest
from sqlalchemy import text


def _fake_scraper(monkeypatch, *, resolve: dict, save: dict, enqueue: dict):
    """Substitui httpx.AsyncClient do guias_router por um stub determinístico."""
    import guias_router

    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload
            self.status_code = 200
            self.text = ""

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "json": json})
            if url.endswith("/guia/resolver"):
                return FakeResponse(resolve)
            if url.endswith("/guia/salvar-cadernos"):
                return FakeResponse(save)
            if url.endswith("/enqueue/caderno"):
                return FakeResponse(enqueue)
            raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(guias_router.httpx, "AsyncClient", FakeAsyncClient)
    return calls


RESOLVE = {
    "tc_guia_id": 6818,
    "slug": "oab-2026/nacional-unificado-oab",
    "url": "https://www.tecconcursos.com.br/guias/oab-2026/nacional-unificado-oab/-/-",
    "nome": "Guia OAB / 2026 para concurso Nacional Unificado",
    "banca": "FGV",
    "cadernos": [
        {
            "tc_caderno_id": 96081479,
            "caderno_base_id": 87000001,
            "nome": "Filosofia do Direito - OAB 2026 - 46º Exame",
            "total_questoes": 63,
            "total_capitulos": 0,
            "ordem": 20,
            "usuario_possui_salvo": True,
        },
        {
            "tc_caderno_id": 96081470,
            "caderno_base_id": 87000002,
            "nome": "Direito Internacional - OAB 2026 - 46º Exame",
            "total_questoes": 76,
            "total_capitulos": 4,
            "ordem": 11,
            "usuario_possui_salvo": True,
        },
    ],
}
SAVE = {"pasta_id": 7024498, "itens": []}
ENQUEUE = {"job_id": 1, "status": "pending", "total_units": 1, "enqueued_units": 1}


@pytest.mark.asyncio
async def test_importar_guia_persiste_e_enfileira(client, db_session, monkeypatch):
    calls = _fake_scraper(monkeypatch, resolve=RESOLVE, save=SAVE, enqueue=ENQUEUE)

    r = await client.post(
        "/api/q/guias/importar",
        json={"url": "https://www.tecconcursos.com.br/guias/oab-2026"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["tc_guia_id"] == 6818
    assert body["banca"] == "FGV"
    assert body["cadernos"] == 2
    assert body["enqueued"] == 2
    assert body["tc_pasta_id"] == 7024498
    assert body["status"] == "collecting"

    # Resolver + salvar + 2 enqueues
    assert any(c["url"].endswith("/guia/resolver") for c in calls)
    assert any(c["url"].endswith("/guia/salvar-cadernos") for c in calls)
    assert sum(1 for c in calls if c["url"].endswith("/enqueue/caderno")) == 2

    # Persistência
    guia_count = (await db_session.execute(text("SELECT COUNT(*) FROM guias"))).scalar()
    cad_count = (await db_session.execute(text("SELECT COUNT(*) FROM guia_cadernos"))).scalar()
    assert guia_count == 1
    assert cad_count == 2


@pytest.mark.asyncio
async def test_importar_guia_idempotente(client, db_session, monkeypatch):
    _fake_scraper(monkeypatch, resolve=RESOLVE, save=SAVE, enqueue=ENQUEUE)

    await client.post("/api/q/guias/importar", json={"url": "x", "iniciar_coleta": False})
    await client.post("/api/q/guias/importar", json={"url": "x", "iniciar_coleta": False})

    guia_count = (await db_session.execute(text("SELECT COUNT(*) FROM guias"))).scalar()
    cad_count = (await db_session.execute(text("SELECT COUNT(*) FROM guia_cadernos"))).scalar()
    assert guia_count == 1  # não duplica
    assert cad_count == 2


@pytest.mark.asyncio
async def test_listar_e_detalhe_guia(client, monkeypatch):
    _fake_scraper(monkeypatch, resolve=RESOLVE, save=SAVE, enqueue=ENQUEUE)
    imp = (
        await client.post(
            "/api/q/guias/importar", json={"url": "x", "iniciar_coleta": False}
        )
    ).json()
    guia_id = imp["id"]

    lst = (await client.get("/api/q/guias")).json()
    assert len(lst["guias"]) == 1
    assert lst["guias"][0]["cadernos_total"] == 2
    assert lst["guias"][0]["questoes_esperadas"] == 139  # 63 + 76

    det = (await client.get(f"/api/q/guias/{guia_id}")).json()
    assert len(det["cadernos"]) == 2
    # ordena por ordem: Internacional (11) antes de Filosofia (20)
    assert det["cadernos"][0]["tc_caderno_id"] == 96081470
    assert all(c["status"] == "pending" for c in det["cadernos"])


@pytest.mark.asyncio
async def test_importar_guia_fresco_usa_itens_da_pasta(client, db_session, monkeypatch):
    """Guia que o usuário ainda não salvou: listar-pelo-guia vem sem ids; a fonte
    dos cadernos é a pasta criada por 'salvar todos'."""
    resolve_sem_ids = {
        "tc_guia_id": 7000,
        "slug": "oab-2025/x",
        "url": "u",
        "nome": "Guia OAB 2025",
        "banca": "FGV",
        "cadernos": [
            # capítulos/ordem por nome, sem tc_caderno_id (não salvo ainda)
            {
                "tc_caderno_id": None,
                "nome": "Direito Penal - OAB 2025",
                "total_questoes": 0,
                "total_capitulos": 99,
                "ordem": 5,
                "usuario_possui_salvo": False,
            },
        ],
    }
    save_com_itens = {
        "pasta_id": 555,
        "itens": [
            {"id": 88000001, "nome": "Direito Penal - OAB 2025", "quantidadeItens": 1700, "cadernoGuia": True},
            {"id": 88000002, "nome": "Ética - OAB 2025", "quantidadeItens": 410, "cadernoGuia": True},
        ],
    }
    _fake_scraper(monkeypatch, resolve=resolve_sem_ids, save=save_com_itens, enqueue=ENQUEUE)

    r = await client.post("/api/q/guias/importar", json={"url": "x", "iniciar_coleta": False})
    assert r.status_code == 202
    assert r.json()["cadernos"] == 2

    rows = (
        await db_session.execute(
            text("SELECT tc_caderno_id, nome, total_questoes, total_capitulos FROM guia_cadernos ORDER BY tc_caderno_id")
        )
    ).all()
    assert (88000001, "Direito Penal - OAB 2025", 1700, 99) == tuple(rows[0])
    assert (88000002, "Ética - OAB 2025", 410, 0) == tuple(rows[1])


@pytest.mark.asyncio
async def test_materializar_sem_coleta_nao_cria_caderno(client, monkeypatch):
    _fake_scraper(monkeypatch, resolve=RESOLVE, save=SAVE, enqueue=ENQUEUE)
    imp = (
        await client.post(
            "/api/q/guias/importar", json={"url": "x", "iniciar_coleta": False}
        )
    ).json()

    r = await client.post(f"/api/q/guias/{imp['id']}/materializar")
    assert r.status_code == 200
    assert r.json()["total"] == 0  # sem membership coletada, nada a materializar
