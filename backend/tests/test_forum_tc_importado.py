import pytest
from models import Questao, QuestaoTcImport

pytestmark = pytest.mark.asyncio


async def test_forum_expoe_flag_tc_importado(db_session, client):
    db_session.add(
        Questao(
            id=20,
            id_externo=20,
            tipo="MULTIPLA_ESCOLHA",
            enunciado_html="<p>x</p>",
            gabarito="A",
            status="ATIVA",
        )
    )
    await db_session.commit()

    r = await client.get("/api/q/questoes/20/forum?quadro=alunos")
    assert r.status_code == 200
    assert r.json()["tc_importado"] is False

    db_session.add(QuestaoTcImport(questao_id=20, quadro="alunos", count=0))
    await db_session.commit()

    r2 = await client.get("/api/q/questoes/20/forum?quadro=alunos")
    assert r2.status_code == 200
    assert r2.json()["tc_importado"] is True
