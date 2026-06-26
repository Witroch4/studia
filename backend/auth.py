"""Validação da sessão do studIA via JWT de sessão (zero I/O no banco).

O Better Auth (Next.js) emite a sessão; o handoff (`/api/session/handoff`) lê a
sessão do banco UMA vez e emite um JWT interno (`studia_session`). A partir daí,
cada request é autenticado apenas decodificando o JWT — zero hits no banco.

Topologia:
- Produção: Traefik serve front e back no mesmo domínio (`/api/*` → backend),
  então o cookie chega naturalmente (same-origin). Cookie ganha prefixo
  `__Secure-` por estar em HTTPS.
- Dev: cross-origin (`localhost:3000` → `localhost:8011`); o CORS precisa de
  `allow_credentials=True` e o fetch do front precisa de `credentials:"include"`.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from security import SESSION_COOKIE, decode_session_jwt

# Better Auth nomeia o cookie assim; em HTTPS ganha o prefixo __Secure-.
_COOKIE_NAMES = (
    "better-auth.session_token",
    "__Secure-better-auth.session_token",
)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    role: str
    banned: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_professor(self) -> bool:
        # admin é superset de professor (pode tudo que o professor pode)
        return self.role in ("professor", "admin")


def _extrair_token(request: Request) -> Optional[str]:
    """Pega o token cru do cookie de sessão (parte antes da assinatura)."""
    for nome in _COOKIE_NAMES:
        raw = request.cookies.get(nome)
        if raw:
            # cookie = "<token>.<assinatura>" (urlencoded); o token não tem ".".
            return urllib.parse.unquote(raw).split(".")[0]
    return None


async def _carregar_usuario(token: str, db: AsyncSession) -> Optional[CurrentUser]:
    row = (
        await db.execute(
            text(
                """
                SELECT u.id,
                       u.email,
                       u.name,
                       COALESCE(u.role, 'user') AS role,
                       COALESCE(u.banned, false) AS banned
                FROM session s
                JOIN "user" u ON u.id = s."userId"
                WHERE s.token = :token
                  AND s."expiresAt" > now()
                """
            ),
            {"token": token},
        )
    ).mappings().first()
    if not row:
        return None
    return CurrentUser(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=row["role"] or "user",
        banned=bool(row["banned"]),
    )


async def get_current_user_opt(request: Request) -> Optional[CurrentUser]:
    """Usuário atual a partir do JWT de sessão (zero I/O no banco). None se ausente/inválido."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    claims = decode_session_jwt(raw)
    if not claims:
        return None
    return CurrentUser(
        id=claims["sub"],
        email=claims.get("email", ""),
        name=claims.get("name", ""),
        role=claims.get("role", "user"),
        banned=False,  # banimento é checado no handoff (na emissão do JWT)
    )


async def require_user(
    user: Optional[CurrentUser] = Depends(get_current_user_opt),
) -> CurrentUser:
    """Exige sessão válida; 401 se não logado, 403 se banido."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")
    if user.banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "conta suspensa")
    return user


async def require_admin(
    user: CurrentUser = Depends(require_user),
) -> CurrentUser:
    """Exige role admin; 403 caso contrário."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "acesso restrito a administradores")
    return user


async def require_professor(
    user: CurrentUser = Depends(require_user),
) -> CurrentUser:
    """Exige role professor ou admin; 403 caso contrário."""
    if not user.is_professor:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "acesso restrito a professores")
    return user
