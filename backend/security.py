"""Tokens de sessão do studIA: JWT em cookie HttpOnly + CSRF double-submit.

O FastAPI valida a sessão decodificando o JWT (zero I/O no banco). O JWT é
emitido no handoff (que lê a sessão Better Auth uma vez). CSRF é double-submit:
o cookie `studia_csrf` (legível) precisa casar com o header X-CSRF-Token.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

SESSION_COOKIE = "studia_session"
CSRF_COOKIE = "studia_csrf"
_ALG = "HS256"
_TTL_MIN = int(os.getenv("STUDIA_JWT_TTL_MIN", "30"))
_SECRET = os.getenv(
    "STUDIA_JWT_SECRET",
    "studia-dev-jwt-secret-change-in-prod-0001",  # fallback só de dev
)
# Cookies seguros (HTTPS) em produção; em dev (HTTP) precisam de Secure=False.
_SECURE = os.getenv("STUDIA_COOKIE_SECURE", "true").lower() != "false"


def mint_session_jwt(*, user_id: str, email: str, name: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role,
        "type": "session",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=_TTL_MIN)).timestamp()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALG)


def decode_session_jwt(token: str) -> Optional[dict]:
    try:
        claims = jwt.decode(token, _SECRET, algorithms=[_ALG])
    except JWTError:
        return None
    if claims.get("type") != "session":
        return None
    return claims


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookies(response, *, jwt_token: str, csrf_token: str) -> None:
    """Seta studia_session (HttpOnly) + studia_csrf (legível p/ double-submit)."""
    max_age = _TTL_MIN * 60
    response.set_cookie(
        SESSION_COOKIE, jwt_token, max_age=max_age, httponly=True,
        secure=_SECURE, samesite="lax", path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False,
        secure=_SECURE, samesite="lax", path="/",
    )


def clear_session_cookies(response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")
