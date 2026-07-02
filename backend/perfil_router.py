"""Perfil de usuário: /api/q/perfil (próprio), avatar e perfil público /u/{apelido}."""

from __future__ import annotations

import io
import re as _re
import uuid as _uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import perfil_service
from auth import CurrentUser, require_user
from database import get_db
from minio_client import download_bytes, remove_object, upload_bytes
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


_AVATAR_TIPOS = {"image/png", "image/jpeg", "image/webp"}
_AVATAR_MAX = 5 * 1024 * 1024  # 5 MB
_AVATAR_LADO = 256
_AVATAR_KEY_RE = _re.compile(r"^avatars/[0-9a-f-]{36}\.webp$")


def _processar_avatar(data: bytes) -> bytes:
    """Crop central quadrado + resize 256x256 → webp (roda em threadpool)."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = ImageOps.fit(img.convert("RGB"), (_AVATAR_LADO, _AVATAR_LADO))
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)
    return out.getvalue()


@router.post("/avatar")
async def subir_avatar(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if (file.content_type or "").lower() not in _AVATAR_TIPOS:
        raise HTTPException(415, "tipo de imagem não suportado (use png, jpg ou webp)")
    data = await file.read()
    if len(data) > _AVATAR_MAX:
        raise HTTPException(413, "imagem acima de 5 MB")
    try:
        webp = await run_in_threadpool(_processar_avatar, data)
    except Exception as exc:
        raise HTTPException(422, "imagem inválida") from exc

    p = await _get_or_create_perfil(db, user.id)
    key_antiga = p.avatar_key
    key = f"avatars/{_uuid.uuid4()}.webp"
    await run_in_threadpool(upload_bytes, key, webp, "image/webp")
    p.avatar_key = key
    await db.commit()
    if key_antiga:
        try:
            await run_in_threadpool(remove_object, key_antiga)
        except Exception:
            pass  # objeto órfão é aceitável; nunca falhar o upload por isso
    return {"avatar_url": f"/api/q/perfil/avatar/{key}"}


@router.delete("/avatar")
async def remover_avatar(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    p = await _get_or_create_perfil(db, user.id)
    key = p.avatar_key
    p.avatar_key = None
    await db.commit()
    if key:
        try:
            await run_in_threadpool(remove_object, key)
        except Exception:
            pass
    return {"ok": True}


@router.get("/avatar/{key:path}")
async def servir_avatar(key: str) -> Response:
    """Serve o avatar PELO backend (stream do MinIO) — mesmo racional das
    imagens do fórum: o host minio:9000 só resolve na rede dos containers.
    Key é uuid aleatório por upload → cache immutable é seguro."""
    if not _AVATAR_KEY_RE.match(key):
        raise HTTPException(404, "avatar não encontrado")
    try:
        data = await run_in_threadpool(download_bytes, key)
    except Exception as exc:
        raise HTTPException(404, "avatar não encontrado") from exc
    return Response(
        content=data,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
