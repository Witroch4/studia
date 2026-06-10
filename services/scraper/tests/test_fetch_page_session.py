"""Testes do auto-relogin em `_fetch_page_from_tc`.

Não exigem Postgres: TcClient, login e fetch_pagina são todos mockados.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)

import app.tasks.caderno as caderno_tasks
from app.schemas import SessionExpired


@dataclass
class _FakeResponse:
    status_code: int


def _make_fake_tc_client(warmup_statuses: list[int]) -> type:
    """Fábrica de TcClient fake: cada instância consome o próximo status."""
    statuses = iter(warmup_statuses)

    class _FakeInnerClient:
        async def get(self, *args, **kwargs) -> _FakeResponse:
            return _FakeResponse(status_code=next(statuses))

    class _FakeTcClient:
        def __init__(self, cookies) -> None:
            self._client = _FakeInnerClient()

        async def __aenter__(self) -> "_FakeTcClient":
            return self

        async def __aexit__(self, *exc) -> None:
            return None

    return _FakeTcClient


@dataclass
class _FakeSettings:
    tc_storage_state_path: Path


@pytest.fixture
def session_env(monkeypatch, tmp_path):
    """Mocka cookies, settings, login e fetch_pagina."""
    relogins: list[bool] = []
    fetched: list[tuple[int, int, int]] = []

    monkeypatch.setattr(caderno_tasks, "load_cookies_for_httpx", lambda: {})
    monkeypatch.setattr(
        caderno_tasks,
        "get_settings",
        lambda: _FakeSettings(tc_storage_state_path=tmp_path / "storage_state.json"),
    )

    async def fake_login(*, headless: bool = True) -> str:
        relogins.append(headless)
        return str(tmp_path / "storage_state.json")

    async def fake_fetch_pagina(client, caderno_id, inicio, page_size):
        fetched.append((caderno_id, inicio, page_size))
        return [{"idQuestao": 1}]

    monkeypatch.setattr(caderno_tasks, "login_and_save_state", fake_login)
    monkeypatch.setattr(caderno_tasks, "fetch_pagina", fake_fetch_pagina)
    return relogins, fetched


@pytest.mark.asyncio
async def test_warmup_redirect_triggers_relogin_and_retries(session_env, monkeypatch):
    relogins, fetched = session_env
    # 1ª tentativa: 302 (sessão morta) → reloga → 2ª tentativa: 200 → fetch ok
    monkeypatch.setattr(caderno_tasks, "TcClient", _make_fake_tc_client([302, 200]))

    result = await caderno_tasks._fetch_page_from_tc(95872872, 2800, 200)

    assert result == [{"idQuestao": 1}]
    assert relogins == [True]
    assert fetched == [(95872872, 2800, 200)]


@pytest.mark.asyncio
async def test_warmup_ok_does_not_relogin(session_env, monkeypatch):
    relogins, fetched = session_env
    monkeypatch.setattr(caderno_tasks, "TcClient", _make_fake_tc_client([200]))

    result = await caderno_tasks._fetch_page_from_tc(95872872, 2800, 200)

    assert result == [{"idQuestao": 1}]
    assert relogins == []
    assert fetched == [(95872872, 2800, 200)]


@pytest.mark.asyncio
async def test_warmup_redirect_after_relogin_raises_session_expired(
    session_env, monkeypatch
):
    relogins, fetched = session_env
    monkeypatch.setattr(caderno_tasks, "TcClient", _make_fake_tc_client([302, 302]))

    with pytest.raises(SessionExpired):
        await caderno_tasks._fetch_page_from_tc(95872872, 2800, 200)

    assert relogins == [True]
    assert fetched == []


class _ExplodingSessionFactory:
    """Falha se for chamada — prova que o gate curto-circuita antes do DB."""

    def __call__(self, *args, **kwargs):
        raise AssertionError("session_factory não deveria ser chamada")


@pytest.mark.asyncio
async def test_meili_index_skips_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setattr(
        caderno_tasks,
        "get_settings",
        lambda: type(
            "S", (), {"meili_url": None, "meili_key": None,
                      "tc_storage_state_path": tmp_path / "s.json"}
        )(),
    )
    # meili_url None → retorna sem tocar no DB nem no Meili
    await caderno_tasks._index_meili_best_effort(_ExplodingSessionFactory(), [1, 2, 3])


@pytest.mark.asyncio
async def test_meili_index_skips_when_no_pks(monkeypatch, tmp_path):
    monkeypatch.setattr(
        caderno_tasks,
        "get_settings",
        lambda: type(
            "S", (), {"meili_url": "http://meili:7700", "meili_key": "k",
                      "tc_storage_state_path": tmp_path / "s.json"}
        )(),
    )
    # pks vazio → no-op, mesmo com Meili configurado
    await caderno_tasks._index_meili_best_effort(_ExplodingSessionFactory(), [])


@pytest.mark.asyncio
async def test_meili_index_is_best_effort_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        caderno_tasks,
        "get_settings",
        lambda: type(
            "S", (), {"meili_url": "http://meili:7700", "meili_key": "k",
                      "tc_storage_state_path": tmp_path / "s.json"}
        )(),
    )

    class _BoomFactory:
        def __call__(self, *args, **kwargs):
            raise RuntimeError("DB indisponível")

    # Qualquer falha (import, DB, HTTP) é engolida — não propaga pro worker
    await caderno_tasks._index_meili_best_effort(_BoomFactory(), [1, 2, 3])


@pytest.mark.asyncio
async def test_relogin_skipped_when_storage_state_is_fresh(session_env, tmp_path):
    relogins, _ = session_env
    fresh = tmp_path / "storage_state.json"
    fresh.write_text("{}")  # mtime = agora

    await caderno_tasks._ensure_fresh_session()
    assert relogins == []

    # Arquivo antigo → reloga
    stat = os.stat(fresh)
    os.utime(fresh, (stat.st_atime, stat.st_mtime - 3600))
    await caderno_tasks._ensure_fresh_session()
    assert relogins == [True]
