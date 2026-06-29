from __future__ import annotations

import pytest

from models import CadernoQuestoes, Questao, QuestaoFavorita, Resolucao
from tests.conftest import USER_B

pytestmark = pytest.mark.asyncio


async def test_detalhe_questao_inclui_estado_do_usuario(client, db_session):
    db_session.add(Questao(id=701, id_externo=900701, enunciado_md="Q", gabarito="A"))
    db_session.add(
        CadernoQuestoes(
            id=70,
            nome="Meu caderno",
            owner_uid="admin-1",
            pasta="OAB",
            question_ids=[701],
            total=1,
        )
    )
    db_session.add(QuestaoFavorita(owner_uid="admin-1", questao_id=701))
    db_session.add(
        Resolucao(
            usuario_uid="admin-1",
            questao_id=701,
            caderno_id=None,
            resposta="B",
            acertou=False,
            tempo_segundos=12,
        )
    )
    await db_session.commit()

    response = await client.get("/api/q/701")

    assert response.status_code == 200
    body = response.json()
    assert body["favorita"] is True
    assert body["minha_resolucao"] == {"resposta": "B", "acertou": False}
    assert body["cadernos"] == [{"id": 70, "nome": "Meu caderno", "pasta": "OAB"}]


async def test_detalhe_questao_publico_nao_expoe_estado_de_usuario(client, db_session, auth_state):
    db_session.add(Questao(id=702, id_externo=900702, enunciado_md="Q", gabarito="A"))
    db_session.add(QuestaoFavorita(owner_uid="admin-1", questao_id=702))
    db_session.add(
        Resolucao(
            usuario_uid="admin-1",
            questao_id=702,
            caderno_id=None,
            resposta="A",
            acertou=True,
        )
    )
    await db_session.commit()
    auth_state["user"] = None

    response = await client.get("/api/q/702")

    assert response.status_code == 200
    body = response.json()
    assert body["favorita"] is False
    assert body["minha_resolucao"] is None
    assert body["cadernos"] == []


async def test_adicionar_questao_a_caderno_existente_e_idempotente(client, db_session):
    db_session.add_all(
        [
            Questao(id=801, id_externo=900801, enunciado_md="Q801", gabarito="A"),
            CadernoQuestoes(
                id=80,
                nome="Caderno alvo",
                owner_uid="admin-1",
                question_ids=[800],
                total=1,
            ),
        ]
    )
    await db_session.commit()

    response = await client.post("/api/q/cadernos/80/questoes/801")

    assert response.status_code == 200
    assert response.json() == {
        "id": 80,
        "questao_id": 801,
        "adicionada": True,
        "total": 2,
        "redirect": "/q/caderno/80",
    }
    caderno = await db_session.get(CadernoQuestoes, 80)
    assert caderno is not None
    await db_session.refresh(caderno)
    assert caderno.question_ids == [800, 801]
    assert caderno.total == 2

    response = await client.post("/api/q/cadernos/80/questoes/801")

    assert response.status_code == 200
    assert response.json()["adicionada"] is False
    await db_session.refresh(caderno)
    assert caderno.question_ids == [800, 801]
    assert caderno.total == 2


async def test_adicionar_questao_exige_caderno_do_usuario(client, db_session, auth_state):
    db_session.add_all(
        [
            Questao(id=802, id_externo=900802, enunciado_md="Q802", gabarito="A"),
            CadernoQuestoes(
                id=81,
                nome="Caderno de outro usuario",
                owner_uid="admin-1",
                question_ids=[],
                total=0,
            ),
        ]
    )
    await db_session.commit()
    auth_state["user"] = USER_B

    response = await client.post("/api/q/cadernos/81/questoes/802")

    assert response.status_code == 404
