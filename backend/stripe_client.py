"""Cliente fino do Stripe (sem SDK) — replica o padrão do witdev-platform-core.

Chamadas à API REST do Stripe via httpx com auth básica (secret key como user).
Inclui verificação de assinatura de webhook (esquema `t=...,v1=...`).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

import httpx

STRIPE_API_BASE = os.getenv("STRIPE_API_BASE", "https://api.stripe.com/v1")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_PRICE_ID_ANUAL = os.getenv("STRIPE_PRICE_ID_ANUAL", "")
PRECO_LABEL = os.getenv("STRIPE_PRICE_LABEL", "R$ 29,90/mês")
PRECO_LABEL_ANUAL = os.getenv("STRIPE_PRICE_LABEL_ANUAL", "R$ 298,80/ano")
# Versão da API que suporta ui_mode="elements".
STRIPE_API_VERSION = os.getenv("STRIPE_API_VERSION", "2026-05-27.dahlia")


class StripeError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Stripe {status_code}: {message}")


def stripe_configurado() -> bool:
    """True se há secret key + price configurados (checkout viável)."""
    return bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID)


async def stripe_request(method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Chamada à API do Stripe (form-encoded). `path` pode trazer query string."""
    if not STRIPE_SECRET_KEY:
        raise StripeError(500, "STRIPE_SECRET_KEY não configurado")
    url = f"{STRIPE_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.request(
            method,
            url,
            data={k: str(v) for k, v in (data or {}).items()},
            auth=(STRIPE_SECRET_KEY, ""),
            headers={
                "Accept": "application/json",
                **({"Stripe-Version": STRIPE_API_VERSION} if STRIPE_API_VERSION else {}),
            },
        )
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            msg = resp.text
        raise StripeError(resp.status_code, msg)
    return resp.json()


def verificar_assinatura_webhook(
    payload: bytes,
    sig_header: str,
    secret: str | None = None,
    tolerance: int = 300,
) -> bool:
    """Valida o header `Stripe-Signature` (HMAC-SHA256 de `{t}.{payload}`)."""
    secret = secret if secret is not None else STRIPE_WEBHOOK_SECRET
    if not secret or not sig_header:
        return False
    try:
        partes = dict(
            p.split("=", 1) for p in sig_header.split(",") if "=" in p
        )
        t = partes.get("t")
        v1 = partes.get("v1")
        if not t or not v1:
            return False
        assinado = t.encode("utf-8") + b"." + payload
        esperado = hmac.new(secret.encode("utf-8"), assinado, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperado, v1):
            return False
        if tolerance and abs(time.time() - int(t)) > tolerance:
            return False
        return True
    except (ValueError, TypeError):
        return False
