"""Login automatizado em TecConcursos via Playwright.

Salva `storage_state.json` (cookies + localStorage) que o `TcClient` (httpx)
reusa em todas as requisições JSON. Renovar quando sessão expirar.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import async_playwright

from app.config import get_settings
from app.observability import get_logger

log = get_logger(__name__)


async def login_and_save_state(headless: bool = True) -> Path:
    """Loga via Playwright e persiste storage_state em disco.

    Retorna o caminho do arquivo salvo. Headless False na primeira execução
    ajuda a debugar (captcha, layout novo, etc).
    """
    settings = get_settings()
    if not settings.tc_email or not settings.tc_password:
        raise RuntimeError(
            "TC_EMAIL e TC_PASSWORD precisam estar no .env "
            "(ou exportadas no ambiente)"
        )

    storage_path = settings.tc_storage_state_path
    log.info(
        "tc.login.start",
        email=settings.tc_email,
        storage=str(storage_path),
        headless=headless,
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=settings.tc_user_agent,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1920, "height": 1080},
        )
        page = await ctx.new_page()
        await page.goto(f"{settings.tc_base}/login")

        await page.fill('input[type="email"]', settings.tc_email)
        await page.fill('input[type="password"]', settings.tc_password)
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
