from __future__ import annotations

from app.auth import load_cookies_for_httpx
from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger

log = get_logger(__name__)


async def discover_caderno_total(caderno_id: int, *, max_probe: int = 100_000) -> int:
    cookies = load_cookies_for_httpx()
    async with TcClient(cookies) as client:
        lo, hi = 0, 1
        while hi <= max_probe and await _position_exists(client, caderno_id, hi):
            lo = hi
            hi *= 2

        hi = min(hi, max_probe)
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if await _position_exists(client, caderno_id, mid):
                lo = mid
            else:
                hi = mid

    if lo <= 0:
        raise ValueError(f"could not discover total for caderno={caderno_id}")
    log.info("tc_total.discovered", caderno_id=caderno_id, total=lo)
    return lo


async def _position_exists(client: TcClient, caderno_id: int, position: int) -> bool:
    r = await client.get(
        f"/api/cadernos/{caderno_id}/questoes/{position}",
        referer=f"{get_settings().tc_base}/questoes/cadernos/{caderno_id}",
    )
    return r.status_code == 200
