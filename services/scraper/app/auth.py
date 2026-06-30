"""Login automatizado em TecConcursos via Playwright.

Salva `storage_state.json` (cookies + localStorage) que o `TcClient` (httpx)
reusa em todas as requisições JSON. Renovar quando sessão expirar.
"""

from __future__ import annotations

import json
import os
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from app.config import get_settings
from app.observability import get_logger

log = get_logger(__name__)

TC_TASK_CADERNO = "caderno"
TC_TASK_FORUM_LAZY = "forum_lazy"
TC_TASK_FORUM_MASS = "forum_mass"
TC_TASK_GABARITO = "gabarito"
TC_TASK_GUIA = "guia"
TC_TASK_IMAGEM = "imagem"

TC_ACCOUNT_TASKS = (
    TC_TASK_CADERNO,
    TC_TASK_FORUM_LAZY,
    TC_TASK_FORUM_MASS,
    TC_TASK_GABARITO,
    TC_TASK_GUIA,
    TC_TASK_IMAGEM,
)
DEFAULT_TC_ACCOUNT_CAPABILITIES = {task: True for task in TC_ACCOUNT_TASKS}


class NoEligibleTcAccount(RuntimeError):
    def __init__(self, task: str) -> None:
        super().__init__(f"nenhuma conta TC habilitada para a tarefa {task}")
        self.task = task


def _runtime_credentials_path(settings: Any | None = None) -> Path:
    settings = settings or get_settings()
    return settings.tc_storage_state_path.parent / "tc_credentials.json"


def _accounts_path(settings: Any | None = None) -> Path:
    settings = settings or get_settings()
    return settings.tc_storage_state_path.parent / "tc_accounts.json"


def _account_storage_dir(settings: Any | None = None) -> Path:
    settings = settings or get_settings()
    return settings.tc_storage_state_path.parent / "tc_accounts"


def _account_storage_path(account_id: str, *, settings: Any | None = None) -> Path:
    return _account_storage_dir(settings) / f"{account_id}.storage_state.json"


def _account_id_for_email(email: str) -> str:
    normalized = email.strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def _normalize_capabilities(raw: Any | None) -> dict[str, bool]:
    capabilities = dict(DEFAULT_TC_ACCOUNT_CAPABILITIES)
    if isinstance(raw, dict):
        for task in TC_ACCOUNT_TASKS:
            if task in raw:
                capabilities[task] = bool(raw[task])
    return capabilities


def _read_accounts_file(settings: Any | None = None) -> list[dict[str, Any]]:
    path = _accounts_path(settings)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("tc.accounts.invalid", path=str(path))
        return []
    raw_accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(raw_accounts, list):
        return []
    accounts: list[dict[str, Any]] = []
    for raw in raw_accounts:
        if not isinstance(raw, dict):
            continue
        email = str(raw.get("email") or "").strip()
        password = str(raw.get("password") or "")
        if not email or not password:
            continue
        account_id = str(raw.get("id") or _account_id_for_email(email))
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        last_used_at = (
            raw.get("last_used_at") if isinstance(raw.get("last_used_at"), dict) else {}
        )
        accounts.append(
            {
                "id": account_id,
                "email": email,
                "password": password,
                "source": str(raw.get("source") or "runtime"),
                "capabilities": _normalize_capabilities(raw.get("capabilities")),
                "usage": {
                    task: int(usage.get(task) or 0)
                    for task in TC_ACCOUNT_TASKS
                },
                "last_used_at": {
                    task: str(last_used_at.get(task) or "")
                    for task in TC_ACCOUNT_TASKS
                },
                "legacy_storage": False,
            }
        )
    return accounts


def _write_accounts_file(accounts: list[dict[str, Any]], *, settings: Any | None = None) -> Path:
    path = _accounts_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        "accounts": [
            {
                "id": account["id"],
                "email": account["email"],
                "password": account["password"],
                "source": account.get("source") or "runtime",
                "capabilities": _normalize_capabilities(account.get("capabilities")),
                "usage": {
                    task: int((account.get("usage") or {}).get(task) or 0)
                    for task in TC_ACCOUNT_TASKS
                },
                "last_used_at": {
                    task: str((account.get("last_used_at") or {}).get(task) or "")
                    for task in TC_ACCOUNT_TASKS
                },
            }
            for account in accounts
        ]
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def _legacy_account(
    *,
    email: str,
    password: str,
    source: str,
) -> dict[str, Any]:
    return {
        "id": _account_id_for_email(email),
        "email": email,
        "password": password,
        "source": source,
        "capabilities": dict(DEFAULT_TC_ACCOUNT_CAPABILITIES),
        "usage": {task: 0 for task in TC_ACCOUNT_TASKS},
        "last_used_at": {task: "" for task in TC_ACCOUNT_TASKS},
        "legacy_storage": True,
    }


def _list_account_records(settings: Any | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    accounts = _read_accounts_file(settings)
    seen = {str(account["email"]).strip().lower() for account in accounts}

    runtime = _read_runtime_credentials(settings)
    if runtime and runtime["email"].strip().lower() not in seen:
        accounts.append(
            _legacy_account(
                email=runtime["email"],
                password=runtime["password"],
                source="runtime",
            )
        )
        seen.add(runtime["email"].strip().lower())

    tc_email = getattr(settings, "tc_email", None)
    tc_password = getattr(settings, "tc_password", None)
    if tc_email and tc_password:
        env_email = str(tc_email).strip()
        if env_email and env_email.lower() not in seen:
            accounts.append(
                _legacy_account(
                    email=env_email,
                    password=str(tc_password),
                    source="env",
                )
            )
    return accounts


def _sanitize_account(account: dict[str, Any], *, settings: Any | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = tc_account_storage_path(account["id"], settings=settings)
    if not path.exists() and not account.get("legacy_storage"):
        runtime = _read_runtime_credentials(settings)
        legacy_email = (
            runtime["email"]
            if runtime
            else str(getattr(settings, "tc_email", "") or "").strip()
        )
        if (
            legacy_email
            and legacy_email.lower() == str(account["email"]).strip().lower()
            and settings.tc_storage_state_path.exists()
        ):
            path = settings.tc_storage_state_path
    storage_exists = path.exists()
    storage_mtime: str | None = None
    storage_age_seconds: int | None = None
    if storage_exists:
        stat = path.stat()
        storage_mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        storage_age_seconds = max(0, int(time.time() - stat.st_mtime))
    return {
        "id": account["id"],
        "email": account["email"],
        "source": account.get("source") or "runtime",
        "capabilities": _normalize_capabilities(account.get("capabilities")),
        "storage_state_exists": storage_exists,
        "storage_state_mtime": storage_mtime,
        "storage_state_age_seconds": storage_age_seconds,
        "usage": {
            task: int((account.get("usage") or {}).get(task) or 0)
            for task in TC_ACCOUNT_TASKS
        },
    }


def _read_runtime_credentials(settings: Any | None = None) -> dict[str, str] | None:
    path = _runtime_credentials_path(settings)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("tc.credentials.runtime_invalid", path=str(path))
        return None
    email = str(data.get("email") or "").strip()
    password = str(data.get("password") or "")
    if not email or not password:
        return None
    return {"email": email, "password": password}


def save_tc_account(
    email: str,
    password: str,
    *,
    capabilities: dict[str, bool] | None = None,
    settings: Any | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    email = email.strip()
    if not email or not password:
        raise ValueError("email e senha do TC são obrigatórios")
    accounts = _read_accounts_file(settings)
    account_id = _account_id_for_email(email)
    normalized_capabilities = _normalize_capabilities(capabilities)
    updated = False
    for account in accounts:
        if account["id"] == account_id or account["email"].strip().lower() == email.lower():
            account.update(
                {
                    "id": account_id,
                    "email": email,
                    "password": password,
                    "source": "runtime",
                    "capabilities": normalized_capabilities,
                }
            )
            updated = True
            break
    if not updated:
        accounts.append(
            {
                "id": account_id,
                "email": email,
                "password": password,
                "source": "runtime",
                "capabilities": normalized_capabilities,
                "usage": {task: 0 for task in TC_ACCOUNT_TASKS},
                "last_used_at": {task: "" for task in TC_ACCOUNT_TASKS},
            }
        )
    _write_accounts_file(accounts, settings=settings)
    log.info("tc.account.saved", email=email, account_id=account_id)
    return _sanitize_account(
        next(account for account in _read_accounts_file(settings) if account["id"] == account_id),
        settings=settings,
    )


def save_runtime_credentials(
    email: str,
    password: str,
    *,
    settings: Any | None = None,
    capabilities: dict[str, bool] | None = None,
) -> Path:
    email = email.strip()
    if not email or not password:
        raise ValueError("email e senha do TC são obrigatórios")
    path = _runtime_credentials_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"email": email, "password": password}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    save_tc_account(email, password, capabilities=capabilities, settings=settings)
    log.info("tc.credentials.runtime_saved", email=email, path=str(path))
    return path


def effective_tc_credentials(*, settings: Any | None = None) -> tuple[str | None, str | None, str]:
    settings = settings or get_settings()
    runtime = _read_runtime_credentials(settings)
    if runtime:
        return runtime["email"], runtime["password"], "runtime"
    accounts = _read_accounts_file(settings)
    if accounts:
        account = accounts[0]
        return account["email"], account["password"], str(account.get("source") or "runtime")
    tc_email = getattr(settings, "tc_email", None)
    tc_password = getattr(settings, "tc_password", None)
    if tc_email and tc_password:
        return tc_email, tc_password, "env"
    return None, None, "none"


def list_tc_accounts(*, settings: Any | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    return [_sanitize_account(account, settings=settings) for account in _list_account_records(settings)]


def get_tc_account(account_id: str, *, settings: Any | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    for account in _list_account_records(settings):
        if account["id"] == account_id:
            return account
    raise KeyError(account_id)


def update_tc_account_capabilities(
    account_id: str,
    capabilities: dict[str, bool],
    *,
    settings: Any | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    accounts = _read_accounts_file(settings)
    for account in accounts:
        if account["id"] == account_id:
            merged = _normalize_capabilities(account.get("capabilities"))
            for task, enabled in capabilities.items():
                if task in TC_ACCOUNT_TASKS:
                    merged[task] = bool(enabled)
            account["capabilities"] = merged
            _write_accounts_file(accounts, settings=settings)
            return _sanitize_account(
                next(a for a in _read_accounts_file(settings) if a["id"] == account_id),
                settings=settings,
            )

    # Contas legadas/env ainda não estão no arquivo. Materializa antes de editar.
    legacy = get_tc_account(account_id, settings=settings)
    save_tc_account(
        legacy["email"],
        legacy["password"],
        capabilities=legacy.get("capabilities"),
        settings=settings,
    )
    return update_tc_account_capabilities(
        account_id, capabilities, settings=settings
    )


def _touch_account_usage(account_id: str, task: str, *, settings: Any | None = None) -> None:
    accounts = _read_accounts_file(settings)
    for account in accounts:
        if account["id"] != account_id:
            continue
        usage = account.setdefault("usage", {})
        last_used_at = account.setdefault("last_used_at", {})
        usage[task] = int(usage.get(task) or 0) + 1
        last_used_at[task] = datetime.now(timezone.utc).isoformat()
        _write_accounts_file(accounts, settings=settings)
        return


def select_tc_account_for_task(
    task: str,
    *,
    settings: Any | None = None,
    touch_usage: bool = True,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if task not in TC_ACCOUNT_TASKS:
        raise ValueError(f"tarefa TC inválida: {task}")
    accounts = _list_account_records(settings)
    eligible = [
        account
        for account in accounts
        if _normalize_capabilities(account.get("capabilities")).get(task) is True
    ]
    if not eligible:
        raise NoEligibleTcAccount(task)
    selected = sorted(
        eligible,
        key=lambda account: (
            int((account.get("usage") or {}).get(task) or 0),
            str((account.get("last_used_at") or {}).get(task) or ""),
            str(account["email"]).lower(),
        ),
    )[0]
    if touch_usage:
        _touch_account_usage(selected["id"], task, settings=settings)
        selected = get_tc_account(selected["id"], settings=settings)
    return selected


def tc_account_storage_path(
    account_id: str | None = None,
    *,
    task: str | None = None,
    settings: Any | None = None,
    touch_usage: bool = True,
) -> Path:
    settings = settings or get_settings()
    if account_id:
        account = get_tc_account(account_id, settings=settings)
    elif task:
        account = select_tc_account_for_task(task, settings=settings, touch_usage=touch_usage)
    else:
        return settings.tc_storage_state_path
    if account.get("legacy_storage"):
        return settings.tc_storage_state_path
    return _account_storage_path(account["id"], settings=settings)


def clear_tc_session(account_id: str | None = None, *, settings: Any | None = None) -> bool:
    settings = settings or get_settings()
    if account_id:
        account = get_tc_account(account_id, settings=settings)
        storage_path = tc_account_storage_path(account_id, settings=settings)
        if not storage_path.exists() and not account.get("legacy_storage"):
            runtime = _read_runtime_credentials(settings)
            legacy_email = (
                runtime["email"]
                if runtime
                else str(getattr(settings, "tc_email", "") or "").strip()
            )
            if (
                legacy_email
                and legacy_email.lower() == str(account["email"]).strip().lower()
                and settings.tc_storage_state_path.exists()
            ):
                storage_path = settings.tc_storage_state_path
    else:
        storage_path = settings.tc_storage_state_path
    if not storage_path.exists():
        return False
    storage_path.unlink()
    log.info("tc.session.removed", storage=str(storage_path))
    return True


def tc_auth_status(*, settings: Any | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    email, _password, source = effective_tc_credentials(settings=settings)
    storage_path = settings.tc_storage_state_path
    storage_exists = storage_path.exists()
    storage_mtime: str | None = None
    storage_age_seconds: int | None = None
    if storage_exists:
        stat = storage_path.stat()
        storage_mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        storage_age_seconds = max(0, int(time.time() - stat.st_mtime))
    accounts = list_tc_accounts(settings=settings)
    primary = accounts[0] if accounts else None
    if primary is not None:
        email = primary["email"]
        source = primary["source"]
        storage_exists = bool(primary["storage_state_exists"])
        storage_mtime = primary["storage_state_mtime"]
        storage_age_seconds = primary["storage_state_age_seconds"]
    return {
        "configured": bool(email),
        "email": email,
        "source": source,
        "storage_state_exists": storage_exists,
        "storage_state_mtime": storage_mtime,
        "storage_state_age_seconds": storage_age_seconds,
        "tasks": list(TC_ACCOUNT_TASKS),
        "accounts": accounts,
    }


async def login_and_save_state(
    headless: bool = True,
    *,
    email: str | None = None,
    password: str | None = None,
    account_id: str | None = None,
    task: str | None = None,
) -> Path:
    """Loga via Playwright e persiste storage_state em disco.

    Retorna o caminho do arquivo salvo. Headless False na primeira execução
    ajuda a debugar (captcha, layout novo, etc).
    """
    settings = get_settings()
    account: dict[str, Any] | None = None
    tc_email = (email or "").strip()
    tc_password = password
    source = "request"
    if account_id:
        account = get_tc_account(account_id, settings=settings)
        tc_email = account["email"]
        tc_password = account["password"]
        source = str(account.get("source") or "runtime")
    elif task:
        account = select_tc_account_for_task(task, settings=settings)
        tc_email = account["email"]
        tc_password = account["password"]
        source = str(account.get("source") or "runtime")
    elif not tc_email or not tc_password:
        tc_email, tc_password, source = effective_tc_credentials(settings=settings)
        if tc_email:
            try:
                account = get_tc_account(_account_id_for_email(tc_email), settings=settings)
            except KeyError:
                account = None
    if not tc_email or not tc_password:
        raise RuntimeError(
            "Credenciais TC ausentes. Informe email/senha na UI ou configure "
            "TC_EMAIL e TC_PASSWORD no ambiente."
        )

    if account is not None:
        storage_path = (
            settings.tc_storage_state_path
            if account.get("legacy_storage")
            else _account_storage_path(account["id"], settings=settings)
        )
    elif email:
        storage_path = _account_storage_path(_account_id_for_email(tc_email), settings=settings)
    else:
        storage_path = settings.tc_storage_state_path
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    log.info(
        "tc.login.start",
        email=tc_email,
        credentials_source=source,
        storage=str(storage_path),
        headless=headless,
    )

    # Se proxy residencial configurado, passa pro Playwright
    proxy_cfg = None
    if settings.residential_proxy_url:
        from urllib.parse import urlparse
        u = urlparse(settings.residential_proxy_url)
        # Chromium NÃO suporta auth em SOCKS5 — usa HTTP CONNECT na mesma porta
        # (residential-proxy auto-detecta SOCKS vs HTTP pelo 1º byte).
        proxy_cfg = {
            "server": f"http://{u.hostname}:{u.port}",
            "username": u.username,
            "password": u.password,
        }
        log.info("tc.login.proxy_enabled", server=proxy_cfg["server"], user=proxy_cfg["username"])

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx_kwargs: dict = dict(
            user_agent=settings.tc_user_agent,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1920, "height": 1080},
        )
        if proxy_cfg:
            ctx_kwargs["proxy"] = proxy_cfg
        ctx = await browser.new_context(**ctx_kwargs)
        page = await ctx.new_page()
        await page.goto(f"{settings.tc_base}/login")

        await page.fill('input[type="email"]', tc_email)
        await page.fill('input[type="password"]', tc_password)
        await page.click('button:has-text("Entrar no site")')

        # Aguarda sair de /login (redirect para qualquer área autenticada)
        try:
            await page.wait_for_url(
                lambda url: "/login" not in url, timeout=20_000
            )
        except Exception:
            # Captura snapshot para diagnóstico antes de propagar
            html = await page.content()
            snap_path = storage_path.with_suffix(".login_fail.html")
            snap_path.write_text(html, encoding="utf-8")
            log.error("tc.login.timeout", snapshot=str(snap_path), url=page.url)
            raise

        # Confirma com um GET autenticado leve — se voltar HTML de login, falhou
        await page.wait_for_load_state("networkidle", timeout=10_000)
        log.info("tc.login.url_after", url=page.url)

        await ctx.storage_state(path=storage_path)
        await browser.close()

    log.info("tc.login.ok", storage=str(storage_path))
    return storage_path


def load_cookies_for_httpx(
    storage_path: Path | None = None,
    *,
    account_id: str | None = None,
    task: str | None = None,
) -> dict[str, str]:
    """Lê storage_state.json e retorna cookies como dict para httpx."""
    storage_path = storage_path or tc_account_storage_path(account_id, task=task)
    if not storage_path.exists():
        raise FileNotFoundError(
            f"storage_state ausente em {storage_path}; "
            "rode `python -m app.main login` primeiro"
        )
    state = json.loads(storage_path.read_text(encoding="utf-8"))
    return {
        c["name"]: c["value"]
        for c in state.get("cookies", [])
        if "tecconcursos" in c.get("domain", "")
    }
