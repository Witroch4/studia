"""Login automatizado em TecConcursos via Playwright.

Salva `storage_state.json` (cookies + localStorage) que o `TcClient` (httpx)
reusa em todas as requisições JSON. Renovar quando sessão expirar.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from app.config import get_settings
from app.observability import get_logger

log = get_logger(__name__)


def _runtime_credentials_path(settings: Any | None = None) -> Path:
    settings = settings or get_settings()
    return settings.tc_storage_state_path.parent / "tc_credentials.json"


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


def save_runtime_credentials(email: str, password: str, *, settings: Any | None = None) -> Path:
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
    log.info("tc.credentials.runtime_saved", email=email, path=str(path))
    return path


def effective_tc_credentials(*, settings: Any | None = None) -> tuple[str | None, str | None, str]:
    settings = settings or get_settings()
    runtime = _read_runtime_credentials(settings)
    if runtime:
        return runtime["email"], runtime["password"], "runtime"
    if settings.tc_email and settings.tc_password:
        return settings.tc_email, settings.tc_password, "env"
    return None, None, "none"


def clear_tc_session(*, settings: Any | None = None) -> bool:
    settings = settings or get_settings()
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
    return {
        "configured": bool(email),
        "email": email,
        "source": source,
        "storage_state_exists": storage_exists,
        "storage_state_mtime": storage_mtime,
        "storage_state_age_seconds": storage_age_seconds,
    }


async def login_and_save_state(
    headless: bool = True,
    *,
    email: str | None = None,
    password: str | None = None,
) -> Path:
    """Loga via Playwright e persiste storage_state em disco.

    Retorna o caminho do arquivo salvo. Headless False na primeira execução
    ajuda a debugar (captcha, layout novo, etc).
    """
    settings = get_settings()
    tc_email = (email or "").strip()
    tc_password = password
    source = "request"
    if not tc_email or not tc_password:
        tc_email, tc_password, source = effective_tc_credentials(settings=settings)
    if not tc_email or not tc_password:
        raise RuntimeError(
            "Credenciais TC ausentes. Informe email/senha na UI ou configure "
            "TC_EMAIL e TC_PASSWORD no ambiente."
        )

    storage_path = settings.tc_storage_state_path
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


def load_cookies_for_httpx(storage_path: Path | None = None) -> dict[str, str]:
    """Lê storage_state.json e retorna cookies como dict para httpx."""
    storage_path = storage_path or get_settings().tc_storage_state_path
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
