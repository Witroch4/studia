"""llm_registry: normalização do catálogo central, fallback local e filtro Gemini."""

import pytest

import llm_registry
from llm_registry import (
    _local_fallback_payload,
    _normalize_central_models,
    fetch_catalog,
    gemini_id_from_alias,
    gemini_options_from_catalog,
    invalidate_catalog_cache,
)

CENTRAL_PAYLOAD = {
    "models": [
        {
            "value": "witdev_copilot/gemini-3-flash-preview",
            "alias": "witdev_copilot/gemini-3-flash-preview",
            "label": "Gemini 3 Flash",
            "provider": "gemini",
            "pricing": "$0.50 / $3.00",
            "supportsVision": True,
        },
        {
            "value": "witdev_copilot/claude-sonnet-5",
            "label": "Claude Sonnet 5",
            "provider": "anthropic",
            "supportsVision": True,
        },
        {"value": "witdev_copilot/gpt-texto", "label": "GPT Texto", "provider": "openai"},
    ],
    "source": "litellm_proxy",
}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeAsyncClient:
    """Substitui httpx.AsyncClient no fetch_catalog."""

    response: _FakeResponse = _FakeResponse(200, CENTRAL_PAYLOAD)
    raise_on_get: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        if type(self).raise_on_get is not None:
            raise type(self).raise_on_get
        return type(self).response


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_catalog_cache()
    yield
    invalidate_catalog_cache()


def test_normaliza_payload_central():
    models = _normalize_central_models(CENTRAL_PAYLOAD)
    assert [m["value"] for m in models] == [
        "witdev_copilot/gemini-3-flash-preview",
        "witdev_copilot/claude-sonnet-5",
        "witdev_copilot/gpt-texto",
    ]
    assert models[0]["capabilities"] == {"vision": True}
    assert models[2]["capabilities"] == {"vision": False}


def test_normaliza_payload_invalido():
    assert _normalize_central_models(None) == []
    assert _normalize_central_models({"models": [{"sem": "value"}]}) == []
    assert _normalize_central_models("lixo") == []


def test_gemini_id_from_alias():
    assert gemini_id_from_alias("witdev_copilot/gemini-3-flash-preview") == "gemini-3-flash-preview"
    assert gemini_id_from_alias("gemini-2.5-pro") == "gemini-2.5-pro"


def test_gemini_options_filtra_e_deriva_id():
    catalog = {"source": "central", "models": _normalize_central_models(CENTRAL_PAYLOAD)}
    options = gemini_options_from_catalog(catalog)
    assert [m["value"] for m in options] == ["gemini-3-flash-preview"]


@pytest.mark.asyncio
async def test_fetch_catalog_central_ok(monkeypatch):
    _FakeAsyncClient.response = _FakeResponse(200, CENTRAL_PAYLOAD)
    _FakeAsyncClient.raise_on_get = None
    monkeypatch.setattr(llm_registry.httpx, "AsyncClient", _FakeAsyncClient)

    catalog = await fetch_catalog()
    assert catalog["source"] == "central"
    # Central respondeu → usa SÓ a central, sem mesclar fallback local.
    assert len(catalog["models"]) == 3


@pytest.mark.asyncio
async def test_fetch_catalog_central_fora_usa_fallback(monkeypatch):
    import httpx

    _FakeAsyncClient.raise_on_get = httpx.ConnectError("down")
    monkeypatch.setattr(llm_registry.httpx, "AsyncClient", _FakeAsyncClient)

    catalog = await fetch_catalog()
    assert catalog["source"] == "local_fallback"
    assert {m["value"] for m in catalog["models"]} == {m["value"] for m in llm_registry.GEMINI_MODELS}
    _FakeAsyncClient.raise_on_get = None


@pytest.mark.asyncio
async def test_fetch_catalog_central_vazia_usa_fallback(monkeypatch):
    _FakeAsyncClient.response = _FakeResponse(200, {"models": []})
    _FakeAsyncClient.raise_on_get = None
    monkeypatch.setattr(llm_registry.httpx, "AsyncClient", _FakeAsyncClient)

    catalog = await fetch_catalog()
    assert catalog["source"] == "local_fallback"


@pytest.mark.asyncio
async def test_fetch_catalog_cacheia(monkeypatch):
    calls = {"n": 0}

    class CountingClient(_FakeAsyncClient):
        async def get(self, url):
            calls["n"] += 1
            return _FakeResponse(200, CENTRAL_PAYLOAD)

    monkeypatch.setattr(llm_registry.httpx, "AsyncClient", CountingClient)
    await fetch_catalog()
    await fetch_catalog()
    assert calls["n"] == 1


def test_fallback_local_marca_source():
    payload = _local_fallback_payload()
    assert payload["source"] == "local_fallback"
    assert all(m["capabilities"] == {"vision": True} for m in payload["models"])
