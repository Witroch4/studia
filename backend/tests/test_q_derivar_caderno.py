"""Deriva cadernos a partir das resoluções do usuário (resolvidas/acertadas/erradas)."""

import pytest

from models import CadernoQuestoes, Questao

pytestmark = pytest.mark.asyncio


async def _seed(db_session):
    db_session.add(CadernoQuestoes(id=10, nome="Caderno Base", owner_uid="admin-1", pasta="Estudos", question_ids=[99, 100, 101], total=3))
    db_session.add(Questao(id=99, id_externo=1, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q1</p>", gabarito="A", status="ATIVA"))
    db_session.add(Questao(id=100, id_externo=2, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q2</p>", gabarito="B", status="ATIVA"))
    db_session.add(Questao(id=101, id_externo=3, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q3</p>", gabarito="A", status="ATIVA"))
    await db_session.commit()


async def _responder(client, qid, resposta):
    r = await client.post(f"/api/q/{qid}/responder", json={"resposta": resposta, "caderno_id": 10})
    assert r.status_code == 200, r.text
    return r.json()


async def test_derivar_separa_acertadas_erradas_resolvidas(client, db_session):
    await _seed(db_session)
    assert (await _responder(client, 99, "A"))["acertou"] is True   # acerto
    assert (await _responder(client, 100, "A"))["acertou"] is False  # erro (gab B)
    assert (await _responder(client, 101, "A"))["acertou"] is True   # acerto

    # erradas → só a 100
    r = await client.post("/api/q/cadernos/10/derivar", json={"tipo": "erradas", "nome": "Minhas erradas"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    novo = await db_session.get(CadernoQuestoes, body["id"])
    assert novo.question_ids == [100]
    assert novo.owner_uid == "admin-1"
    assert novo.pasta == "Estudos"  # herda a pasta da origem
    assert novo.nome == "Minhas erradas"

    # acertadas → 99 e 101, na ordem original
    r = await client.post("/api/q/cadernos/10/derivar", json={"tipo": "acertadas"})
    assert r.status_code == 200
    novo = await db_session.get(CadernoQuestoes, r.json()["id"])
    assert novo.question_ids == [99, 101]
    assert novo.nome == "Acertadas — Caderno Base"  # nome automático

    # resolvidas → as três
    r = await client.post("/api/q/cadernos/10/derivar", json={"tipo": "resolvidas"})
    assert r.json()["total"] == 3


async def test_derivar_categoria_vazia_retorna_400(client, db_session):
    await _seed(db_session)
    await _responder(client, 99, "A")  # só acertos, nenhuma errada
    r = await client.post("/api/q/cadernos/10/derivar", json={"tipo": "erradas"})
    assert r.status_code == 400


async def test_derivar_tipo_invalido_422(client, db_session):
    await _seed(db_session)
    r = await client.post("/api/q/cadernos/10/derivar", json={"tipo": "xpto"})
    assert r.status_code == 422
