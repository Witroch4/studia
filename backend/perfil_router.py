"""Perfil de usuário: /api/q/perfil (próprio), avatar e perfil público /u/{apelido}."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import perfil_service
from auth import CurrentUser, require_user
from database import get_db
from models import PerfilUsuario

router = APIRouter(prefix="/api/q/perfil", tags=["perfil"])


def _avatar_url(p: Optional[PerfilUsuario]) -> Optional[str]:
    if p is not None and p.avatar_key:
        return f"/api/q/perfil/avatar/{p.avatar_key}"
    return None


async def _get_perfil(db: AsyncSession, uid: str) -> Optional[PerfilUsuario]:
    return (
        await db.execute(select(PerfilUsuario).where(PerfilUsuario.owner_uid == uid))
    ).scalars().first()


async def _get_or_create_perfil(db: AsyncSession, uid: str) -> PerfilUsuario:
    p = await _get_perfil(db, uid)
    if p is None:
        p = PerfilUsuario(owner_uid=uid)
        db.add(p)
        await db.flush()
    return p


@router.get("")
async def meu_perfil(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    p = await _get_perfil(db, user.id)
    return {
        "apelido": p.apelido if p else None,
        "avatar_url": _avatar_url(p),
        "perfil_publico": p.perfil_publico if p else True,
        "mostrar_estatisticas": p.mostrar_estatisticas if p else True,
        "mostrar_foto": p.mostrar_foto if p else True,
        "resumo": await perfil_service.resumo_perfil(db, user.id),
    }


class PatchPerfilReq(BaseModel):
    apelido: Optional[str] = None
    perfil_publico: Optional[bool] = None
    mostrar_estatisticas: Optional[bool] = None
    mostrar_foto: Optional[bool] = None


@router.patch("")
async def atualizar_perfil(
    req: PatchPerfilReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    p = await _get_or_create_perfil(db, user.id)
    if "apelido" in req.model_fields_set:
        apelido = (req.apelido or "").strip().lower() or None
        if apelido is not None and not perfil_service.APELIDO_RE.match(apelido):
            raise HTTPException(
                422,
                "apelido inválido: 3 a 32 caracteres, só letras minúsculas, "
                "números e hífens (não pode começar com hífen)",
            )
        p.apelido = apelido
    for campo in ("perfil_publico", "mostrar_estatisticas", "mostrar_foto"):
        valor = getattr(req, campo)
        if campo in req.model_fields_set and valor is not None:
            setattr(p, campo, valor)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "este apelido já está em uso")
    return {"ok": True, "apelido": p.apelido}
