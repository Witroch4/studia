"""GET/PATCH /api/q/perfil: criação lazy, apelido (formato/unicidade) e toggles."""

import pytest
from sqlalchemy import select

from conftest import USER_A, USER_B
from models import PerfilUsuario

pytestmark = pytest.mark.asyncio


async def test_get_perfil_sem_linha_retorna_defaults(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.get("/api/q/perfil")
    assert r.status_code == 200
    body = r.json()
    assert body["apelido"] is None
    assert body["avatar_url"] is None
    assert body["perfil_publico"] is True
    assert body["mostrar_estatisticas"] is True
    assert body["mostrar_foto"] is True
    assert body["resumo"]["pontuacao"]["total"] == 0
    assert body["resumo"]["resolvidas"] == 0


async def test_patch_cria_linha_lazy_e_salva_apelido(client, db_session, auth_state):
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={"apelido": "  Rochedo-16 "})
    assert r.status_code == 200
    assert r.json()["apelido"] == "rochedo-16"  # normalizado (trim + lower)
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.apelido == "rochedo-16"


async def test_patch_apelido_invalido_422(client, auth_state):
    auth_state["user"] = USER_A
    for ruim in ["ab", "-comeca-com-hifen", "tem espaço", "açúcar", "x" * 33]:
        r = await client.patch("/api/q/perfil", json={"apelido": ruim})
        assert r.status_code == 422, f"apelido {ruim!r} deveria dar 422"


async def test_patch_apelido_em_uso_409(client, db_session, auth_state):
    db_session.add(PerfilUsuario(owner_uid="user-B", apelido="rochedo-16"))
    await db_session.commit()
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={"apelido": "rochedo-16"})
    assert r.status_code == 409


async def test_patch_apelido_vazio_limpa(client, db_session, auth_state):
    db_session.add(PerfilUsuario(owner_uid="user-A", apelido="rochedo-16"))
    await db_session.commit()
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={"apelido": ""})
    assert r.status_code == 200
    assert r.json()["apelido"] is None


async def test_patch_toggles(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={
        "perfil_publico": False, "mostrar_estatisticas": False, "mostrar_foto": False,
    })
    assert r.status_code == 200
    body = (await client.get("/api/q/perfil")).json()
    assert body["perfil_publico"] is False
    assert body["mostrar_estatisticas"] is False
    assert body["mostrar_foto"] is False


async def test_patch_parcial_nao_toca_outros_campos(client, auth_state):
    auth_state["user"] = USER_A
    await client.patch("/api/q/perfil", json={"apelido": "rochedo-16"})
    await client.patch("/api/q/perfil", json={"perfil_publico": False})
    body = (await client.get("/api/q/perfil")).json()
    assert body["apelido"] == "rochedo-16"  # PATCH parcial preservou


async def test_perfil_exige_login(client, auth_state):
    auth_state["user"] = None
    assert (await client.get("/api/q/perfil")).status_code == 401
    assert (await client.patch("/api/q/perfil", json={})).status_code == 401
