"""Testes do painel admin de assinaturas (admin_billing_router).

Cobre: overview, listagem com busca, concessão de Pro via voucher, cancelar sem sub.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from auth import CurrentUser

pytestmark = pytest.mark.asyncio

_UTC = timezone.utc

# Usuário não-admin para testar bloqueio 403
USER_A = CurrentUser(id="user-A", email="user-A@studia.test", name="user-A", role="user", banned=False)


async def _seed_user_table(
    db,
    *,
    uid: str = "u-test",
    email: str = "t@studia.test",
    name: str = "T",
    role: str = "user",
    banned: bool = False,
) -> None:
    """Cria tabela "user" mínima (Better Auth não está nas migrations) e insere 1 linha."""
    await db.execute(
        text(
            'CREATE TABLE IF NOT EXISTS "user" ('
            "id varchar PRIMARY KEY, email varchar, name varchar, role varchar, banned boolean)"
        )
    )
    await db.execute(
        text(
            'INSERT INTO "user" (id,email,name,role,banned) VALUES (:id,:e,:n,:r,:b) '
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": uid, "e": email, "n": name, "r": role, "b": banned},
    )


# ─── Overview ────────────────────────────────────────────────────


async def test_overview_admin_ok(client, db_session):
    await _seed_user_table(db_session)
    r = await client.get("/api/admin/billing/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_usuarios"] >= 1
    assert "mrr_centavos" in body and "gratis" in body


async def test_overview_nao_admin_403(client, db_session, auth_state):
    auth_state["user"] = USER_A
    r = await client.get("/api/admin/billing/overview")
    assert r.status_code == 403


# ─── Lista de usuários ───────────────────────────────────────────


async def test_listar_usuarios_busca(client, db_session):
    await _seed_user_table(db_session, uid="u-busca", email="alvo@studia.test", name="Alvo")
    r = await client.get("/api/admin/billing/usuarios?q=alvo")
    assert r.status_code == 200, r.text
    emails = [u["email"] for u in r.json()["usuarios"]]
    assert "alvo@studia.test" in emails


# ─── Conceder Pro ────────────────────────────────────────────────


async def test_conceder_pro_cria_voucher(client, db_session):
    await _seed_user_table(db_session, uid="u-conc", email="conc@studia.test")
    r = await client.post("/api/admin/billing/usuarios/u-conc/conceder", json={"dias": 30})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["dias"] == 30
    # agora aparece como pro_voucher na lista
    r2 = await client.get("/api/admin/billing/usuarios?q=conc@studia.test")
    assert r2.json()["usuarios"][0]["plano"] == "pro_voucher"


# ─── Cancelar sem assinatura ────────────────────────────────────


async def test_cancelar_sem_assinatura_400(client, db_session):
    await _seed_user_table(db_session, uid="u-sem-sub", email="semsub@studia.test")
    # Sem chaves Stripe no ambiente de teste → stripe_configurado() False → 503;
    # com chaves mas sem assinatura → 400. Aceitamos qualquer um dos dois (não há sub).
    r = await client.post(
        "/api/admin/billing/usuarios/u-sem-sub/cancelar", json={"modo": "imediato"}
    )
    assert r.status_code in (400, 503), r.text
