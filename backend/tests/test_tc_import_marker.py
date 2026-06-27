import pytest
from sqlalchemy import select
from models import Questao, QuestaoTcImport


@pytest.mark.asyncio
async def test_marcador_unico_por_questao_quadro(db_session):
    # Seed uma questão para satisfazer a FK
    db_session.add(Questao(id=1, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>Q</p>",
                            gabarito="A", status="ATIVA"))
    await db_session.commit()

    db_session.add(QuestaoTcImport(questao_id=1, quadro="alunos", count=3))
    await db_session.commit()
    row = (await db_session.execute(
        select(QuestaoTcImport).where(
            QuestaoTcImport.questao_id == 1, QuestaoTcImport.quadro == "alunos")
    )).scalar_one()
    assert row.count == 3 and row.fetched_at is not None
