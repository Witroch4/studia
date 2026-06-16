"""Painel admin de assinaturas — visão geral, lista de usuários e gestão.

Tudo aqui é admin-only. Leitura rápida do DB local (lista/overview) e chamadas
ao Stripe ao vivo apenas no detalhe de um usuário e nas ações (cancelar/sincronizar).
Conceder Pro manual reaproveita o modelo Voucher (auto-resgatado na conta).
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_admin
from billing_router import _upsert_sub
from database import get_db
from models import Assinatura, Voucher
from stripe_client import (
    STRIPE_PRICE_ID,
    PRECO_LABEL,
    StripeError,
    stripe_configurado,
    stripe_request,
)

router = APIRouter(prefix="/api/admin/billing", tags=["admin-billing"])

_UTC = timezone.utc
_ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Cache em memória do valor unitário do preço (centavos) p/ MRR. None = ainda não buscado.
_preco_cache: dict[str, Any] = {"centavos": None, "moeda": "brl"}


def _gerar_codigo() -> str:
    bloco = lambda: "".join(secrets.choice(_ALFABETO) for _ in range(4))
    return f"ADM-{bloco()}-{bloco()}"


def _label_para_centavos(label: str) -> Optional[int]:
    """Extrai centavos de um rótulo tipo 'R$ 29,90/mês' (fallback do MRR)."""
    m = re.search(r"(\d+)[.,](\d{2})", label)
    if m:
        return int(m.group(1)) * 100 + int(m.group(2))
    m = re.search(r"(\d+)", label)
    return int(m.group(1)) * 100 if m else None


async def _preco_centavos() -> tuple[Optional[int], str]:
    """Valor unitário do preço (centavos, moeda). Stripe 1×, cacheado; fallback no label."""
    if _preco_cache["centavos"] is not None:
        return _preco_cache["centavos"], _preco_cache["moeda"]
    if stripe_configurado() and STRIPE_PRICE_ID:
        try:
            preco = await stripe_request("GET", f"/prices/{STRIPE_PRICE_ID}")
            if preco.get("unit_amount") is not None:
                _preco_cache["centavos"] = int(preco["unit_amount"])
                _preco_cache["moeda"] = preco.get("currency", "brl")
                return _preco_cache["centavos"], _preco_cache["moeda"]
        except StripeError:
            pass
    return _label_para_centavos(PRECO_LABEL), "brl"


# ─── Overview ───────────────────────────────────────────────────

@router.get("/overview")
async def overview(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (usuario_uid) usuario_uid, status, current_period_end
                    FROM assinaturas
                    ORDER BY usuario_uid, updated_at DESC
                )
                SELECT
                    count(*) FILTER (
                        WHERE status IN ('active','trialing')
                          AND (current_period_end IS NULL OR current_period_end > now())
                    ) AS ativos,
                    count(*) FILTER (WHERE status = 'past_due') AS atraso,
                    count(*) FILTER (
                        WHERE status IN ('canceled','unpaid','incomplete_expired')
                    ) AS cancelados
                FROM latest
                """
            )
        )
    ).mappings().first()
    ativos = int(row["ativos"] or 0)
    atraso = int(row["atraso"] or 0)
    cancelados = int(row["cancelados"] or 0)

    total_usuarios = int(
        (await db.execute(text('SELECT count(*) FROM "user"'))).scalar() or 0
    )
    admins = int(
        (await db.execute(text(
            "SELECT count(*) FROM \"user\" WHERE role = 'admin'"
        ))).scalar() or 0
    )
    pro_voucher = int(
        (await db.execute(text(
            """
            SELECT count(DISTINCT v.resgatado_por_uid)
            FROM vouchers v
            WHERE v.pro_ate > now()
              AND v.resgatado_por_uid IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM assinaturas a
                  WHERE a.usuario_uid = v.resgatado_por_uid
                    AND a.status IN ('active','trialing')
                    AND (a.current_period_end IS NULL OR a.current_period_end > now())
              )
            """
        ))).scalar() or 0
    )
    gratis = max(0, total_usuarios - ativos - pro_voucher - admins)

    centavos, moeda = await _preco_centavos()
    mrr_centavos = (centavos or 0) * ativos

    return {
        "total_usuarios": total_usuarios,
        "ativos": ativos,
        "atraso": atraso,
        "cancelados": cancelados,
        "pro_voucher": pro_voucher,
        "admins": admins,
        "gratis": gratis,
        "preco_centavos": centavos,
        "moeda": moeda,
        "mrr_centavos": mrr_centavos,
        "stripe_configurado": stripe_configurado(),
    }


# ─── Lista de usuários ──────────────────────────────────────────

@router.get("/usuarios")
async def listar_usuarios(
    q: Optional[str] = None,
    plano: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    like = f"%{q.strip()}%" if q and q.strip() else None
    plano_f = plano if plano in {"admin", "pro_stripe", "pro_voucher", "free"} else None

    rows = (
        await db.execute(
            text(
                """
                SELECT * FROM (
                    SELECT
                        u.id, u.email, u.name,
                        COALESCE(u.role,'user')   AS role,
                        COALESCE(u.banned,false)  AS banned,
                        a.status, a.current_period_end, a.cancel_at_period_end,
                        a.stripe_customer_id, a.stripe_subscription_id,
                        v.pro_ate,
                        CASE
                            WHEN COALESCE(u.role,'user') = 'admin' THEN 'admin'
                            WHEN a.status IN ('active','trialing')
                                 AND (a.current_period_end IS NULL OR a.current_period_end > now())
                                 THEN 'pro_stripe'
                            WHEN v.pro_ate > now() THEN 'pro_voucher'
                            ELSE 'free'
                        END AS plano,
                        count(*) OVER() AS total_rows
                    FROM "user" u
                    LEFT JOIN LATERAL (
                        SELECT * FROM assinaturas
                        WHERE usuario_uid = u.id
                        ORDER BY updated_at DESC LIMIT 1
                    ) a ON true
                    LEFT JOIN LATERAL (
                        SELECT max(pro_ate) AS pro_ate FROM vouchers
                        WHERE resgatado_por_uid = u.id
                    ) v ON true
                ) t
                WHERE (CAST(:like AS varchar) IS NULL OR t.email ILIKE :like OR t.name ILIKE :like)
                  AND (CAST(:plano AS varchar) IS NULL OR t.plano = :plano)
                ORDER BY t.email
                LIMIT :limit OFFSET :offset
                """
            ),
            {"like": like, "plano": plano_f, "limit": page_size, "offset": offset},
        )
    ).mappings().all()

    total = int(rows[0]["total_rows"]) if rows else 0
    usuarios = [
        {
            "uid": r["id"],
            "email": r["email"],
            "name": r["name"],
            "role": r["role"],
            "banned": bool(r["banned"]),
            "plano": r["plano"],
            "status": r["status"],
            "current_period_end": r["current_period_end"].isoformat() if r["current_period_end"] else None,
            "cancel_at_period_end": bool(r["cancel_at_period_end"]) if r["cancel_at_period_end"] is not None else False,
            "pro_ate": r["pro_ate"].isoformat() if r["pro_ate"] else None,
            "stripe_customer_id": r["stripe_customer_id"],
            "stripe_subscription_id": r["stripe_subscription_id"],
        }
        for r in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "usuarios": usuarios}


# ─── Detalhe (Stripe ao vivo) ───────────────────────────────────

async def _email_do_uid(db: AsyncSession, uid: str) -> Optional[dict[str, Any]]:
    return (
        await db.execute(
            text('SELECT id, email, name, COALESCE(role,\'user\') AS role, '
                 'COALESCE(banned,false) AS banned FROM "user" WHERE id = :uid'),
            {"uid": uid},
        )
    ).mappings().first()


@router.get("/usuarios/{uid}")
async def detalhe_usuario(
    uid: str,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    u = await _email_do_uid(db, uid)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")

    ass = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid)
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()

    vouchers = (
        await db.execute(
            select(Voucher).where(Voucher.resgatado_por_uid == uid).order_by(Voucher.pro_ate.desc())
        )
    ).scalars().all()

    stripe_subs: list[dict[str, Any]] = []
    stripe_erro: Optional[str] = None
    customer_id = ass.stripe_customer_id if ass else None
    if customer_id and stripe_configurado():
        try:
            resp = await stripe_request(
                "GET",
                f"/subscriptions?customer={customer_id}&status=all&limit=10&expand[]=data.latest_invoice",
            )
            for s in resp.get("data", []):
                inv = s.get("latest_invoice") or {}
                inv = inv if isinstance(inv, dict) else {}
                stripe_subs.append({
                    "id": s.get("id"),
                    "status": s.get("status"),
                    "cancel_at_period_end": bool(s.get("cancel_at_period_end")),
                    "current_period_end": s.get("current_period_end"),
                    "ultima_cobranca_centavos": inv.get("amount_paid"),
                    "payment_intent": inv.get("payment_intent"),
                    "moeda": inv.get("currency"),
                })
        except StripeError as exc:
            stripe_erro = exc.message

    return {
        "usuario": {
            "uid": u["id"], "email": u["email"], "name": u["name"],
            "role": u["role"], "banned": bool(u["banned"]),
        },
        "assinatura_local": {
            "status": ass.status if ass else None,
            "stripe_subscription_id": ass.stripe_subscription_id if ass else None,
            "stripe_customer_id": customer_id,
            "current_period_end": ass.current_period_end.isoformat() if ass and ass.current_period_end else None,
            "cancel_at_period_end": ass.cancel_at_period_end if ass else False,
            "cancel_motivo": ass.cancel_motivo if ass else None,
            "cancel_em": ass.cancel_em.isoformat() if ass and ass.cancel_em else None,
        } if ass else None,
        "vouchers": [
            {"codigo": v.codigo, "dias": v.dias,
             "pro_ate": v.pro_ate.isoformat() if v.pro_ate else None,
             "resgatado_em": v.resgatado_em.isoformat() if v.resgatado_em else None}
            for v in vouchers
        ],
        "stripe_subscriptions": stripe_subs,
        "stripe_erro": stripe_erro,
    }


# ─── Conceder Pro manual (via voucher auto-resgatado) ───────────

class ConcederIn(BaseModel):
    dias: int = Field(default=365, ge=1, le=3650)


@router.post("/usuarios/{uid}/conceder")
async def conceder_pro(
    uid: str,
    body: ConcederIn,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    u = await _email_do_uid(db, uid)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")

    base = datetime.now(_UTC)
    ass = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid, Assinatura.status.in_(("active", "trialing")))
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if ass and ass.current_period_end:
        fim = ass.current_period_end
        if fim.tzinfo is None:
            fim = fim.replace(tzinfo=_UTC)
        if fim > base:
            base = fim
    maior_voucher = (
        await db.execute(
            select(Voucher.pro_ate)
            .where(Voucher.resgatado_por_uid == uid, Voucher.pro_ate.isnot(None))
            .order_by(Voucher.pro_ate.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if maior_voucher:
        mv = maior_voucher if maior_voucher.tzinfo else maior_voucher.replace(tzinfo=_UTC)
        if mv > base:
            base = mv

    pro_ate = base + timedelta(days=body.dias)
    v = Voucher(
        codigo=f"{_gerar_codigo()}-{secrets.token_hex(2).upper()}",
        dias=body.dias,
        criado_por_uid=admin.id,
        resgatado_por_uid=uid,
        resgatado_em=datetime.now(_UTC),
        pro_ate=pro_ate,
    )
    db.add(v)
    await db.commit()
    return {"ok": True, "dias": body.dias, "pro_ate": pro_ate.isoformat(), "codigo": v.codigo}


# ─── Cancelar (3 modos + banir opcional) ────────────────────────

class CancelarIn(BaseModel):
    modo: str = Field(default="fim_periodo")  # fim_periodo | imediato | imediato_reembolso
    motivo: Optional[str] = None
    banir: bool = False


async def _expirar_vouchers(db: AsyncSession, uid: str, agora: datetime) -> None:
    """Expira (pro_ate=agora) todos os vouchers vigentes do usuário."""
    await db.execute(
        update(Voucher)
        .where(Voucher.resgatado_por_uid == uid, Voucher.pro_ate > agora)
        .values(pro_ate=agora)
    )


@router.post("/usuarios/{uid}/cancelar")
async def cancelar(
    uid: str,
    body: CancelarIn,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cancela acesso PRO. Modos imediatos revogam LOCALMENTE (assinatura + vouchers),
    independem do Stripe — funcionam pra PRO via voucher e pra assinatura cujo customer
    Stripe não existe mais (ex.: criado em teste). O Stripe é tratado best-effort."""
    if body.modo not in {"fim_periodo", "imediato", "imediato_reembolso"}:
        raise HTTPException(400, "modo inválido")
    u = await _email_do_uid(db, uid)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")

    agora = datetime.now(_UTC)
    assinaturas = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid)
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().all()
    com_sub = next((a for a in assinaturas if a.stripe_subscription_id), None)

    reembolso: Optional[dict[str, Any]] = None
    stripe_aviso: Optional[str] = None

    # ── Stripe best-effort (só se houver sub + chaves) — nunca derruba o cancelamento
    if com_sub and com_sub.stripe_subscription_id and stripe_configurado():
        sub_id = com_sub.stripe_subscription_id
        try:
            if body.modo == "fim_periodo":
                sub = await stripe_request(
                    "POST", f"/subscriptions/{sub_id}", {"cancel_at_period_end": "true"}
                )
                com_sub.cancel_at_period_end = True
                cpe = sub.get("current_period_end")
                if cpe:
                    com_sub.current_period_end = datetime.fromtimestamp(int(cpe), tz=_UTC)
            else:
                if body.modo == "imediato_reembolso":
                    sub_atual = await stripe_request(
                        "GET", f"/subscriptions/{sub_id}?expand[]=latest_invoice"
                    )
                    inv = sub_atual.get("latest_invoice") or {}
                    inv = inv if isinstance(inv, dict) else {}
                    pi = inv.get("payment_intent")
                    if pi:
                        ref = await stripe_request("POST", "/refunds", {"payment_intent": pi})
                        reembolso = {"id": ref.get("id"), "centavos": ref.get("amount"), "status": ref.get("status")}
                    else:
                        stripe_aviso = "sem cobrança a reembolsar"
                await stripe_request("DELETE", f"/subscriptions/{sub_id}")
        except StripeError as exc:
            stripe_aviso = f"Stripe: {exc.message}"  # segue com a revogação local

    # ── Revogação LOCAL (independe do Stripe) p/ modos imediatos
    if body.modo in {"imediato", "imediato_reembolso"}:
        for a in assinaturas:
            if a.status in ("active", "trialing"):
                a.status = "canceled"
                a.current_period_end = agora
                a.cancel_at_period_end = False  # já cancelou de vez: não "cancela no fim"
        await _expirar_vouchers(db, uid, agora)

    # ── fim_periodo: marca cancel_at_period_end LOCALMENTE também (independe do
    #    Stripe — cobre customer de teste/inexistente no live, em que a chamada
    #    Stripe falha e nada seria persistido). Mantém acesso até o fim do período.
    if body.modo == "fim_periodo":
        for a in assinaturas:
            if a.status in ("active", "trialing"):
                a.cancel_at_period_end = True

    alvo = com_sub or (assinaturas[0] if assinaturas else None)
    if alvo:
        alvo.cancel_motivo = body.motivo
        alvo.cancel_admin_uid = admin.id
        alvo.cancel_em = agora

    banido = False
    if body.banir:
        await db.execute(
            text('UPDATE "user" SET banned = true WHERE id = :uid'), {"uid": uid}
        )
        banido = True

    await db.commit()
    return {"ok": True, "modo": body.modo, "reembolso": reembolso, "banido": banido, "stripe_aviso": stripe_aviso}


# ─── Editar tempo (define a validade do PRO local) ──────────────

class EditarTempoIn(BaseModel):
    dias: Optional[int] = Field(default=None, ge=0, le=3650)  # validade a partir de agora; 0 = revoga
    pro_ate: Optional[str] = None  # alternativa: data ISO exata


@router.post("/usuarios/{uid}/editar-tempo")
async def editar_tempo(
    uid: str,
    body: EditarTempoIn,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Define a validade do PRO de forma determinística: revoga todas as fontes
    locais e, se a data-alvo for futura, concede um voucher único até ela."""
    u = await _email_do_uid(db, uid)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")

    agora = datetime.now(_UTC)
    if body.pro_ate:
        try:
            alvo = datetime.fromisoformat(body.pro_ate)
        except ValueError:
            raise HTTPException(400, "pro_ate inválido (use ISO 8601)")
        if alvo.tzinfo is None:
            alvo = alvo.replace(tzinfo=_UTC)
    elif body.dias is not None:
        alvo = agora + timedelta(days=body.dias)
    else:
        raise HTTPException(400, "informe 'dias' ou 'pro_ate'")

    # revoga tudo (assinaturas ativas + vouchers vigentes)
    assinaturas = (
        await db.execute(select(Assinatura).where(Assinatura.usuario_uid == uid))
    ).scalars().all()
    for a in assinaturas:
        if a.status in ("active", "trialing"):
            a.status = "canceled"
            a.current_period_end = agora
            a.cancel_at_period_end = False  # revogado de vez: não "cancela no fim"
    await _expirar_vouchers(db, uid, agora)

    codigo: Optional[str] = None
    if alvo > agora:
        dias_calc = max(1, (alvo - agora).days)
        v = Voucher(
            codigo=f"{_gerar_codigo()}-{secrets.token_hex(2).upper()}",
            dias=dias_calc,
            criado_por_uid=admin.id,
            resgatado_por_uid=uid,
            resgatado_em=agora,
            pro_ate=alvo,
        )
        db.add(v)
        codigo = v.codigo

    await db.commit()
    return {
        "ok": True,
        "revogado": alvo <= agora,
        "pro_ate": alvo.isoformat() if alvo > agora else None,
        "codigo": codigo,
    }


# ─── Sincronizar do Stripe ──────────────────────────────────────

@router.post("/usuarios/{uid}/sincronizar")
async def sincronizar(
    uid: str,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado (faltam chaves Stripe)")
    ass = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid, Assinatura.stripe_customer_id.isnot(None))
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if ass is None or not ass.stripe_customer_id:
        raise HTTPException(400, "usuário sem customer Stripe")
    try:
        resp = await stripe_request(
            "GET", f"/subscriptions?customer={ass.stripe_customer_id}&status=all&limit=10"
        )
    except StripeError as exc:
        # Customer pode não existir no live (ex.: criado em modo teste) — não derruba.
        return {"ok": False, "sincronizadas": 0, "aviso": f"Stripe: {exc.message}"}

    n = 0
    for sub in resp.get("data", []):
        await _upsert_sub(db, sub, uid_fallback=uid, customer_fallback=ass.stripe_customer_id)
        n += 1
    await db.commit()
    return {"ok": True, "sincronizadas": n}
