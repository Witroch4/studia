"""Assinatura (Stripe) — checkout, webhook e status.

Fluxo: usuário grátis abre `/api/billing/checkout` → Checkout Session do Stripe
(modo subscription) → paga → Stripe chama `/api/billing/webhook` → marcamos a
assinatura ativa. A partir daí o limite diário de questões some (ilimitado).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_user
from database import get_db
from entitlements import assinatura_ativa, resumo_limite
from models import Assinatura
from stripe_client import (
    PRECO_LABEL,
    STRIPE_PRICE_ID,
    STRIPE_PUBLISHABLE_KEY,
    StripeError,
    stripe_configurado,
    stripe_request,
    verificar_assinatura_webhook,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])

FRONTEND_URL = (
    os.getenv("FRONTEND_URL")
    or os.getenv("BETTER_AUTH_URL")
    or "http://localhost:3000"
).rstrip("/")


def _assinatura_dict(a: Assinatura) -> dict[str, Any]:
    return {
        "status": a.status,
        "price_id": a.price_id,
        "cancel_at_period_end": a.cancel_at_period_end,
        "current_period_end": a.current_period_end.isoformat() if a.current_period_end else None,
    }


@router.get("/status")
async def billing_status(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ass = await assinatura_ativa(db, user.id)
    ilimitado = user.is_admin or ass is not None
    return {
        "plano": "pro" if ilimitado else "free",
        "is_admin": user.is_admin,
        "ilimitado": ilimitado,
        "assinatura": _assinatura_dict(ass) if ass else None,
        "limite": await resumo_limite(db, user),
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "preco_label": PRECO_LABEL,
        "stripe_configurado": stripe_configurado(),
    }


async def _garantir_customer(db: AsyncSession, user: CurrentUser) -> str:
    """Acha (ou cria) o customer Stripe do usuário e persiste num placeholder."""
    row = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == user.id, Assinatura.stripe_customer_id.isnot(None))
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if row and row.stripe_customer_id:
        return row.stripe_customer_id

    cust = await stripe_request(
        "POST",
        "/customers",
        {"email": user.email, "name": user.name, "metadata[usuario_uid]": user.id},
    )
    cid = cust["id"]
    db.add(Assinatura(usuario_uid=user.id, stripe_customer_id=cid, status="incomplete"))
    await db.commit()
    return cid


@router.post("/checkout")
async def criar_checkout(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado (faltam chaves Stripe)")
    if user.is_admin or await assinatura_ativa(db, user.id):
        raise HTTPException(400, "você já tem acesso ilimitado")

    try:
        customer_id = await _garantir_customer(db, user)
        session = await stripe_request(
            "POST",
            "/checkout/sessions",
            {
                "mode": "subscription",
                "line_items[0][price]": STRIPE_PRICE_ID,
                "line_items[0][quantity]": "1",
                "customer": customer_id,
                "client_reference_id": user.id,
                "metadata[usuario_uid]": user.id,
                "subscription_data[metadata][usuario_uid]": user.id,
                "allow_promotion_codes": "true",
                "success_url": f"{FRONTEND_URL}/assinar?status=sucesso&session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{FRONTEND_URL}/assinar?status=cancelado",
            },
        )
    except StripeError as exc:
        raise HTTPException(502, f"Stripe: {exc.message}") from exc

    return {"url": session["url"], "id": session["id"]}


async def _upsert_sub(
    db: AsyncSession,
    sub: dict[str, Any],
    uid_fallback: Optional[str] = None,
    customer_fallback: Optional[str] = None,
) -> None:
    """Cria/atualiza a Assinatura local a partir de um objeto subscription do Stripe."""
    sub_id = sub.get("id")
    if not sub_id:
        return
    metadata = sub.get("metadata") or {}
    uid = metadata.get("usuario_uid") or uid_fallback
    itens = (sub.get("items") or {}).get("data") or []
    price_id = (itens[0].get("price") or {}).get("id") if itens else None
    cpe = sub.get("current_period_end")
    customer = sub.get("customer") or customer_fallback

    # 1) por subscription_id; 2) placeholder do mesmo usuário (criado no checkout)
    row = (
        await db.execute(select(Assinatura).where(Assinatura.stripe_subscription_id == sub_id))
    ).scalars().first()
    if row is None and uid:
        row = (
            await db.execute(
                select(Assinatura)
                .where(Assinatura.usuario_uid == uid)
                .order_by(Assinatura.updated_at.desc())
            )
        ).scalars().first()
    if row is None:
        row = Assinatura(usuario_uid=uid or "")
        db.add(row)

    if uid:
        row.usuario_uid = uid
    row.stripe_subscription_id = sub_id
    if customer:
        row.stripe_customer_id = customer
    if sub.get("status"):
        row.status = sub["status"]
    if price_id:
        row.price_id = price_id
    row.cancel_at_period_end = bool(sub.get("cancel_at_period_end", False))
    if cpe:
        row.current_period_end = datetime.fromtimestamp(int(cpe), tz=timezone.utc)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not verificar_assinatura_webhook(payload, sig):
        raise HTTPException(400, "assinatura de webhook inválida")

    try:
        event = json.loads(payload)
    except ValueError:
        raise HTTPException(400, "payload inválido")

    tipo = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    if tipo == "checkout.session.completed":
        sub_id = obj.get("subscription")
        uid = (obj.get("metadata") or {}).get("usuario_uid") or obj.get("client_reference_id")
        cust = obj.get("customer")
        if sub_id:
            try:
                sub = await stripe_request("GET", f"/subscriptions/{sub_id}")
                await _upsert_sub(db, sub, uid_fallback=uid, customer_fallback=cust)
            except StripeError:
                pass
    elif tipo.startswith("customer.subscription."):
        await _upsert_sub(db, obj)

    await db.commit()
    return {"received": True}
