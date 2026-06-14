"""Handoff Better Auth → JWT do studIA, e logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _carregar_usuario, _extrair_token
from database import get_db
from security import (
    clear_session_cookies,
    mint_session_jwt,
    new_csrf_token,
    set_session_cookies,
)

# Prefixo /api/session (NÃO /api/auth): em prod o Traefik roteia /api/auth/* para
# o frontend (Better Auth, router priority 100), então um handoff em /api/auth
# ficaria inalcançável no backend. /api/session cai na regra /api (priority 50) →
# backend. (PathPrefix(/api/auth) também pegaria /api/auth-*, por isso saímos do
# prefixo inteiro.)
router = APIRouter(prefix="/api/session", tags=["auth"])


@router.post("/handoff")
async def handoff(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Valida a sessão Better Auth (1 hit no banco) e emite o JWT + CSRF."""
    token = _extrair_token(request)
    user = await _carregar_usuario(token, db) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sessão inválida")
    if user.banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "conta suspensa")
    jwt_token = mint_session_jwt(
        user_id=user.id, email=user.email, name=user.name, role=user.role
    )
    set_session_cookies(response, jwt_token=jwt_token, csrf_token=new_csrf_token())
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookies(response)
    return {"ok": True}
