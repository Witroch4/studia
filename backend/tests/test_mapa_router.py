"""Mapa da Aprovação — extração: enfileira, faz polling, idempotência."""
import pytest
from sqlalchemy import select

from models import EditalExtracao, TcConcurso, TcConcursoArquivo
from tests.conftest import make_user

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
