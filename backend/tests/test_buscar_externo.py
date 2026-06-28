"""Busca de questão por id_externo (ID do TC) + gerar caderno de 1 questão."""
import pytest
from models import Questao, Banca, Materia, CadernoQuestoes
from tests.conftest import ADMIN_USER


@pytest.mark.asyncio
async def test_buscar_externo_lista_cadernos_e_dados(db_session, client):
    db_session.add(Banca(id=1, sigla="IDECAN", nome="IDECAN", slug="idecan"))
    db_session.add(Materia(id=1, nome="Engenharia Civil"))
    db_session.add(Questao(
        id=500, id_externo=3412517, status="ANULADA",
        gabarito="ANULADA_MULTIPLA_ESCOLHA", tipo="MULTIPLA_ESCOLHA",
        enunciado_md="Um ensaio de granulometria forneceu os seguintes dados...",
        banca_id=1, materia_id=1,
    ))
    db_session.add(CadernoQuestoes(
        id=900, owner_uid=ADMIN_USER.id, nome="Meu Caderno",
        question_ids=[500, 1, 2], total=3,
    ))
    await db_session.commit()

    r = (await client.get("/api/q/questoes/buscar-externo/3412517")).json()
    assert r["found"] is True
    assert r["questao"]["status"] == "ANULADA"
    assert r["questao"]["banca"] == "IDECAN"
    assert r["questao"]["materia"] == "Engenharia Civil"
    assert r["questao"]["preview"].startswith("Um ensaio")
    assert any(c["id"] == 900 for c in r["cadernos"])

    # não encontrada
    assert (await client.get("/api/q/questoes/buscar-externo/99999999")).json()["found"] is False


@pytest.mark.asyncio
async def test_buscar_por_nosso_id(db_session, client):
    db_session.add(Questao(id=482, id_externo=3412517, status="ATIVA", gabarito="A"))
    await db_session.commit()
    # busca pelo NOSSO id (482), não pelo do TC
    r = (await client.get("/api/q/questoes/buscar-externo/482")).json()
    assert r["found"] is True
    assert r["questao"]["id"] == 482
    assert r["questao"]["id_externo"] == 3412517


@pytest.mark.asyncio
async def test_colisao_prioriza_id_externo(db_session, client):
    # número 777 bate id_externo de A e id de B → deve retornar A
    db_session.add(Questao(id=500, id_externo=777, status="ATIVA", gabarito="A"))
    db_session.add(Questao(id=777, id_externo=999, status="ATIVA", gabarito="B"))
    await db_session.commit()
    r = (await client.get("/api/q/questoes/buscar-externo/777")).json()
    assert r["found"] is True
    assert r["questao"]["id"] == 500
    assert r["questao"]["id_externo"] == 777


@pytest.mark.asyncio
async def test_gerar_caderno_por_question_ids(db_session, client):
    db_session.add(Questao(id=777, id_externo=111, status="ATIVA", gabarito="A"))
    await db_session.commit()
    r = await client.post("/api/q/cadernos", json={"nome": "Só essa", "question_ids": [777]})
    assert r.status_code == 200
    j = r.json()
    assert j["total"] == 1 and j["primeira_questao_id"] == 777
