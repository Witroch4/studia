"""Mapa da Aprovação — extração: enfileira, faz polling, idempotência."""
import pytest
from sqlalchemy import select

from models import EditalExtracao, TcConcurso, TcConcursoArquivo
from tests.conftest import make_user
from models import Banca, CadernoQuestoes, MapaAprovacao, MapaItem, Materia, Prova, Questao

pytestmark = pytest.mark.asyncio

DADOS_OK = {
    "concurso": {"data_prova": "2026-09-20"},
    "eventos": [{"titulo": "Prova", "data_inicio": "2026-09-20", "tipo": "prova"}],
    "cargos": [{"nome": "Engenheiro Civil",
                "conteudo_programatico": [
                    {"materia": "Língua Portuguesa", "assuntos": ["Crase", "Concordância"]},
                ]}],
}


async def seed_concurso(db, *, com_edital=True) -> TcConcurso:
    c = TcConcurso(concurso_id_externo=99, nome_completo="Prefeitura X — 2026",
                   url_concurso="x", banca_nome="IDECAN — Instituto de Desenvolvimento",
                   orgao_sigla="PMX", ano=2026)
    db.add(c)
    await db.flush()
    if com_edital:
        db.add(TcConcursoArquivo(concurso_id=c.id, tipo="EDITAL", arquivo_id_externo=1,
                                 uuid="u", nome_arquivo="e.pdf", minio_object_key="k"))
    await db.commit()
    return c


@pytest.fixture(autouse=True)
def _sem_fila(monkeypatch):
    """Extração não vai pro NATS em teste: kiq vira no-op registrando chamadas."""
    import mapa_router

    chamadas: list[tuple] = []

    class FakeTask:
        async def kiq(self, *a, **kw):
            chamadas.append(a)

    monkeypatch.setattr(mapa_router, "extrair_edital_task", FakeTask())
    return chamadas


async def test_extrair_cria_registro_e_enfileira(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 202
    assert r.json()["status"] == "pendente"
    assert len(_sem_fila) == 1
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "pendente"


async def test_extrair_concluido_nao_reenfileira(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 202
    assert r.json()["status"] == "concluido"
    assert _sem_fila == []


async def test_extrair_sem_edital_409(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session, com_edital=False)
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 409


async def test_extrair_concurso_inexistente_404(client, auth_state, _sem_fila):
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": 999999})
    assert r.status_code == 404
    assert _sem_fila == []


async def test_extrair_processando_nao_reenfileira(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="processando"))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 202
    assert r.json()["status"] == "processando"
    assert _sem_fila == []


async def test_extrair_erro_reseta_e_reenfileira(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="erro", erro_msg="x"))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 202
    assert r.json()["status"] == "pendente"
    assert len(_sem_fila) == 1
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "pendente"
    assert ext.erro_msg is None


async def test_polling_extracao(client, db_session, auth_state):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.get(f"/api/q/mapas/extracao/{c.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "concluido"
    assert body["dados"]["cargos"][0]["nome"] == "Engenheiro Civil"


async def _seed_banco_questoes(db) -> None:
    """Banca IDECAN + matéria Português + 4 questões (2 anuladas, uma por filtro)."""
    banca = Banca(nome="Instituto de Desenvolvimento — IDECAN", slug="idecan", sigla="IDECAN")
    mat = Materia(nome="Português")
    db.add_all([banca, mat])
    await db.flush()
    prova = Prova(banca_id=banca.id, ano=2024)
    db.add(prova)
    await db.flush()
    db.add_all([
        Questao(banca_id=banca.id, materia_id=mat.id, prova_id=prova.id, gabarito="A"),
        Questao(banca_id=banca.id, materia_id=mat.id, prova_id=prova.id, gabarito="B"),
        # Anulada SÓ pelo status (gabarito normal) — cobre o filtro de status.
        Questao(banca_id=banca.id, materia_id=mat.id, prova_id=prova.id,
                status="ANULADA", gabarito="C"),
        # Anulada SÓ pelo gabarito (status None) — cobre o filtro de gabarito.
        Questao(banca_id=banca.id, materia_id=mat.id, prova_id=prova.id,
                gabarito="ANULADA"),
    ])
    await db.commit()


@pytest.fixture
def _pro(monkeypatch):
    import mapa_router
    async def _sim(db, uid):
        return True
    monkeypatch.setattr(mapa_router, "acesso_pro_ativo", _sim)


@pytest.fixture
def _match_ia(monkeypatch):
    import mapa_service
    def _fake(materias_edital, materias_banco, modelo):
        return {"Língua Portuguesa": "Português"}
    monkeypatch.setattr(mapa_service, "mapear_materias", _fake)


async def test_criar_mapa_completo(client, db_session, auth_state, _pro, _match_ia):
    c = await seed_concurso(db_session)
    await _seed_banco_questoes(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")

    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cadernos_criados"] == 1
    assert body["total_questoes"] == 2  # 2 válidas de 4 (anuladas por status E por gabarito fora)

    mapa = (await db_session.execute(select(MapaAprovacao))).scalar_one()
    assert mapa.cargo_nome == "Engenheiro Civil"
    itens = (await db_session.execute(
        select(MapaItem).where(MapaItem.mapa_id == mapa.id).order_by(MapaItem.ordem)
    )).scalars().all()
    assert [i.assunto_texto for i in itens] == ["Crase", "Concordância"]
    assert all(i.caderno_id is not None for i in itens)  # matéria com match ganhou caderno
    cad = (await db_session.execute(select(CadernoQuestoes))).scalar_one()
    assert cad.owner_uid == "u1"
    assert len(cad.question_ids) == 2


async def test_criar_mapa_sem_pro_403(client, db_session, auth_state, _match_ia, monkeypatch):
    import mapa_router

    async def _nao_pro(db, uid):
        return False

    # Não usar o acesso_pro_ativo real: tabelas de billing podem não existir
    # no banco de teste — o contrato aqui é só "sem PRO → 403".
    monkeypatch.setattr(mapa_router, "acesso_pro_ativo", _nao_pro)
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 403


async def test_criar_mapa_cargo_inexistente_404(client, db_session, auth_state, _pro):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Fiscal"})
    assert r.status_code == 404


async def test_criar_mapa_duplicado_409(client, db_session, auth_state, _pro, _match_ia):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r1 = await client.post("/api/q/mapas", json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r1.status_code == 200, r1.text
    mapa_id = r1.json()["id"]
    r = await client.post("/api/q/mapas", json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["id"] == mapa_id  # detail estruturado: wizard usa o id programaticamente


async def test_criar_mapa_ia_match_fora_nao_quebra(client, db_session, auth_state, _pro, monkeypatch):
    """IA de match indisponível → mapa nasce sem cadernos, sem 500."""
    import mapa_service
    chamadas: list[tuple] = []
    def _boom(a, b, m):
        chamadas.append((a, b, m))
        raise RuntimeError("proxy fora")
    monkeypatch.setattr(mapa_service, "mapear_materias", _boom)
    c = await seed_concurso(db_session)
    # COM matérias no banco: o guard `materias_edital and materias_banco` passa
    # e o _boom dispara de verdade — cobre o except do montar_mapa.
    await _seed_banco_questoes(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 200
    assert r.json()["cadernos_criados"] == 0
    assert chamadas, "mapear_materias deveria ter sido chamado (e falhado)"

    # Mapa nasce íntegro: itens criados, só sem caderno/matéria vinculados.
    mapa = (await db_session.execute(select(MapaAprovacao))).scalar_one()
    itens = (await db_session.execute(
        select(MapaItem).where(MapaItem.mapa_id == mapa.id).order_by(MapaItem.ordem)
    )).scalars().all()
    assert [i.assunto_texto for i in itens] == ["Crase", "Concordância"]
    assert all(i.caderno_id is None for i in itens)
    assert (await db_session.execute(select(CadernoQuestoes))).scalars().all() == []


# --- Task 9: CRUD do Mapa (lista, detalhe, checklist, delete, reextrair) -----

async def _criar_mapa_via_api(client, db_session, auth_state):
    c = await seed_concurso(db_session)
    await _seed_banco_questoes(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    return r.json()["id"], c


async def test_listar_meus_mapas(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, c = await _criar_mapa_via_api(client, db_session, auth_state)
    r = await client.get("/api/q/mapas")
    assert r.status_code == 200
    m = r.json()["mapas"][0]
    assert m["id"] == mapa_id
    assert m["data_prova"] == "2026-09-20"
    assert m["total_itens"] == 2
    assert m["caderno_ids"]


async def test_detalhe_verticalizacao(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    r = await client.get(f"/api/q/mapas/{mapa_id}")
    body = r.json()
    assert body["eventos"][0]["tipo"] == "prova"
    v = body["verticalizacao"]
    assert v[0]["materia_nome"] == "Língua Portuguesa"
    assert [i["assunto_texto"] for i in v[0]["itens"]] == ["Crase", "Concordância"]


async def test_detalhe_de_outro_usuario_404(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    auth_state["user"] = make_user("u2")
    r = await client.get(f"/api/q/mapas/{mapa_id}")
    assert r.status_code == 404


async def test_patch_item_status(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    det = (await client.get(f"/api/q/mapas/{mapa_id}")).json()
    item_id = det["verticalizacao"][0]["itens"][0]["id"]
    r = await client.patch(f"/api/q/mapas/{mapa_id}/itens/{item_id}",
                           json={"status": "dominado"})
    assert r.status_code == 200
    r2 = await client.patch(f"/api/q/mapas/{mapa_id}/itens/{item_id}",
                            json={"status": "qualquer"})
    assert r2.status_code in (400, 422)


async def test_delete_mapa_preserva_cadernos(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    r = await client.delete(f"/api/q/mapas/{mapa_id}")
    assert r.status_code == 200
    assert (await db_session.execute(select(MapaAprovacao))).scalar_one_or_none() is None
    assert (await db_session.execute(select(CadernoQuestoes))).scalar_one() is not None


async def test_reextrair_admin(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido",
                                  dados=DADOS_OK, prompt_versao=1))
    await db_session.commit()
    auth_state["user"] = make_user("adm", role="admin")
    r = await client.post(f"/api/q/mapas/extracao/{c.id}/reextrair")
    assert r.status_code == 202
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "pendente" and ext.prompt_versao == 2
    assert len(_sem_fila) == 1

    auth_state["user"] = make_user("u1")  # não-admin
    assert (await client.post(f"/api/q/mapas/extracao/{c.id}/reextrair")).status_code == 403
