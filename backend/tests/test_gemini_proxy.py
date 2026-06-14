"""Escolha de transporte da IA: LiteLLM passthrough vs Gemini direto.

_client_config() é puro (lê env), então testa sem rede.
"""
import pytest

from gemini_service import _client_config, _get_client


def test_config_proxy_quando_litellm_key_setada(monkeypatch):
    monkeypatch.setenv("LITELLM_API_KEY", "sk-abc123")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://platform-litellm:4000")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-direct")
    cfg = _client_config()
    assert cfg.via_proxy is True
    assert cfg.api_key == "sk-abc123"
    assert cfg.base_url == "http://platform-litellm:4000/gemini"


def test_config_proxy_normaliza_barra_final(monkeypatch):
    monkeypatch.setenv("LITELLM_API_KEY", "sk-abc123")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://platform-litellm:4000/")
    cfg = _client_config()
    assert cfg.base_url == "http://platform-litellm:4000/gemini"


def test_config_direto_sem_litellm_key(monkeypatch):
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-direct")
    cfg = _client_config()
    assert cfg.via_proxy is False
    assert cfg.api_key == "AIza-direct"
    assert cfg.base_url is None


def test_get_client_constroi_nos_dois_modos(monkeypatch):
    from google import genai
    monkeypatch.setenv("LITELLM_API_KEY", "sk-abc123")
    assert isinstance(_get_client(), genai.Client)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-direct")
    assert isinstance(_get_client(), genai.Client)
