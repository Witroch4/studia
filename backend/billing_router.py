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
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_user
from database import get_db
from entitlements import acesso_pro_ativo, assinatura_ativa, resumo_limite, voucher_pro_ativo
from models import Assinatura
from stripe_client import (
    PRECO_LABEL,
    PRECO_LABEL_ANUAL,
    STRIPE_PRICE_ID,
    STRIPE_PRICE_ID_ANUAL,
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
    voucher_ate = await voucher_pro_ativo(db, user.id)
    ilimitado = user.is_admin or ass is not None or voucher_ate is not None
    tem_customer = (
        await db.execute(
            select(Assinatura.id).where(
                Assinatura.usuario_uid == user.id,
                Assinatura.stripe_customer_id.isnot(None),
            )
        )
    ).first() is not None
    return {
        "plano": "pro" if ilimitado else "free",
        "is_admin": user.is_admin,
        "ilimitado": ilimitado,
        "assinatura": _assinatura_dict(ass) if ass else None,
        "voucher_pro_ate": voucher_ate.isoformat() if voucher_ate else None,
        "limite": await resumo_limite(db, user),
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "preco_label": PRECO_LABEL,
        "preco_label_anual": PRECO_LABEL_ANUAL,
        "stripe_configurado": stripe_configurado(),
        "tem_customer": tem_customer,
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


class CheckoutBody(BaseModel):
    intervalo: str = "month"  # "month" | "year"


@router.post("/checkout")
async def criar_checkout(
    body: CheckoutBody = CheckoutBody(),
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado (faltam chaves Stripe)")
    if user.is_admin or await acesso_pro_ativo(db, user.id):
        raise HTTPException(400, "você já tem acesso ilimitado")

    intervalo = "year" if body.intervalo == "year" else "month"
    price = STRIPE_PRICE_ID_ANUAL if intervalo == "year" else STRIPE_PRICE_ID
    if not price:
        raise HTTPException(503, f"plano {intervalo} não configurado")

    try:
        customer_id = await _garantir_customer(db, user)
        session = await stripe_request(
            "POST",
            "/checkout/sessions",
            {
                "ui_mode": "elements",
                "mode": "subscription",
                "line_items[0][price]": price,
                "line_items[0][quantity]": "1",
                "customer": customer_id,
                "client_reference_id": user.id,
                "metadata[usuario_uid]": user.id,
                "subscription_data[metadata][usuario_uid]": user.id,
                "saved_payment_method_options[payment_method_save]": "enabled",
                "return_url": (
                    f"{FRONTEND_URL}/assinar?status=sucesso"
                    "&session_id={CHECKOUT_SESSION_ID}"
                ),
            },
        )
    except StripeError as exc:
        raise HTTPException(502, f"Stripe: {exc.message}") from exc

    return {"client_secret": session["client_secret"], "intervalo": intervalo}


@router.post("/portal")
async def abrir_portal(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado")
    row = (
        await db.execute(
            select(Assinatura)
            .where(
                Assinatura.usuario_uid == user.id,
                Assinatura.stripe_customer_id.isnot(None),
            )
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if not row or not row.stripe_customer_id:
        raise HTTPException(400, "nenhuma assinatura para gerenciar")

    try:
        sess = await stripe_request(
            "POST",
            "/billing_portal/sessions",
            {
                "customer": row.stripe_customer_id,
                "return_url": f"{FRONTEND_URL}/conta",
            },
        )
    except StripeError as exc:
        raise HTTPException(502, f"Stripe: {exc.message}") from exc
    return {"url": sess["url"]}


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
