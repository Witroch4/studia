"""Intercepta XHRs ao navegar para uma pasta do TecConcursos.

Descobre o endpoint REAL que lista os cadernos de uma pasta (Minhas pastas).
Salva requisições em /state/discovery/xhrs-pasta-{id}.jsonl e o HTML final.

uso: python scripts/intercept_pasta.py <pasta_id> [--relogin]
"""

from __future__ import annotations

import asyncio
import json
import sys

from playwright.async_api import async_playwright

from app.auth import login_and_save_state
from app.config import get_settings
from app.observability import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

STATIC_HINTS = (".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico", ".gif", "fonts.googleapis")


async def main(pasta_id: int, relogin: bool) -> None:
    settings = get_settings()
    out = settings.discovery_dump_dir
    out.mkdir(parents=True, exist_ok=True)
    xhrs = out / f"xhrs-pasta-{pasta_id}.jsonl"
    xhrs.write_text("")

    if relogin:
        await login_and_save_state(headless=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            storage_state=str(settings.tc_storage_state_path),
            user_agent=settings.tc_user_agent,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1920, "height": 1080},
        )
        page = await ctx.new_page()
        idx = {"n": 0}

        async def on_response(resp):
            try:
                url = resp.url
                if any(h in url for h in STATIC_HINTS):
                    return
                if "tecconcursos" not in url:
                    return
                ct = resp.headers.get("content-type", "")
                if "json" in ct.lower():
                    try:
                        body = await resp.json()
                        body_preview = json.dumps(body, ensure_ascii=False)[:20000]
                    except Exception:
                        body_preview = (await resp.text())[:2000]
                elif "html" in ct.lower():
                    body_preview = f"[html len={len(await resp.text())}]"
                else:
                    body_preview = f"[content-type={ct}]"

                idx["n"] += 1
                rec = {
                    "i": idx["n"],
                    "method": resp.request.method,
                    "url": url,
                    "status": resp.status,
                    "content_type": ct,
                    "request_post_data": resp.request.post_data,
                    "body": body_preview,
                }
                with xhrs.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.info("xhr", i=idx["n"], method=rec["method"], url=url, status=resp.status)
            except Exception as e:  # noqa: BLE001
                log.warning("xhr.fail", err=str(e))

        page.on("response", on_response)

        url = f"{settings.tc_base}/questoes/pastas/{pasta_id}"
        log.info("goto", url=url)
        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            log.warning("networkidle.timeout")
        await asyncio.sleep(3)

        html = await page.content()
        html_path = out / f"pasta-{pasta_id}.html"
        html_path.write_text(html, encoding="utf-8")
        log.info("done", xhrs=str(xhrs), html=str(html_path), final_url=page.url)

        await browser.close()


if __name__ == "__main__":
    pid = int(sys.argv[1])
    relogin = "--relogin" in sys.argv
    asyncio.run(main(pid, relogin))
