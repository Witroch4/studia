"""Regressão: responder a mesma questão no mesmo caderno é idempotente.

Bug original: voltar à questão (ou cliques-fantasma) gravava Resolucao duplicada,
inflando estatísticas e o total diário. O 2º POST não pode criar linha nova.
"""

import pytest
from sqlalchemy import func, select

from models import CadernoQuestoes, Questao, Resolucao

pytestmark = pytest.mark.asyncio


async def _seed(db_session):
    # owner = admin-1 (usuário default do conftest) p/ passar no controle de acesso.
    db_session.add(CadernoQuestoes(id=10, nome="Caderno", owner_uid="admin-1", question_ids=[99], total=1))
    db_session.add(
        Questao(
            id=99,
            id_externo=3966994,
            tipo="MULTIPLA_ESCOLHA",
            enunciado_html="<p>Enunciado</p>",
            gabarito="A",
            status="ATIVA",
        )
    )
    await db_session.commit()


async def _conta_resolucoes(db_session, questao_id: int) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(Resolucao).where(Resolucao.questao_id == questao_id)
        )
    ).scalar_one()


async def test_responder_duas_vezes_nao_duplica_resolucao(client, db_session):
    await _seed(db_session)

    r1 = await client.post("/api/q/99/responder", json={"resposta": "A", "caderno_id": 10})
    assert r1.status_code == 200
    assert r1.json()["acertou"] is True
    assert await _conta_resolucoes(db_session, 99) == 1

    # 2ª resposta (mesma questão/caderno), inclusive trocando a alternativa:
    # deve devolver o resultado original e NÃO gravar nova resolução.
    r2 = await client.post("/api/q/99/responder", json={"resposta": "B", "caderno_id": 10})
    assert r2.status_code == 200
    body = r2.json()
    assert body["ja_resolvida"] is True
    assert body["acertou"] is True  # mantém o gabarito da 1ª resposta
    assert await _conta_resolucoes(db_session, 99) == 1


async def test_minhas_resolucoes_lista_o_que_respondi(client, db_session):
    await _seed(db_session)
    await client.post("/api/q/99/responder", json={"resposta": "A", "caderno_id": 10})

    resp = await client.get("/api/q/cadernos/10/minhas-resolucoes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolucoes"]["99"] == {"resposta": "A", "acertou": True}
