from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func as safunc
from sqlalchemy import select

import guia_service
from models import Guia, GuiaCaderno, GuiaFila


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


_RESOLVE = {
    "tc_guia_id": 7777,
    "slug": "x/y",
    "url": "https://www.tecconcursos.com.br/guias/x/y/-",
    "nome": "Guia X",
    "banca": "FGV",
    "cadernos": [
        {"tc_caderno_id": 111, "nome": "Mat A", "total_questoes": 10, "total_capitulos": 0, "ordem": 1},
    ],
}
_SAVE = {"pasta_id": 9001, "itens": [{"id": 111, "nome": "Mat A", "quantidadeItens": 10}]}


def _patch_scraper(monkeypatch):
    """Patcha guias_router.httpx (resolver_e_salvar usa _scraper_post de lá)."""
    from test_guias_router import _fake_scraper

    return _fake_scraper(
        monkeypatch, resolve=_RESOLVE, save=_SAVE,
        enqueue={"job_id": 1, "status": "pending", "total_units": 1, "enqueued_units": 1},
    )


@pytest.mark.asyncio
async def test_resolver_e_salvar_cria_guia_e_cadernos(db_session, monkeypatch):
    _patch_scraper(monkeypatch)
    guia, cadernos = await guia_service.resolver_e_salvar(
        db_session, url="x", relogin=False, page_size=200
    )
    await db_session.commit()
    assert guia.tc_guia_id == 7777
    assert len(cadernos) == 1
    n = (await db_session.execute(select(safunc.count()).select_from(GuiaCaderno))).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_guia_coleta_completa_sem_jobs_e_false(db_session, monkeypatch):
    _patch_scraper(monkeypatch)
    guia, _ = await guia_service.resolver_e_salvar(db_session, url="x", relogin=False, page_size=200)
    await db_session.commit()
    assert await guia_service.guia_coleta_completa(db_session, guia.id) is False


@pytest.mark.asyncio
async def test_enqueue_cadernos_do_guia(db_session, monkeypatch):
    calls = _patch_scraper(monkeypatch)
    guia, _ = await guia_service.resolver_e_salvar(db_session, url="x", relogin=False, page_size=200)
    await db_session.commit()
    enq, falhas = await guia_service.enqueue_cadernos_do_guia(db_session, guia.id, page_size=200)
    assert enq == 1 and falhas == []
    assert sum(1 for c in calls if c["url"].endswith("/enqueue/caderno")) == 1


# ─── Testes de endpoint (fila HTTP) ─────────────────────


@pytest.mark.asyncio
async def test_importar_lote_cria_fila(client, db_session):
    r = await client.post(
        "/api/q/guias/importar-lote",
        json={"urls": ["https://tc/guias/a", "https://tc/guias/a", "https://tc/guias/b"]},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["enfileirados"] == 2  # dedup
    rows = (await db_session.execute(select(GuiaFila))).scalars().all()
    assert {e.url for e in rows} == {"https://tc/guias/a", "https://tc/guias/b"}


@pytest.mark.asyncio
async def test_importar_default_vai_pra_fila_sem_resolver(client, db_session, monkeypatch):
    calls = _patch_scraper(monkeypatch)
    r = await client.post("/api/q/guias/importar", json={"url": "https://tc/guias/z"})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    assert calls == []  # NÃO resolve agora (preguiçoso)


@pytest.mark.asyncio
async def test_importar_apenas_catalogar_resolve_agora(client, db_session, monkeypatch):
    calls = _patch_scraper(monkeypatch)
    r = await client.post(
        "/api/q/guias/importar", json={"url": "x", "apenas_catalogar": True}
    )
    assert r.status_code == 202, r.text
    assert r.json()["cadernos"] == 1
    assert any(c["url"].endswith("/guia/resolver") for c in calls)
    # não enfileira coleta
    assert sum(1 for c in calls if c["url"].endswith("/enqueue/caderno")) == 0


@pytest.mark.asyncio
async def test_get_fila_e_pular(client, db_session):
    await client.post("/api/q/guias/importar-lote", json={"urls": ["a", "b"]})
    r = await client.get("/api/q/guias/fila")
    assert r.status_code == 200
    fila = r.json()["fila"]
    assert [e["posicao"] for e in fila] == [1, 2]
    fid = fila[0]["id"]
    rp = await client.post(f"/api/q/guias/fila/{fid}/pular")
    assert rp.status_code == 200 and rp.json()["ok"] is True
    rd = await client.delete(f"/api/q/guias/fila/{fila[1]['id']}")
    assert rd.status_code == 200 and rd.json()["ok"] is True
