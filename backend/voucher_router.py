"""Vouchers PRO — geração (admin), controle (admin) e resgate (usuário).

Um voucher concede acesso PRO por `dias` SEM passar pelo Stripe. Gerado pelo
admin, resgatável uma única vez por uma única conta. Ao resgatar, o acesso é
estendido a partir da data mais distante já vigente (assinatura Stripe ou voucher
anterior) — nunca desperdiça dias.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_admin, require_user
from database import get_db
from entitlements import assinatura_ativa, voucher_pro_ativo
from models import Voucher

router = APIRouter(prefix="/api/vouchers", tags=["vouchers"])

_UTC = timezone.utc

# Alfabeto sem caracteres ambíguos (0/O, 1/I/L) — códigos fáceis de ditar.
_ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODIGO_RE = re.compile(r"^[A-Z0-9-]{4,32}$")


def _gerar_codigo() -> str:
    """Código no formato PRO-XXXX-XXXX (alfabeto sem ambíguos)."""
    bloco = lambda: "".join(secrets.choice(_ALFABETO) for _ in range(4))
    return f"PRO-{bloco()}-{bloco()}"


def _voucher_dict(v: Voucher, email: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": v.id,
        "codigo": v.codigo,
        "dias": v.dias,
        "status": "usado" if v.resgatado_por_uid else "disponivel",
        "resgatado_por_uid": v.resgatado_por_uid,
        "resgatado_por_email": email,
        "resgatado_em": v.resgatado_em.isoformat() if v.resgatado_em else None,
        "pro_ate": v.pro_ate.isoformat() if v.pro_ate else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


class GerarVouchersIn(BaseModel):
    dias: int = Field(default=365, ge=1, le=3650)
    quantidade: int = Field(default=1, ge=1, le=200)
    codigo: Optional[str] = None  # se informado, gera UM voucher com esse código


@router.post("")
async def gerar_vouchers(
    body: GerarVouchersIn,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Gera N vouchers aleatórios, ou 1 voucher com código custom."""
    criados: list[Voucher] = []

    if body.codigo:
        codigo = body.codigo.strip().upper()
        if not _CODIGO_RE.match(codigo):
            raise HTTPException(400, "código inválido (use 4–32 letras/números/hífen)")
        existe = (
            await db.execute(select(Voucher.id).where(Voucher.codigo == codigo))
        ).first()
        if existe:
            raise HTTPException(409, "já existe um voucher com esse código")
        v = Voucher(codigo=codigo, dias=body.dias, criado_por_uid=admin.id)
        db.add(v)
        criados.append(v)
    else:
        # Gera códigos únicos; em colisão (raríssima) tenta de novo.
        gerados: set[str] = set()
        while len(gerados) < body.quantidade:
            codigo = _gerar_codigo()
            if codigo in gerados:
                continue
            existe = (
                await db.execute(select(Voucher.id).where(Voucher.codigo == codigo))
            ).first()
            if existe:
                continue
            gerados.add(codigo)
            v = Voucher(codigo=codigo, dias=body.dias, criado_por_uid=admin.id)
            db.add(v)
            criados.append(v)

    await db.commit()
    for v in criados:
        await db.refresh(v)
    return {"criados": [_voucher_dict(v) for v in criados]}


@router.get("")
async def listar_vouchers(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Controle: todos os vouchers + email da conta que resgatou (mais novos primeiro)."""
    vouchers = (
        await db.execute(select(Voucher).order_by(Voucher.created_at.desc(), Voucher.id.desc()))
    ).scalars().all()

    uids = {v.resgatado_por_uid for v in vouchers if v.resgatado_por_uid}
    emails: dict[str, str] = {}
    if uids:
        rows = (
            await db.execute(
                text('SELECT id, email FROM "user" WHERE id = ANY(:uids)'),
                {"uids": list(uids)},
            )
        ).mappings().all()
        emails = {r["id"]: r["email"] for r in rows}

    total = len(vouchers)
    usados = sum(1 for v in vouchers if v.resgatado_por_uid)
    return {
        "total": total,
        "usados": usados,
        "disponiveis": total - usados,
        "vouchers": [
            _voucher_dict(v, emails.get(v.resgatado_por_uid or "")) for v in vouchers
        ],
    }


class ResgatarIn(BaseModel):
    codigo: str


@router.post("/resgatar")
async def resgatar_voucher(
    body: ResgatarIn,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Resgata um voucher para a conta atual, estendendo o PRO a partir da data vigente."""
    codigo = body.codigo.strip().upper()
    if not codigo:
        raise HTTPException(400, "informe um código")

    v = (
        await db.execute(select(Voucher).where(Voucher.codigo == codigo))
    ).scalars().first()
    if v is None:
        raise HTTPException(404, "código não encontrado")
    if v.resgatado_por_uid:
        raise HTTPException(409, "este código já foi utilizado")

    # Estende a partir da data mais distante já vigente (Stripe ou voucher anterior).
    base = datetime.now(_UTC)
    ass = await assinatura_ativa(db, user.id)
    if ass and ass.current_period_end:
        fim = ass.current_period_end
        if fim.tzinfo is None:
            fim = fim.replace(tzinfo=_UTC)
        if fim > base:
            base = fim
    voucher_ate = await voucher_pro_ativo(db, user.id)
    if voucher_ate and voucher_ate > base:
        base = voucher_ate

    pro_ate = base + timedelta(days=v.dias)
    v.resgatado_por_uid = user.id
    v.resgatado_em = datetime.now(_UTC)
    v.pro_ate = pro_ate
    await db.commit()

    return {"ok": True, "dias": v.dias, "pro_ate": pro_ate.isoformat()}
