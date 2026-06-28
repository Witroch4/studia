"""Questão ANULADA não pode ser respondida: não grava Resolucao nem pontua."""
import pytest
from sqlalchemy import select, func
from models import Questao, Alternativa, Resolucao


@pytest.mark.asyncio
async def test_responder_anulada_nao_grava_nem_pontua(db_session, client):
    db_session.add(Questao(
        id=600, id_externo=1, status="ANULADA",
        gabarito="ANULADA_MULTIPLA_ESCOLHA", tipo="MULTIPLA_ESCOLHA",
    ))
    await db_session.commit()

    r = (await client.post("/api/q/600/responder", json={"resposta": "A"})).json()
    assert r["anulada"] is True
    assert r["acertou"] is None

    # Não gravou Resolucao → não conta na estatística nem no limite.
    n = (await db_session.execute(
        select(func.count()).where(Resolucao.questao_id == 600)
    )).scalar_one()
    assert n == 0


@pytest.mark.asyncio
async def test_responder_normal_continua_pontuando(db_session, client):
    db_session.add(Questao(id=601, id_externo=2, status="ATIVA", gabarito="A", tipo="MULTIPLA_ESCOLHA"))
    db_session.add(Alternativa(id=9001, questao_id=601, letra="A", texto_md="certa", correta=True, ordem=0))
    db_session.add(Alternativa(id=9002, questao_id=601, letra="B", texto_md="errada", correta=False, ordem=1))
    await db_session.commit()

    r = (await client.post("/api/q/601/responder", json={"resposta": "A"})).json()
    assert r.get("anulada") is not True
    assert r["acertou"] is True
    n = (await db_session.execute(
        select(func.count()).where(Resolucao.questao_id == 601)
    )).scalar_one()
    assert n == 1
