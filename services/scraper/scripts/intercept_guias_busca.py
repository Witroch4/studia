"""Intercepta a busca de guias do TC (palavra-chave) para achar a API e os slugs.

uso: python scripts/intercept_guias_busca.py oab
"""

from __future__ import annotations

import asyncio
import json
import sys

from playwright.async_api import async_playwright

from app.config import get_settings
from app.observability import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

SKIP = ("facebook", "google", "doubleclick", "trackcmp", "prism", "analytics", "clarity",
        ".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico", ".gif")


async def main(termo: str) -> None:
    settings = get_settings()
    out = settings.discovery_dump_dir
    out.mkdir(parents=True, exist_ok=True)
    xhrs = out / f"xhrs-guias-busca-{termo}.jsonl"
    xhrs.write_text("")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            storage_state=str(settings.tc_storage_state_path),
            user_agent=settings.tc_user_agent, locale="pt-BR",
        )
        page = await ctx.new_page()
        n = {"i": 0}

        async def on_response(resp):
            url = resp.url
            if any(h in url for h in SKIP) or "tecconcursos" not in url:
                return
            ct = resp.headers.get("content-type", "")
            if "json" not in ct.lower():
                return
            try:
                body = json.dumps(await resp.json(), ensure_ascii=False)[:40000]
            except Exception:
                return
            n["i"] += 1
            with xhrs.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"i": n["i"], "url": url, "post": resp.request.post_data, "body": body}, ensure_ascii=False) + "\n")
            log.info("xhr", i=n["i"], url=url)

        page.on("response", on_response)
        await page.goto(f"{settings.tc_base}/guias/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        # preenche a busca e dispara
        try:
            await page.fill('input[placeholder*="chave" i]', termo)
            await page.click('button:has-text("BUSCAR")')
        except Exception as e:  # noqa: BLE001
            log.warning("busca.fail", err=str(e))
        await page.wait_for_timeout(4000)
        html = out / f"guias-busca-{termo}.html"
        html.write_text(await page.content(), encoding="utf-8")
        log.info("done", xhrs=str(xhrs), html=str(html))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "oab"))
