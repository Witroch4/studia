"""Testa o caminho real de autenticação JWT + proteção CSRF.

- GET /api/q/cadernos → requer require_user (protegido)
- POST /api/q/cadernos → requer require_user + CSRF (mutação protegida)
"""

import base64
import json

import pytest
from jose import jwt

from security import CSRF_COOKIE, SESSION_COOKIE, decode_session_jwt, mint_session_jwt, new_csrf_token


def _b64url(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_jwt_adulterado_para_admin_e_rejeitado():
    token = mint_session_jwt(user_id="user-1", email="u@b.c", name="U", role="user")
    header = jwt.get_unverified_header(token)
    claims = jwt.get_unverified_claims(token)
    claims["role"] = "admin"
    forged = f"{_b64url(header)}.{_b64url(claims)}.{token.rsplit('.', 1)[1]}"

    assert decode_session_jwt(forged) is None


@pytest.mark.anyio
async def test_jwt_required_and_csrf(client, auth_state):
    from auth import get_current_user_opt
    from main import app

    # Remove o override de auth p/ exercitar o caminho real do JWT
    app.dependency_overrides.pop(get_current_user_opt, None)
    try:
        # (a) Sem JWT → 401 no endpoint protegido GET /api/q/cadernos
        r = await client.get("/api/q/cadernos")
        assert r.status_code == 401, f"Esperava 401, obteve {r.status_code}: {r.text}"

        # (b) Com JWT mas sem header CSRF → 403 em POST /api/q/cadernos
        jwt_token = mint_session_jwt(
            user_id="admin-1", email="a@b.c", name="A", role="admin"
        )
        client.cookies.set(SESSION_COOKIE, jwt_token)
        client.cookies.set(CSRF_COOKIE, new_csrf_token())
        # Não enviamos o header X-CSRF-Token → middleware deve retornar 403
        r2 = await client.post("/api/q/cadernos", json={})
        assert r2.status_code == 403, f"Esperava 403 (csrf inválido), obteve {r2.status_code}: {r2.text}"
    finally:
        # Restaura o override para não vazar estado nos próximos testes
        app.dependency_overrides[get_current_user_opt] = lambda: auth_state["user"]
        # Limpa os cookies setados
        client.cookies.clear()
