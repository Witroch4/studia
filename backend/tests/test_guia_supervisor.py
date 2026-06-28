from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import guia_service
from models import Guia, GuiaFila

CFG = dict(cooldown_s=900, max_coleta_s=21600, max_tentativas=3)


async def _guia(db, *, status="collecting"):
    g = Guia(tc_guia_id=None, nome="G", status=status)
    db.add(g)
    await db.flush()
    return g


def _deps(*, resolver=None, enqueue=None, completa=None):
    async def _r(db, url, *, page_size):  # cria um guia fake e devolve
        g = Guia(tc_guia_id=None, nome=f"resolvido:{url}", status="saving")
        db.add(g)
        await db.flush()
        return g

    async def _e(db, guia_id, *, page_size):
        return (1, [])

    async def _c(db, guia_id):
        return False

    return dict(
        resolver=resolver or _r,
        enqueue=enqueue or _e,
        completa=completa or _c,
    )


@pytest.mark.asyncio
async def test_primeiro_guia_inicia_imediatamente(db_session):
    await guia_service.enfileirar_urls(db_session, ["a"], requested_by=None)
    await db_session.flush()
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), **CFG, **_deps()
    )
    assert out["acao"] == "iniciou"
    [e] = (await db_session.execute(select(GuiaFila))).scalars().all()
    assert e.status == "collecting" and e.guia_id is not None


@pytest.mark.asyncio
async def test_nao_inicia_se_ja_coletando(db_session):
    g = await _guia(db_session)
    db_session.add(GuiaFila(guia_id=g.id, status="collecting", iniciado_em=datetime(2026, 1, 1, 11, 0, 0)))
    await guia_service.enfileirar_urls(db_session, ["b"], requested_by=None)
    await db_session.flush()
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), **CFG,
        **_deps(completa=lambda db, gid: _false()),
    )
    assert out["acao"] in ("aguardando", "nada")
    fila_b = (await db_session.execute(select(GuiaFila).where(GuiaFila.url == "b"))).scalar_one()
    assert fila_b.status == "queued"


async def _false():
    return False


@pytest.mark.asyncio
async def test_conclui_guia_e_dispara_cooldown(db_session):
    g = await _guia(db_session)
    e = GuiaFila(guia_id=g.id, status="collecting", iniciado_em=datetime(2026, 1, 1, 11, 0, 0))
    db_session.add(e)
    await db_session.flush()

    async def _completa(db, gid):
        return True

    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), **CFG,
        **_deps(completa=_completa),
    )
    assert out["acao"] == "concluiu"
    await db_session.refresh(e)
    assert e.status == "done" and e.finalizado_em == datetime(2026, 1, 1, 12, 0, 0)


@pytest.mark.asyncio
async def test_respeita_cooldown(db_session):
    fim = datetime(2026, 1, 1, 12, 0, 0)
    db_session.add(GuiaFila(url="x", status="done", finalizado_em=fim))
    await guia_service.enfileirar_urls(db_session, ["novo"], requested_by=None)
    await db_session.flush()
    # 100s depois → ainda dentro do cooldown de 900s
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=fim + timedelta(seconds=100), **CFG, **_deps()
    )
    assert out["acao"] == "cooldown"
    novo = (await db_session.execute(select(GuiaFila).where(GuiaFila.url == "novo"))).scalar_one()
    assert novo.status == "queued"


@pytest.mark.asyncio
async def test_inicia_apos_cooldown(db_session):
    fim = datetime(2026, 1, 1, 12, 0, 0)
    db_session.add(GuiaFila(url="x", status="done", finalizado_em=fim))
    await guia_service.enfileirar_urls(db_session, ["novo"], requested_by=None)
    await db_session.flush()
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=fim + timedelta(seconds=901), **CFG, **_deps()
    )
    assert out["acao"] == "iniciou"


@pytest.mark.asyncio
async def test_auto_skip_apos_max_coleta(db_session):
    g = await _guia(db_session)
    e = GuiaFila(guia_id=g.id, status="collecting", iniciado_em=datetime(2026, 1, 1, 0, 0, 0))
    db_session.add(e)
    await db_session.flush()

    async def _completa(db, gid):
        return False

    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 7, 0, 0), **CFG,  # 7h > 6h
        **_deps(completa=_completa),
    )
    assert out["acao"] == "pulou_timeout"
    await db_session.refresh(e)
    assert e.status == "skipped"


@pytest.mark.asyncio
async def test_resolver_falha_vira_error_apos_tentativas(db_session):
    await guia_service.enfileirar_urls(db_session, ["ruim"], requested_by=None)
    await db_session.flush()

    async def _resolver_falha(db, url, *, page_size):
        raise RuntimeError("scraper 502")

    agora = datetime(2026, 1, 1, 12, 0, 0)
    # 3 tentativas: cada tick incrementa; na 3ª vira error
    for _ in range(3):
        out = await guia_service.guia_supervisor_tick(
            db_session, agora=agora, **CFG, **_deps(resolver=_resolver_falha)
        )
    e = (await db_session.execute(select(GuiaFila).where(GuiaFila.url == "ruim"))).scalar_one()
    assert e.status == "error" and e.tentativas == 3 and out["acao"] == "erro_resolver"


@pytest.mark.asyncio
async def test_resolving_preso_drena_ate_error(db_session):
    e = GuiaFila(url="x", status="resolving", iniciado_em=datetime(2026, 1, 1, 11, 0, 0))
    db_session.add(e)
    await db_session.flush()
    agora = datetime(2026, 1, 1, 12, 0, 0)
    out = None
    for _ in range(3):  # max_tentativas=3
        out = await guia_service.guia_supervisor_tick(db_session, agora=agora, **CFG, **_deps())
    await db_session.refresh(e)
    assert out["acao"] == "erro_resolver"
    assert e.status == "error" and e.tentativas == 3


@pytest.mark.asyncio
async def test_cooldown_boundary_exato_inicia(db_session):
    fim = datetime(2026, 1, 1, 12, 0, 0)
    db_session.add(GuiaFila(url="x", status="done", finalizado_em=fim))
    await guia_service.enfileirar_urls(db_session, ["novo"], requested_by=None)
    await db_session.flush()
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=fim + timedelta(seconds=900), **CFG, **_deps()
    )
    assert out["acao"] == "iniciou"


def test_carregar_config_defaults(monkeypatch):
    for k in ("GUIA_COOLDOWN_SECONDS", "GUIA_SUPERVISOR_INTERVAL",
              "GUIA_MAX_COLETA_SECONDS", "GUIA_RESOLVE_MAX_TENTATIVAS"):
        monkeypatch.delenv(k, raising=False)
    from scripts.guia_supervisor import carregar_config

    cfg = carregar_config()
    assert cfg == {
        "cooldown_s": 900,
        "interval": 30,
        "max_coleta_s": 21600,
        "max_tentativas": 3,
    }
