"""Intercepta XHRs ao navegar para um caderno do TecConcursos.

Use para descobrir o endpoint REAL que serve a lista de IDs e qualquer
metadado. Salva todas as requisições em /state/discovery/xhr-{idx}.json.

uso: python scripts/intercept_caderno.py <caderno_id>
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from app.config import get_settings
from app.observability import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


async def main(caderno_id: int) -> None:
    settings = get_settings()
    out = settings.discovery_dump_dir
    out.mkdir(parents=True, exist_ok=True)
    xhrs = out / f"xhrs-caderno-{caderno_id}.jsonl"
    xhrs.write_text("")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            storage_state=str(settings.tc_storage_state_path),
            user_agent=settings.tc_user_agent,
            locale="pt-BR",
        )
        page = await ctx.new_page()
        idx = {"n": 0}

        async def on_response(resp):
            try:
                url = resp.url
                if "/api/" not in url:
                    return
                ct = resp.headers.get("content-type", "")
                body_preview = None
                if "json" in ct.lower():
                    try:
                        body = await resp.json()
                        body_preview = (
                            json.dumps(body, ensure_ascii=False)[:8000]
                        )
                    except Exception:
                        body_preview = (await resp.text())[:2000]
                else:
                    body_preview = f"[non-json content-type={ct}]"

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

        await page.goto(
            f"{settings.tc_base}/questoes/cadernos/{caderno_id}",
            wait_until="networkidle",
            timeout=30_000,
        )
        # Pequena espera extra pra pegar XHRs lazy
        await page.wait_for_timeout(3000)

        await browser.close()

    print(f"saved: {xhrs}")


if __name__ == "__main__":
    cid = int(sys.argv[1])
    asyncio.run(main(cid))
