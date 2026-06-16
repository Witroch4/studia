from datetime import date

import pytest
from sqlalchemy import select

from models import CadernoQuestoes, Cronograma, CronogramaDiscursiva, CronogramaSimulado


@pytest.mark.asyncio
async def test_cria_cronograma_com_filhos(db_session):
    # CadernoQuestoes necessário para satisfazer a FK de cronogramas.caderno_id
    caderno = CadernoQuestoes(
        nome="Caderno Teste", owner_uid="user-A", question_ids=[], total=0
    )
    db_session.add(caderno)
    await db_session.flush()

    cron = Cronograma(
        usuario_uid="user-A", caderno_id=caderno.id,
        data_inicio=date(2026, 6, 1), data_prova=date(2026, 8, 16),
        dias_folga=[6], buffer_dias=21,
        incluir_revisao=True, incluir_discursivas=True, incluir_simulados=True,
        discursivas_por_semana=2,
    )
    db_session.add(cron)
    await db_session.flush()
    assert cron.id is not None

    db_session.add(CronogramaDiscursiva(
        cronograma_id=cron.id, data=date(2026, 6, 2), tema="Tema X",
        tipo="Treino 20 linhas", qtd=1, status="Pendente", reescrita=False,
    ))
    db_session.add(CronogramaSimulado(
        cronograma_id=cron.id, data=date(2026, 6, 28), tipo="Simulado parcial",
        objetivas_planejadas=70, meta_objetiva=95, discursiva_planejada=1,
    ))
    await db_session.flush()

    discs = (await db_session.execute(
        select(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == cron.id)
    )).scalars().all()
    assert len(discs) == 1
    assert discs[0].status == "Pendente"
