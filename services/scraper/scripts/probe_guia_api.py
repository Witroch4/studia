"""Sonda a API caderno-guia do TC com a sessão httpx autenticada.

uso: python scripts/probe_guia_api.py 6818
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.auth import load_cookies_for_httpx
from app.client import TcClient


async def main(guia_id: int) -> None:
    cookies = load_cookies_for_httpx()
    async with TcClient(cookies) as client:
        r = await client._client.get(  # noqa: SLF001
            f"/api/caderno-guia/listar-pelo-guia/{guia_id}",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.tecconcursos.com.br/guias/oab-2026/nacional-unificado-oab/-/-",
            },
        )
        print("status:", r.status_code, "ct:", r.headers.get("content-type"))
        data = r.json()
        out = f"/state/discovery/caderno-guia-{guia_id}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("saved:", out)
        print(json.dumps(data, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
