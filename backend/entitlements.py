"""Direitos de acesso: assinatura ativa e limite diário de questões.

Regra: plano grátis resolve até LIMITE_DIARIO_GRATIS questões DISTINTAS por dia
(corte à meia-noite no fuso do app). Admin e assinante ativo = ilimitado.
Reabrir/repetir uma questão já contada hoje não consome nova cota.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Assinatura, Resolucao, Voucher

LIMITE_DIARIO_GRATIS = 10
STATUS_ATIVOS = ("active", "trialing")

# O fuso do app casa com o TZ dos containers de produção (America/Fortaleza,
# UTC-3 fixo). created_at das resoluções é gravado UTC-naive (Postgres em UTC).
_TZ_APP = ZoneInfo("America/Fortaleza")
_UTC = ZoneInfo("UTC")


def inicio_do_dia_utc_naive() -> datetime:
    """Meia-noite de hoje no fuso do app, como datetime UTC-naive (p/ comparar com created_at)."""
    agora_local = datetime.now(_TZ_APP)
    inicio_local = agora_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return inicio_local.astimezone(_UTC).replace(tzinfo=None)


async def assinatura_ativa(db: AsyncSession, uid: str) -> Optional[Assinatura]:
    """Retorna a assinatura ativa do usuário (status ativo + período vigente), ou None."""
    row = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid, Assinatura.status.in_(STATUS_ATIVOS))
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if not row:
        return None
    if row.current_period_end is not None:
        fim = row.current_period_end
        agora = datetime.now(_UTC)
        # current_period_end é timestamptz; se vier naive, assume UTC.
        if fim.tzinfo is None:
            fim = fim.replace(tzinfo=_UTC)
        if fim < agora:
            return None
    return row


async def voucher_pro_ativo(db: AsyncSession, uid: str) -> Optional[datetime]:
    """Maior `pro_ate` futuro entre os vouchers resgatados pela conta (ou None)."""
    agora = datetime.now(_UTC)
    pro_ate = (
        await db.execute(
            select(func.max(Voucher.pro_ate)).where(Voucher.resgatado_por_uid == uid)
        )
    ).scalar_one_or_none()
    if pro_ate is None:
        return None
    if pro_ate.tzinfo is None:
        pro_ate = pro_ate.replace(tzinfo=_UTC)
    return pro_ate if pro_ate > agora else None


async def acesso_pro_ativo(db: AsyncSession, uid: str) -> bool:
    """True se a conta tem PRO por assinatura Stripe ativa OU voucher vigente."""
    if await assinatura_ativa(db, uid):
        return True
    return await voucher_pro_ativo(db, uid) is not None


async def contagem_questoes_hoje(db: AsyncSession, uid: str) -> int:
    """Quantas questões DISTINTAS o usuário já resolveu hoje."""
    inicio = inicio_do_dia_utc_naive()
    return (
        await db.execute(
            select(func.count(func.distinct(Resolucao.questao_id))).where(
                Resolucao.usuario_uid == uid,
                Resolucao.created_at >= inicio,
            )
        )
    ).scalar_one()


async def _questao_ja_contada_hoje(db: AsyncSession, uid: str, questao_id: int) -> bool:
    inicio = inicio_do_dia_utc_naive()
    achou = (
        await db.execute(
            select(Resolucao.id)
            .where(
                Resolucao.usuario_uid == uid,
                Resolucao.questao_id == questao_id,
                Resolucao.created_at >= inicio,
            )
            .limit(1)
        )
    ).first()
    return achou is not None


async def resumo_limite(db: AsyncSession, user) -> dict:
    """Resumo do limite para a UI (contador "7/10 hoje" e estado do plano)."""
    if user.is_admin:
        return {"ilimitado": True, "motivo": "admin", "usado": 0,
                "limite": LIMITE_DIARIO_GRATIS, "restantes": None}
    if await assinatura_ativa(db, user.id):
        return {"ilimitado": True, "motivo": "assinatura", "usado": 0,
                "limite": LIMITE_DIARIO_GRATIS, "restantes": None}
    if await voucher_pro_ativo(db, user.id):
        return {"ilimitado": True, "motivo": "voucher", "usado": 0,
                "limite": LIMITE_DIARIO_GRATIS, "restantes": None}
    usado = await contagem_questoes_hoje(db, user.id)
    return {
        "ilimitado": False,
        "motivo": "gratis",
        "usado": usado,
        "limite": LIMITE_DIARIO_GRATIS,
        "restantes": max(0, LIMITE_DIARIO_GRATIS - usado),
    }


async def garantir_pode_resolver(db: AsyncSession, user, questao_id: int) -> None:
    """Levanta 402 se o usuário grátis estourou o limite diário ao responder
    uma questão NOVA hoje. Admin/assinante passam direto."""
    if user.is_admin:
        return
    if await acesso_pro_ativo(db, user.id):
        return
    if await _questao_ja_contada_hoje(db, user.id, questao_id):
        return  # repetir questão já contada não consome nova cota
    usado = await contagem_questoes_hoje(db, user.id)
    if usado >= LIMITE_DIARIO_GRATIS:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "erro": "limite_diario",
                "mensagem": (
                    f"Você atingiu o limite de {LIMITE_DIARIO_GRATIS} questões por dia "
                    "do plano grátis. Assine o studIA Pro para resolver ilimitado."
                ),
                "usado": usado,
                "limite": LIMITE_DIARIO_GRATIS,
            },
        )
