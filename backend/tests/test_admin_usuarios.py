import pytest
from sqlalchemy import text

from tests.conftest import ADMIN_USER, USER_A


async def _semear_usuario(db, uid, email, name, role="user"):
    await db.execute(text(
        'INSERT INTO "user" (id, email, name, role, banned, "createdAt", "updatedAt", "emailVerified") '
        "VALUES (:id, :email, :name, :role, false, now(), now(), true)"
    ), {"id": uid, "email": email, "name": name, "role": role})
    await db.flush()


@pytest.mark.asyncio
async def test_listar_usuarios_admin(client, auth_state, db_session):
    await _semear_usuario(db_session, "alvo-1", "alvo@studia.test", "Aluno Alvo")
    auth_state["user"] = ADMIN_USER
    r = await client.get("/api/q/admin/usuarios?q=alvo")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()["usuarios"]]
    assert "alvo@studia.test" in emails


@pytest.mark.asyncio
async def test_listar_usuarios_nao_admin_403(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.get("/api/q/admin/usuarios")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_role_promove_professor(client, auth_state, db_session):
    await _semear_usuario(db_session, "alvo-2", "p@studia.test", "Promover")
    auth_state["user"] = ADMIN_USER
    r = await client.patch("/api/q/admin/usuarios/alvo-2/role", json={"role": "professor"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "professor"
    assert "aviso" in body, "A resposta deve conter a chave 'aviso'"
    row = (await db_session.execute(
        text('SELECT role FROM "user" WHERE id = :id'), {"id": "alvo-2"}
    )).scalar_one()
    assert row == "professor"


@pytest.mark.asyncio
async def test_patch_role_invalido_422(client, auth_state, db_session):
    await _semear_usuario(db_session, "alvo-3", "x@studia.test", "X")
    auth_state["user"] = ADMIN_USER
    r = await client.patch("/api/q/admin/usuarios/alvo-3/role", json={"role": "rei"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_nao_rebaixa_a_si_mesmo_400(client, auth_state, db_session):
    await _semear_usuario(db_session, ADMIN_USER.id, "admin@studia.test", "Admin", role="admin")
    auth_state["user"] = ADMIN_USER
    r = await client.patch(f"/api/q/admin/usuarios/{ADMIN_USER.id}/role", json={"role": "user"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_role_uid_inexistente_404(client, auth_state):
    auth_state["user"] = ADMIN_USER
    r = await client.patch("/api/q/admin/usuarios/nao-existe/role", json={"role": "user"})
    assert r.status_code == 404
