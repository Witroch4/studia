"""Validação da sessão do Better Auth dentro do backend FastAPI.

O Better Auth (no Next.js) grava as sessões na tabela `session` do MESMO
Postgres que este backend usa. O cookie `better-auth.session_token` carrega
`<token>.<assinatura>`; o `<token>` (32 chars, sem ".") é a chave em
`session.token`. Validamos lendo a sessão direto do banco — sem chamar o Node.

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


async def get_current_user_opt(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[CurrentUser]:
    """Usuário atual ou None (não levanta erro) — para endpoints públicos/opcionais."""
    token = _extrair_token(request)
    if not token:
        return None
    return await _carregar_usuario(token, db)


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
