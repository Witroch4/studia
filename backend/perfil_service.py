"""Perfil de usuário: pontuação DERIVADA (nada persistido) e perfis p/ o fórum.

- Fórum: SUM(score) dos comentários do usuário (origem studia, não deletados).
- Estudo: `resolucoes` agrupada por dia local (America/Fortaleza, mesmo corte
  do entitlements) contando questões DISTINTAS por dia; ≥15 bate meta,
  ≥25/35/45 rendem combos X2/X3/X4 — cumulativos no mesmo dia, espelhando os
  marcos ao vivo de COMBOS_META_DIARIA.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from entitlements import COMBOS_META_DIARIA, META_DIARIA_PRO
from models import PerfilUsuario, QuestaoComentario, Resolucao

APELIDO_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")

PONTOS_META = 10
PONTOS_COMBO = {2: 20, 3: 30, 4: 40}

_TZ_APP = ZoneInfo("America/Fortaleza")
_UTC = ZoneInfo("UTC")


def _dia_local(dt: datetime) -> date:
    """created_at é UTC-naive → dia calendário no fuso do app."""
    return dt.replace(tzinfo=_UTC).astimezone(_TZ_APP).date()


def contar_marcos(contagens_por_dia: list[int]) -> dict[str, int]:
    """Metas e combos a partir das contagens de questões distintas por dia."""
    por_nivel = {nivel: marco for marco, nivel in COMBOS_META_DIARIA.items()}
    return {
        "metas": sum(1 for n in contagens_por_dia if n >= META_DIARIA_PRO),
        "combos_x2": sum(1 for n in contagens_por_dia if n >= por_nivel[2]),
        "combos_x3": sum(1 for n in contagens_por_dia if n >= por_nivel[3]),
        "combos_x4": sum(1 for n in contagens_por_dia if n >= por_nivel[4]),
    }


def pontos_estudo(marcos: dict[str, int]) -> int:
    return (
        marcos["metas"] * PONTOS_META
        + marcos["combos_x2"] * PONTOS_COMBO[2]
        + marcos["combos_x3"] * PONTOS_COMBO[3]
        + marcos["combos_x4"] * PONTOS_COMBO[4]
    )


def _streak(dias: set[date], hoje: date) -> int:
    # Mesma regra do _compute_streak do dashboard (tolerância de 1 dia),
    # reimplementada aqui: q_router importa este módulo, não o contrário.
    if not dias:
        return 0
    if hoje in dias:
        cursor = hoje
    elif hoje - timedelta(days=1) in dias:
        cursor = hoje - timedelta(days=1)
    else:
        return 0
    streak = 0
    while cursor in dias:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def pontos_forum(db: AsyncSession, uid: str) -> dict:
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(QuestaoComentario.score), 0),
                func.count(QuestaoComentario.id),
            ).where(
                QuestaoComentario.owner_uid == uid,
                QuestaoComentario.origem == "studia",
                QuestaoComentario.deleted_at.is_(None),
            )
        )
    ).one()
    return {"pontos": int(row[0] or 0), "comentarios": int(row[1] or 0)}


async def _contagens_diarias(db: AsyncSession, uid: str) -> dict[date, int]:
    """{dia local: nº de questões DISTINTAS} — agregação em Python porque o
    deslocamento de fuso em SQL não é portável e o volume por usuário é pequeno."""
    rows = (
        await db.execute(
            select(Resolucao.questao_id, Resolucao.created_at).where(
                Resolucao.usuario_uid == uid
            )
        )
    ).all()
    por_dia: dict[date, set[int]] = {}
    for questao_id, created_at in rows:
        if created_at is None:
            continue
        por_dia.setdefault(_dia_local(created_at), set()).add(questao_id)
    return {d: len(qs) for d, qs in por_dia.items()}


async def resumo_perfil(db: AsyncSession, uid: str) -> dict:
    forum = await pontos_forum(db, uid)
    por_dia = await _contagens_diarias(db, uid)
    marcos = contar_marcos(list(por_dia.values()))
    estudo = pontos_estudo(marcos)

    dono = (Resolucao.usuario_uid == uid,)
    total = (await db.execute(select(func.count()).where(*dono))).scalar_one()
    acertos = (
        await db.execute(select(func.count()).where(*dono, Resolucao.acertou == True))  # noqa: E712
    ).scalar_one()

    return {
        "pontuacao": {
            "total": forum["pontos"] + estudo,
            "forum": forum["pontos"],
            "estudo": estudo,
            **marcos,
            "comentarios": forum["comentarios"],
        },
        "resolvidas": int(total),
        "acertos": int(acertos),
        "taxa": round((acertos / total) * 100, 1) if total else 0,
        "streak_dias": _streak(set(por_dia.keys()), datetime.now(_TZ_APP).date()),
    }


async def perfis_forum_por_uids(db: AsyncSession, uids: set[str]) -> dict[str, dict]:
    """{uid: {"apelido", "avatar_url"}} só para perfis PÚBLICOS com apelido."""
    uids = {u for u in uids if u}
    if not uids:
        return {}
    rows = (
        await db.execute(
            select(PerfilUsuario).where(
                PerfilUsuario.owner_uid.in_(uids),
                PerfilUsuario.perfil_publico == True,  # noqa: E712
                PerfilUsuario.apelido.is_not(None),
            )
        )
    ).scalars().all()
    return {
        p.owner_uid: {
            "apelido": p.apelido,
            "avatar_url": (
                f"/api/q/perfil/avatar/{p.avatar_key}"
                if (p.avatar_key and p.mostrar_foto)
                else None
            ),
        }
        for p in rows
    }
