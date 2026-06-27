from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import guia_service
from models import GuiaFila


@pytest.mark.asyncio
async def test_enfileirar_urls_cria_entradas_queued_e_dedup(db_session):
    entries = await guia_service.enfileirar_urls(
        db_session, ["a", "a", "  ", "b"], requested_by="admin-1"
    )
    await db_session.commit()
    assert [e.url for e in entries] == ["a", "b"]  # trim + dedup intra-lote
    assert all(e.status == "queued" for e in entries)
    rows = (await db_session.execute(select(GuiaFila))).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_enfileirar_urls_ignora_url_ja_ativa(db_session):
    await guia_service.enfileirar_urls(db_session, ["a"], requested_by=None)
    await db_session.commit()
    again = await guia_service.enfileirar_urls(db_session, ["a", "c"], requested_by=None)
    await db_session.commit()
    assert [e.url for e in again] == ["c"]  # "a" já estava na fila


@pytest.mark.asyncio
async def test_cooldown_zero_sem_finalizados(db_session):
    seg = await guia_service.proximo_cooldown_segundos(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), cooldown_s=900
    )
    assert seg == 0


@pytest.mark.asyncio
async def test_cooldown_conta_do_ultimo_finalizado(db_session):
    fim = datetime(2026, 1, 1, 12, 0, 0)
    db_session.add(GuiaFila(url="a", status="done", finalizado_em=fim))
    await db_session.flush()
    # 300s depois → faltam 600s do cooldown de 900s
    seg = await guia_service.proximo_cooldown_segundos(
        db_session, agora=fim + timedelta(seconds=300), cooldown_s=900
    )
    assert seg == 600


@pytest.mark.asyncio
async def test_remover_e_pular(db_session):
    [e] = await guia_service.enfileirar_urls(db_session, ["a"], requested_by=None)
    await db_session.flush()
    assert await guia_service.remover_da_fila(db_session, e.id) is True
    [e2] = await guia_service.enfileirar_urls(db_session, ["b"], requested_by=None)
    e2.status = "collecting"
    await db_session.flush()
    agora = datetime(2026, 1, 1, 12, 0, 0)
    assert await guia_service.pular_fila(db_session, e2.id, agora=agora) is True
    await db_session.refresh(e2)
    assert e2.status == "skipped" and e2.finalizado_em == agora
