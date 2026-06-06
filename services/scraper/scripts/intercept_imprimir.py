"""Captura a request que o botão IMPRIMIR CADERNO dispara."""

from __future__ import annotations

import asyncio, json, sys
from pathlib import Path

from playwright.async_api import async_playwright

from app.config import get_settings
from app.observability import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


async def main(caderno_id: int) -> None:
    s = get_settings()
    out = s.discovery_dump_dir
    out.mkdir(parents=True, exist_ok=True)
    log_file = out / f"imprimir-{caderno_id}.jsonl"
    log_file.write_text("")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            storage_state=str(s.tc_storage_state_path),
            user_agent=s.tc_user_agent,
            accept_downloads=True,
        )
        page = await ctx.new_page()

        async def on_req(req):
            try:
                post = req.post_data
            except Exception:
                post = "[binary]"
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "request",
                    "method": req.method,
                    "url": req.url,
                    "headers": dict(req.headers),
                    "post_data": post,
                }, ensure_ascii=False) + "\n")

        async def on_resp(resp):
            try:
                ct = resp.headers.get("content-type", "")
                preview = None
                if "html" in ct or "json" in ct:
                    preview = (await resp.text())[:2000]
                with log_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "type": "response",
                        "url": resp.url,
                        "status": resp.status,
                        "content_type": ct,
                        "preview": preview,
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass

        page.on("request", on_req)
        page.on("response", on_resp)

        url = f"{s.tc_base}/questoes/cadernos/{caderno_id}/imprimir"
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(2500)

        # Snapshot do form pra debugar caso seletor mude
        form_html = await page.content()
        (out / f"imprimir-form-{caderno_id}.html").write_text(form_html, encoding="utf-8")
        log.info("form.captured", url=page.url, title=await page.title())

        # Lista todos os botões da página
        buttons = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'))
              .map(b => ({tag: b.tagName, text: (b.innerText||b.value||'').trim().slice(0,80), id: b.id, cls: b.className.slice(0,80)}))
        """)
        log.info("buttons", count=len(buttons), sample=buttons[:20])

        new_page = page  # fallback se não abrir popup

        # Salva HTML final do print
        html = await new_page.content()
        html_path = out / f"imprimir-{caderno_id}-pagina1.html"
        html_path.write_text(html, encoding="utf-8")
        log.info("html.saved", file=str(html_path), bytes=len(html))
        print(f"URL final do print: {new_page.url}")
        print(f"HTML salvo: {html_path}")
        print(f"Log de requests: {log_file}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
