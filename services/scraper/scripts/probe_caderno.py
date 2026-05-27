"""Descobre o total de questões de um caderno via binary search no endpoint
GET /api/cadernos/{cid}/questoes/{N}.

uso: python scripts/probe_caderno.py <caderno_id>
"""

from __future__ import annotations

import asyncio
import sys

from app.auth import load_cookies_for_httpx
from app.client import TcClient


async def main(caderno_id: int) -> None:
    cookies = load_cookies_for_httpx()
    async with TcClient(cookies) as c:
        # Probe exponential first
        lo, hi = 1, 1
        while True:
            r = await c.get(
                f"/api/cadernos/{caderno_id}/questoes/{hi}",
                referer=f"https://www.tecconcursos.com.br/questoes/cadernos/{caderno_id}",
            )
            if r.status_code == 200:
                lo = hi
                hi *= 2
                if hi > 100_000:
                    break
            else:
                break
        # binary search lo (200 OK) ↔ hi (not 200)
        print(f"phase1: lo={lo} hi={hi}")
        while hi - lo > 1:
            mid = (lo + hi) // 2
            r = await c.get(
                f"/api/cadernos/{caderno_id}/questoes/{mid}",
                referer=f"https://www.tecconcursos.com.br/questoes/cadernos/{caderno_id}",
            )
            if r.status_code == 200:
                lo = mid
            else:
                hi = mid
            print(f"  probe N={mid} → {r.status_code}; lo={lo} hi={hi}")
        print(f"TOTAL questoes do caderno {caderno_id}: {lo}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
