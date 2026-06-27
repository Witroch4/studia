"""Domínio da fila serial de coleta de guias.

Concentra: CRUD da `guia_fila`, cálculo de cooldown, as operações de guia
reusadas pelo supervisor (resolver+salvar, enfileirar cadernos, checar
conclusão) e o tick do supervisor. Mantém o scraper genérico — a noção de
"guia" e a serialização entre guias vivem aqui.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import GuiaFila

ATIVOS = ("resolving", "collecting")
TERMINAIS = ("done", "skipped", "error")


# ─── Fila: CRUD + cooldown ───────────────────────────────


async def enfileirar_urls(
    db: AsyncSession, urls: list[str], *, requested_by: str | None
) -> list[GuiaFila]:
    """Cria entradas `queued` para URLs novas (trim + dedup intra-lote; ignora
    URLs que já têm entrada não-terminal). NÃO commita (o chamador commita)."""
    vistos: set[str] = set()
    limpos: list[str] = []
    for u in urls:
        u = (u or "").strip()
        if u and u not in vistos:
            vistos.add(u)
            limpos.append(u)
    if not limpos:
        return []
    ja = set(
        (
            await db.execute(
                select(GuiaFila.url).where(
                    GuiaFila.url.in_(limpos),
                    GuiaFila.status.in_(("queued", *ATIVOS)),
                )
            )
        )
        .scalars()
        .all()
    )
    novos = [GuiaFila(url=u, status="queued", requested_by=requested_by) for u in limpos if u not in ja]
    for e in novos:
        db.add(e)
    await db.flush()
    return novos


async def enfileirar_guia(
    db: AsyncSession, guia_id: int, *, requested_by: str | None
) -> GuiaFila | None:
    """Enfileira a re-coleta de um guia já existente (sem resolver de novo).
    Idempotente: retorna None se já houver entrada não-terminal p/ esse guia."""
    existe = (
        await db.execute(
            select(GuiaFila.id).where(
                GuiaFila.guia_id == guia_id,
                GuiaFila.status.in_(("queued", *ATIVOS)),
            )
        )
    ).first()
    if existe:
        return None
    e = GuiaFila(guia_id=guia_id, status="queued", requested_by=requested_by)
    db.add(e)
    await db.flush()
    return e


async def proximo_cooldown_segundos(
    db: AsyncSession, *, agora: datetime, cooldown_s: int
) -> int:
    """Segundos restantes do cooldown desde o último guia finalizado. 0 se nunca
    finalizou nada ou já passou o cooldown."""
    ultimo = (
        await db.execute(
            select(GuiaFila.finalizado_em)
            .where(GuiaFila.finalizado_em.isnot(None))
            .order_by(GuiaFila.finalizado_em.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ultimo is None:
        return 0
    restante = cooldown_s - (agora - ultimo).total_seconds()
    return max(0, int(restante))


async def listar_fila(db: AsyncSession, *, agora: datetime, cooldown_s: int) -> dict:
    """Fila ordenada (FIFO por id) + countdown do cooldown."""
    rows = (await db.execute(select(GuiaFila).order_by(GuiaFila.id))).scalars().all()
    pos = 0
    itens: list[dict[str, Any]] = []
    for e in rows:
        if e.status == "queued":
            pos += 1
        itens.append(
            {
                "id": e.id,
                "url": e.url,
                "status": e.status,
                "guia_id": e.guia_id,
                "posicao": pos if e.status == "queued" else None,
                "erro": e.erro,
                "iniciado_em": e.iniciado_em.isoformat() if e.iniciado_em else None,
                "finalizado_em": e.finalizado_em.isoformat() if e.finalizado_em else None,
            }
        )
    ativo = any(e.status in ATIVOS for e in rows)
    proximo = 0 if ativo else await proximo_cooldown_segundos(db, agora=agora, cooldown_s=cooldown_s)
    return {"fila": itens, "ativo": ativo, "proximo_em_segundos": proximo}


async def remover_da_fila(db: AsyncSession, fila_id: int) -> bool:
    """Remove uma entrada `queued` (não mexe em ativa/terminal)."""
    e = (
        await db.execute(select(GuiaFila).where(GuiaFila.id == fila_id))
    ).scalar_one_or_none()
    if e is None or e.status != "queued":
        return False
    await db.delete(e)
    await db.flush()
    return True


async def pular_fila(db: AsyncSession, fila_id: int, *, agora: datetime) -> bool:
    """Pula a entrada (marca skipped + finalizado_em → dispara cooldown)."""
    e = (
        await db.execute(select(GuiaFila).where(GuiaFila.id == fila_id))
    ).scalar_one_or_none()
    if e is None or e.status in TERMINAIS:
        return False
    e.status = "skipped"
    e.finalizado_em = agora
    await db.flush()
    return True
