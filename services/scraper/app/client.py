"""Cliente HTTP autenticado em TecConcursos.

Características:
- httpx async com http2
- Cookies da sessão (reusados de `storage_state.json`)
- Rate limit por janela (token bucket simples) + jitter
- Concurrency cap via Semaphore
- Tradução de respostas anômalas em exceções de domínio
- Referer e headers compatíveis com browser real
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx

from app.config import get_settings
from app.observability import get_logger
from app.schemas import AccessBlocked, CaptchaChallenge, RateLimited, SessionExpired

log = get_logger(__name__)


def _redact_proxy(url: str) -> str:
    """socks5h://user:pass@host:port → socks5h://user:***@host:port"""
    import re
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", url)


def classificar_resposta(r: httpx.Response) -> str | None:
    if r.status_code in (403, 451):
        return "acesso_negado"
    if r.status_code == 429:
        return "rate_limit"
    if r.status_code in (401, 452):
        # 401: Unauthorized — sessão expirou (pausa longa, cookies vencidos)
        # 452: TC retorna quando SESSÃO está queimada (anti-bot disfarçado)
        # Ambos resolvem com re-login.
        return "sessao_queimada"
    if r.status_code in (301, 302) and "/login" in r.headers.get("location", ""):
        return "sessao_expirou"
    # Apenas amostra leve do corpo para detectar HTML/captcha
    body_preview = ""
    try:
        body_preview = r.text[:512].lower()
    except Exception:
        pass
    if "captcha" in body_preview:
        return "captcha"
    if r.status_code == 200 and "<html" in body_preview and "login" in body_preview:
        return "sessao_zumbi"
    if r.status_code >= 500:
        return "servidor"
    return None


class TcClient:
    """Cliente assíncrono autenticado para a API REST do TecConcursos."""

    def __init__(self, cookies: dict[str, str]) -> None:
        settings = get_settings()
        self.base = settings.tc_base.rstrip("/")
        self.rate_per_sec = settings.tc_rate_per_sec
        self.sem = asyncio.Semaphore(settings.tc_max_concurrency)
        self._last_req = 0.0
        self._lock = asyncio.Lock()
        self._settings = settings
        self._req_count = 0

        client_kwargs: dict[str, Any] = dict(
            base_url=self.base,
            http2=True,
            cookies=cookies,
            timeout=httpx.Timeout(connect=10, read=30, write=10, pool=30),
            follow_redirects=False,
            headers={
                "User-Agent": settings.tc_user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.base,
            },
        )
        # Proxy residencial WitDev se configurado (rodar em SSH/datacenter)
        if settings.residential_proxy_url:
            client_kwargs["proxy"] = settings.residential_proxy_url
            log.info("tc.client.proxy_enabled", proxy=_redact_proxy(settings.residential_proxy_url))
        self._client = httpx.AsyncClient(**client_kwargs)

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_req
            s = self._settings

            if s.tc_human_mode:
                # Distribuição balanceada (alvo ~3h pras 876 reqs):
                # 75% short (3-7s) | 18% long-short (8-18s) | 5% pause (25-50s)
                # 2% break (60-120s) | burst-pause a cada N reqs (60-120s)
                self._req_count += 1
                roll = random.random()
                cum_break = s.tc_human_break_chance
                cum_pause = cum_break + s.tc_human_pause_chance
                cum_long = cum_pause + s.tc_human_long_chance
                if (
                    s.tc_human_burst_pause_every > 0
                    and self._req_count > 0
                    and self._req_count % s.tc_human_burst_pause_every == 0
                ):
                    wait = random.uniform(s.tc_human_burst_pause_min, s.tc_human_burst_pause_max)
                    log.info("throttle.burst_pause", n=self._req_count, wait_s=round(wait, 1))
                elif roll < cum_break:
                    wait = random.uniform(s.tc_human_break_min, s.tc_human_break_max)
                    log.info("throttle.coffee_break", wait_s=round(wait, 1))
                elif roll < cum_pause:
                    wait = random.uniform(s.tc_human_pause_min, s.tc_human_pause_max)
                elif roll < cum_long:
                    wait = random.uniform(s.tc_human_long_min, s.tc_human_long_max)
                else:
                    wait = random.uniform(s.tc_human_short_min, s.tc_human_short_max)
            else:
                min_interval = 1.0 / max(self.rate_per_sec, 0.01)
                jitter = random.uniform(-0.3, 0.7) * min_interval
                wait = max(0.0, min_interval + jitter - elapsed)

            if wait > 0:
                await asyncio.sleep(wait)
            self._last_req = time.monotonic()

    def _build_headers(self, referer: str | None, content_type: str | None) -> dict[str, str]:
        h: dict[str, str] = {}
        if referer:
            h["Referer"] = referer
        if content_type:
            h["Content-Type"] = content_type
        return h

    def _check(self, r: httpx.Response) -> None:
        tag = classificar_resposta(r)
        if tag == "rate_limit":
            retry_after = int(r.headers.get("Retry-After", "60"))
            raise RateLimited(retry_after)
        if tag in {"sessao_expirou", "sessao_zumbi", "sessao_queimada"}:
            raise SessionExpired(f"sessão inválida ({tag})")
        if tag == "captcha":
            raise CaptchaChallenge("captcha detectado")
        if tag == "acesso_negado":
            raise AccessBlocked(f"status {r.status_code}")

    async def get(self, path: str, *, referer: str | None = None) -> httpx.Response:
        async with self.sem:
            await self._throttle()
            r = await self._client.get(path, headers=self._build_headers(referer, None))
            self._check(r)
            return r

    async def post(
        self,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        referer: str | None = None,
    ) -> httpx.Response:
        async with self.sem:
            await self._throttle()
            r = await self._client.post(
                path,
                json=json_body,
                headers=self._build_headers(referer, "application/json"),
            )
            self._check(r)
            return r

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TcClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
