"""Sonda endpoints TC para descobrir como listar cadernos de uma pasta.

Uso (dentro do container scraper):
    python scripts/probe_pasta.py 7024498
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.auth import load_cookies_for_httpx
from app.client import TcClient


async def main(pasta_id: int) -> None:
    cookies = load_cookies_for_httpx()
    tentativas = [
        ("GET", f"/api/pastas/{pasta_id}", None),
        ("GET", f"/api/pastas/{pasta_id}/cadernos", None),
        ("GET", f"/api/cadernos?idPasta={pasta_id}", None),
        ("GET", f"/questoes/pastas/{pasta_id}", None),
    ]
    async with TcClient(cookies) as client:
        for method, path, body in tentativas:
            try:
                r = await client._client.request(  # noqa: SLF001
                    method,
                    path,
                    headers={
                        "Accept": "application/json, text/html, */*",
                        "Referer": f"https://www.tecconcursos.com.br/questoes/pastas/{pasta_id}",
                    },
                )
                preview = r.text[:600].replace("\n", " ")
                print(f"\n=== {method} {path} -> {r.status_code}")
                print(f"content-type: {r.headers.get('content-type')}")
                print(f"body[:600]: {preview}")
                if "json" in (r.headers.get("content-type") or ""):
                    try:
                        data = r.json()
                        print("json keys:", list(data)[:30] if isinstance(data, dict) else f"list len={len(data)}")
                        out = f"/state/discovery/pasta-{pasta_id}-{path.strip('/').replace('/', '_').replace('?', '_')}.json"
                        with open(out, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        print("saved:", out)
                    except Exception as e:  # noqa: BLE001
                        print("json parse fail:", e)
            except Exception as e:  # noqa: BLE001
                print(f"\n=== {method} {path} -> EXC {type(e).__name__}: {e}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
