"""Painel admin Modelos de IA: gates, settings e validação contra o catálogo."""

import pytest

import admin_llm_router
import main as main_module
from llm_registry import (
    DEFAULT_CALC_ALIAS,
    DEFAULT_GEMINI_MODEL,
    SETTING_CALC,
    get_setting,
)
from tests.conftest import USER_A

pytestmark = pytest.mark.asyncio

CATALOG_CENTRAL = {
    "source": "central",
    "models": [
        {
            "value": "witdev_copilot/gemini-3-flash-preview",
            "label": "Gemini 3 Flash",
            "provider": "gemini",
            "pricing": "$0.50 / $3.00",
            "description": None,
            "capabilities": {"vision": True},
        },
        {
            "value": "witdev_copilot/claude-sonnet-5",
            "label": "Claude Sonnet 5",
            "provider": "anthropic",
            "pricing": None,
            "description": None,
            "capabilities": {"vision": True},
        },
    ],
}


@pytest.fixture
def catalogo_central(monkeypatch):
    async def fake_fetch():
        return CATALOG_CENTRAL

    monkeypatch.setattr(admin_llm_router, "fetch_catalog", fake_fetch)
    monkeypatch.setattr(main_module, "fetch_catalog", fake_fetch)
    return CATALOG_CENTRAL


async def test_models_exige_admin(client, auth_state):
    auth_state["user"] = USER_A
    resp = await client.get("/api/admin/llm/models")
    assert resp.status_code == 403


async def test_settings_exige_admin(client, auth_state):
    auth_state["user"] = USER_A
    assert (await client.get("/api/admin/llm/settings")).status_code == 403
    assert (
        await client.put("/api/admin/llm/settings", json={"chat_aula": "x"})
    ).status_code == 403


async def test_get_settings_devolve_defaults(client):
    resp = await client.get("/api/admin/llm/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calculadora_reconhecimento"] == DEFAULT_CALC_ALIAS
    assert data["processamento_pdf"] == DEFAULT_GEMINI_MODEL
    assert data["chat_aula"] == DEFAULT_GEMINI_MODEL


async def test_put_valida_contra_catalogo(client, catalogo_central):
    resp = await client.put(
        "/api/admin/llm/settings",
        json={"calculadora_reconhecimento": "modelo-inventado"},
    )
    assert resp.status_code == 422


async def test_put_pdf_exige_id_gemini_derivado(client, catalogo_central):
    # PDF/chat validam contra a lista Gemini DERIVADA (id upstream), não o alias.
    alias_cheio = await client.put(
        "/api/admin/llm/settings",
        json={"processamento_pdf": "witdev_copilot/gemini-3-flash-preview"},
    )
    assert alias_cheio.status_code == 422

    derivado = await client.put(
        "/api/admin/llm/settings",
        json={"processamento_pdf": "gemini-3-flash-preview"},
    )
    assert derivado.status_code == 200
    assert derivado.json()["processamento_pdf"] == "gemini-3-flash-preview"


async def test_put_calc_persiste_alias(client, catalogo_central, db_session):
    resp = await client.put(
        "/api/admin/llm/settings",
        json={"calculadora_reconhecimento": "witdev_copilot/claude-sonnet-5"},
    )
    assert resp.status_code == 200
    assert resp.json()["calculadora_reconhecimento"] == "witdev_copilot/claude-sonnet-5"
    assert await get_setting(db_session, SETTING_CALC) == "witdev_copilot/claude-sonnet-5"


async def test_put_vazio_recusa(client, catalogo_central):
    resp = await client.put("/api/admin/llm/settings", json={})
    assert resp.status_code == 422


async def test_api_modelos_filtra_gemini_do_central(client, catalogo_central):
    resp = await client.get("/api/modelos")
    assert resp.status_code == 200
    modelos = resp.json()
    # Central tem gemini + anthropic → aqui só o Gemini, com id derivado.
    assert [m["value"] for m in modelos] == ["gemini-3-flash-preview"]
    assert modelos[0]["recommended"] is True  # default llm.processamento_pdf


async def test_api_modelos_fallback_local(client, monkeypatch):
    async def fake_fetch():
        from llm_registry import _local_fallback_payload

        return _local_fallback_payload()

    monkeypatch.setattr(main_module, "fetch_catalog", fake_fetch)
    resp = await client.get("/api/modelos")
    assert resp.status_code == 200
    valores = {m["value"] for m in resp.json()}
    assert "gemini-3-flash-preview" in valores and len(valores) >= 8
