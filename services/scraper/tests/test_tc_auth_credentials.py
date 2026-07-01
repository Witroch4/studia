from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import app.auth as tc_auth


@dataclass
class _Settings:
    tc_email: str | None
    tc_password: str | None
    tc_storage_state_path: Path


def test_runtime_credentials_override_env_without_exposing_password(tmp_path):
    settings = _Settings(
        tc_email="env@example.com",
        tc_password="env-pass",
        tc_storage_state_path=tmp_path / "storage_state.json",
    )

    tc_auth.save_runtime_credentials("runtime@example.com", "runtime-pass", settings=settings)

    status = tc_auth.tc_auth_status(settings=settings)
    email, password, source = tc_auth.effective_tc_credentials(settings=settings)

    assert (email, password, source) == ("runtime@example.com", "runtime-pass", "runtime")
    assert status["configured"] is True
    assert status["email"] == "runtime@example.com"
    assert status["source"] == "runtime"
    assert "password" not in status
    assert status["accounts"][0]["email"] == "runtime@example.com"
    assert "password" not in status["accounts"][0]


def test_effective_credentials_falls_back_to_env(tmp_path):
    settings = _Settings(
        tc_email="env@example.com",
        tc_password="env-pass",
        tc_storage_state_path=tmp_path / "storage_state.json",
    )

    assert tc_auth.effective_tc_credentials(settings=settings) == (
        "env@example.com",
        "env-pass",
        "env",
    )


def test_clear_tc_session_removes_storage_state_only(tmp_path):
    settings = _Settings(
        tc_email="env@example.com",
        tc_password="env-pass",
        tc_storage_state_path=tmp_path / "storage_state.json",
    )
    settings.tc_storage_state_path.write_text("{}", encoding="utf-8")
    tc_auth.save_runtime_credentials("runtime@example.com", "runtime-pass", settings=settings)

    removed = tc_auth.clear_tc_session(settings=settings)

    assert removed is True
    assert not settings.tc_storage_state_path.exists()
    assert tc_auth.effective_tc_credentials(settings=settings)[0] == "runtime@example.com"


def test_saving_second_account_preserves_previous_legacy_session(tmp_path):
    settings = _Settings(
        tc_email=None,
        tc_password=None,
        tc_storage_state_path=tmp_path / "storage_state.json",
    )
    settings.tc_storage_state_path.write_text('{"cookies": []}', encoding="utf-8")
    tc_auth.save_runtime_credentials("old@example.com", "old-pass", settings=settings)
    old_account_id = tc_auth.tc_auth_status(settings=settings)["accounts"][0]["id"]

    new_account_id = tc_auth._account_id_for_email("new@example.com")
    new_storage = tmp_path / "tc_accounts" / f"{new_account_id}.storage_state.json"
    new_storage.parent.mkdir(parents=True, exist_ok=True)
    new_storage.write_text('{"cookies": []}', encoding="utf-8")
    tc_auth.save_runtime_credentials("new@example.com", "new-pass", settings=settings)

    accounts = {
        account["email"]: account
        for account in tc_auth.tc_auth_status(settings=settings)["accounts"]
    }

    assert accounts["old@example.com"]["storage_state_exists"] is True
    assert (tmp_path / "tc_accounts" / f"{old_account_id}.storage_state.json").exists()


def test_select_tc_account_respects_task_capabilities_and_balances_usage(tmp_path):
    settings = _Settings(
        tc_email=None,
        tc_password=None,
        tc_storage_state_path=tmp_path / "storage_state.json",
    )
    tc_auth.save_tc_account(
        "a@example.com",
        "a-pass",
        capabilities={
            tc_auth.TC_TASK_CADERNO: True,
            tc_auth.TC_TASK_FORUM_LAZY: False,
            tc_auth.TC_TASK_FORUM_MASS: False,
        },
        settings=settings,
    )
    tc_auth.save_tc_account(
        "b@example.com",
        "b-pass",
        capabilities={
            tc_auth.TC_TASK_CADERNO: False,
            tc_auth.TC_TASK_FORUM_LAZY: True,
            tc_auth.TC_TASK_FORUM_MASS: True,
        },
        settings=settings,
    )
    tc_auth.save_tc_account(
        "c@example.com",
        "c-pass",
        capabilities={
            tc_auth.TC_TASK_CADERNO: True,
            tc_auth.TC_TASK_FORUM_LAZY: True,
            tc_auth.TC_TASK_FORUM_MASS: False,
        },
        settings=settings,
    )

    first = tc_auth.select_tc_account_for_task(tc_auth.TC_TASK_CADERNO, settings=settings)
    second = tc_auth.select_tc_account_for_task(tc_auth.TC_TASK_CADERNO, settings=settings)
    lazy = tc_auth.select_tc_account_for_task(tc_auth.TC_TASK_FORUM_LAZY, settings=settings)

    assert {first["email"], second["email"]} == {"a@example.com", "c@example.com"}
    assert lazy["email"] == "b@example.com"


def test_select_tc_account_raises_when_no_enabled_account(tmp_path):
    settings = _Settings(
        tc_email=None,
        tc_password=None,
        tc_storage_state_path=tmp_path / "storage_state.json",
    )
    tc_auth.save_tc_account(
        "a@example.com",
        "a-pass",
        capabilities={tc_auth.TC_TASK_FORUM_MASS: False},
        settings=settings,
    )

    with pytest.raises(tc_auth.NoEligibleTcAccount):
        tc_auth.select_tc_account_for_task(tc_auth.TC_TASK_FORUM_MASS, settings=settings)


@pytest.mark.asyncio
async def test_api_login_saves_credentials_after_success(monkeypatch, tmp_path):
    from app.main import TcAuthLoginBody, tc_auth_login_endpoint

    settings = _Settings(
        tc_email=None,
        tc_password=None,
        tc_storage_state_path=tmp_path / "storage_state.json",
    )
    logins: list[tuple[str | None, str | None]] = []

    async def fake_login_and_save_state(*, headless: bool = True, email=None, password=None):
        logins.append((email, password))
        settings.tc_storage_state_path.write_text("{}", encoding="utf-8")
        return settings.tc_storage_state_path

    monkeypatch.setattr(tc_auth, "get_settings", lambda: settings)
    monkeypatch.setattr("app.main.login_and_save_state", fake_login_and_save_state)

    result = await tc_auth_login_endpoint(
        TcAuthLoginBody(email="runtime@example.com", password="runtime-pass")
    )

    assert result["ok"] is True
    assert result["email"] == "runtime@example.com"
    assert result["storage_state_exists"] is True
    assert logins == [("runtime@example.com", "runtime-pass")]
    assert tc_auth.effective_tc_credentials(settings=settings) == (
        "runtime@example.com",
        "runtime-pass",
        "runtime",
    )
