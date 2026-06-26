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
async def test_renomear_guia(client, db_session, monkeypatch):
    _fake_scraper(monkeypatch, resolve=RESOLVE, save=SAVE, enqueue=ENQUEUE)
    imp = (
        await client.post(
            "/api/q/guias/importar", json={"url": "x", "iniciar_coleta": False}
        )
    ).json()
    guia_id = imp["id"]

    r = await client.patch(f"/api/q/guias/{guia_id}", json={"nome": "  Novo Nome  "})
    assert r.status_code == 200
    assert r.json()["nome"] == "Novo Nome"

    det = (await client.get(f"/api/q/guias/{guia_id}")).json()
    assert det["nome"] == "Novo Nome"

    # nome vazio → 422
    r = await client.patch(f"/api/q/guias/{guia_id}", json={"nome": "   "})
    assert r.status_code == 422

    # guia inexistente → 404
    r = await client.patch("/api/q/guias/999999", json={"nome": "X"})
    assert r.status_code == 404


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


# ─── Guia Builder manual + Pastas de usuários + PRO only ──────────


def _u(uid: str, role: str = "user"):
    from auth import CurrentUser

    return CurrentUser(id=uid, email=f"{uid}@t", name=uid, role=role, banned=False)


async def _cadernos(db_session, specs: list[dict]):
    """Cria CadernoQuestoes e devolve a lista (com ids preenchidos)."""
    from models import CadernoQuestoes

    objs = [CadernoQuestoes(**s) for s in specs]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest.mark.asyncio
async def test_criar_guia_manual_referencia_e_ordem(client, db_session, auth_state):
    cads = await _cadernos(
        db_session,
        [
            {"nome": "Civil", "owner_uid": "user-A", "pasta": "P1", "question_ids": [1, 2], "total": 2},
            {"nome": "Penal", "owner_uid": "user-B", "pasta": "P2", "question_ids": [3], "total": 1},
        ],
    )
    civil, penal = cads[0].id, cads[1].id

    # ordem invertida de propósito: Penal antes de Civil
    r = await client.post(
        "/api/q/guias/manual",
        json={"nome": "Meu Guia", "banca": "FGV", "caderno_ids": [penal, civil]},
    )
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    assert r.json()["cadernos"] == 2
    assert r.json()["pro_only"] is False

    det = (await client.get(f"/api/q/guias/{gid}")).json()
    assert det["pct"] == 100.0
    assert det["questoes_coletadas"] == det["questoes_esperadas"] == 3
    assert [c["nome"] for c in det["cadernos"]] == ["Penal", "Civil"]  # ordem preservada
    assert all(c["caderno_id"] for c in det["cadernos"])
    assert all(c["status"] == "materialized" for c in det["cadernos"])

    # Aluno comum consegue estudar caderno de guia manual (não pro-only).
    auth_state["user"] = _u("user-Z")
    r = await client.get(f"/api/q/cadernos/{civil}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_criar_guia_manual_validacoes(client, db_session):
    # lista vazia → 422 (Pydantic min_length)
    r = await client.post("/api/q/guias/manual", json={"nome": "X", "caderno_ids": []})
    assert r.status_code == 422
    # caderno inexistente → 404
    r = await client.post("/api/q/guias/manual", json={"nome": "X", "caderno_ids": [999999]})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_usuarios_pastas_agrupa_por_dono(client, db_session):
    await _cadernos(
        db_session,
        [
            {"nome": "Cat", "owner_uid": None, "pasta": None, "question_ids": [1], "total": 1},
            {"nome": "A1", "owner_uid": "user-A", "pasta": "Importados", "question_ids": [2], "total": 1},
            {"nome": "B1", "owner_uid": "user-B", "pasta": "X", "question_ids": [3], "total": 1},
        ],
    )
    r = await client.get("/api/q/guias/usuarios-pastas")
    assert r.status_code == 200
    usuarios = r.json()["usuarios"]
    assert usuarios[0]["uid"] is None  # catálogo primeiro
    uids = {u["uid"] for u in usuarios}
    assert {"user-A", "user-B"} <= uids
    a = next(u for u in usuarios if u["uid"] == "user-A")
    assert a["total_cadernos"] == 1
    assert a["pastas"][0]["nome"] == "Importados"


@pytest.mark.asyncio
async def test_guia_pro_only_gate(client, db_session, auth_state):
    cad = (await _cadernos(
        db_session,
        [{"nome": "ProMat", "owner_uid": None, "pasta": None, "question_ids": [1], "total": 1}],
    ))[0]
    r = await client.post(
        "/api/q/guias/manual",
        json={"nome": "PRO Guia", "pro_only": True, "caderno_ids": [cad.id]},
    )
    assert r.status_code == 201
    gid = r.json()["id"]
    assert r.json()["pro_only"] is True

    # Não-PRO: caderno bloqueado (403) e não pode salvar o guia (403).
    auth_state["user"] = _u("user-free")
    assert (await client.get(f"/api/q/cadernos/{cad.id}")).status_code == 403
    assert (await client.post(f"/api/q/guias/{gid}/salvar")).status_code == 403
    det = (await client.get(f"/api/q/guias/{gid}")).json()
    assert det["bloqueado"] is True

    # Admin sempre acessa.
    auth_state["user"] = _u("admin-1", "admin")
    assert (await client.get(f"/api/q/cadernos/{cad.id}")).status_code == 200
    det = (await client.get(f"/api/q/guias/{gid}")).json()
    assert det["bloqueado"] is False


@pytest.mark.asyncio
async def test_patch_pro_only_toggle(client, db_session):
    cad = (await _cadernos(
        db_session,
        [{"nome": "M", "owner_uid": None, "pasta": None, "question_ids": [1], "total": 1}],
    ))[0]
    gid = (await client.post(
        "/api/q/guias/manual", json={"nome": "G", "caderno_ids": [cad.id]}
    )).json()["id"]

    r = await client.patch(f"/api/q/guias/{gid}", json={"pro_only": True})
    assert r.status_code == 200
    assert r.json()["pro_only"] is True
    r = await client.patch(f"/api/q/guias/{gid}", json={"pro_only": False, "nome": "G2"})
    assert r.json()["pro_only"] is False
    assert r.json()["nome"] == "G2"


@pytest.mark.asyncio
async def test_renomear_caderno_do_guia(client, db_session):
    """Admin renomeia um caderno do guia: muda o catálogo (GuiaCaderno.nome) e
    sincroniza o CadernoQuestoes materializado compartilhado."""
    cad = (await _cadernos(
        db_session,
        [{"nome": "Civil", "owner_uid": None, "pasta": None, "question_ids": [1], "total": 1}],
    ))[0]
    civil = cad.id
    gid = (await client.post(
        "/api/q/guias/manual", json={"nome": "G", "caderno_ids": [civil]}
    )).json()["id"]
    det = (await client.get(f"/api/q/guias/{gid}")).json()
    gc_id = det["cadernos"][0]["id"]

    # renomeia (com espaços, devem ser aparados)
    r = await client.patch(
        f"/api/q/guias/{gid}/cadernos/{gc_id}", json={"nome": "  Direito Civil  "}
    )
    assert r.status_code == 200, r.text
    assert r.json()["nome"] == "Direito Civil"

    # reflete no detalhe do guia (catálogo)
    det = (await client.get(f"/api/q/guias/{gid}")).json()
    assert det["cadernos"][0]["nome"] == "Direito Civil"

    # sincroniza o CadernoQuestoes materializado compartilhado
    nome_cad = (
        await db_session.execute(
            text("SELECT nome FROM cadernos_questoes WHERE id = :i"), {"i": civil}
        )
    ).scalar()
    assert nome_cad == "Direito Civil"

    # nome vazio → 422
    r = await client.patch(f"/api/q/guias/{gid}/cadernos/{gc_id}", json={"nome": "   "})
    assert r.status_code == 422

    # caderno do guia inexistente → 404
    r = await client.patch(f"/api/q/guias/{gid}/cadernos/999999", json={"nome": "X"})
    assert r.status_code == 404
