"""Fórum expõe apelido/avatar do autor conforme o perfil (e nunca o owner_uid)."""

import json

import pytest

from conftest import USER_A
from models import PerfilUsuario, Questao, QuestaoComentario

pytestmark = pytest.mark.asyncio


async def _seed(db_session, *, perfil: PerfilUsuario | None = None):
    db_session.add(Questao(id=99, id_externo=99, tipo="MULTIPLA_ESCOLHA",
                           enunciado_html="<p>E</p>", gabarito="A", status="ATIVA"))
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="user-A", autor_nome="Witalo Rocha",
                                     texto_md="oi"))
    if perfil is not None:
        db_session.add(perfil)
    await db_session.commit()


async def test_apelido_substitui_nome_e_expoe_link(client, db_session):
    await _seed(db_session, perfil=PerfilUsuario(
        owner_uid="user-A", apelido="rochedo-16",
        avatar_key="avatars/11111111-1111-1111-1111-111111111111.webp"))
    r = await client.get("/api/q/questoes/99/forum")
    c = r.json()["comentarios"][0]
    assert c["display_name"] == "rochedo-16"
    assert c["autor_apelido"] == "rochedo-16"
    assert c["autor_avatar_url"].endswith(".webp")
    assert "user-A" not in json.dumps(c)  # owner_uid continua não exposto


async def test_sem_apelido_mostra_nome_sem_link(client, db_session):
    await _seed(db_session, perfil=None)
    c = (await client.get("/api/q/questoes/99/forum")).json()["comentarios"][0]
    assert c["display_name"] == "Witalo Rocha"
    assert c["autor_apelido"] is None
    assert c["autor_avatar_url"] is None


async def test_perfil_privado_nao_linka(client, db_session):
    await _seed(db_session, perfil=PerfilUsuario(
        owner_uid="user-A", apelido="oculto", perfil_publico=False))
    c = (await client.get("/api/q/questoes/99/forum")).json()["comentarios"][0]
    assert c["display_name"] == "Witalo Rocha"  # perfil privado → nome, sem apelido
    assert c["autor_apelido"] is None


async def test_mostrar_foto_false_esconde_avatar_mas_linka(client, db_session):
    await _seed(db_session, perfil=PerfilUsuario(
        owner_uid="user-A", apelido="rochedo-16",
        avatar_key="avatars/11111111-1111-1111-1111-111111111111.webp",
        mostrar_foto=False))
    c = (await client.get("/api/q/questoes/99/forum")).json()["comentarios"][0]
    assert c["autor_apelido"] == "rochedo-16"
    assert c["autor_avatar_url"] is None


async def test_criar_comentario_ja_volta_com_apelido(client, db_session, auth_state):
    db_session.add(PerfilUsuario(owner_uid="admin-1", apelido="prof-x"))
    db_session.add(Questao(id=98, id_externo=98, tipo="MULTIPLA_ESCOLHA",
                           enunciado_html="<p>E</p>", gabarito="A", status="ATIVA"))
    await db_session.commit()
    r = await client.post("/api/q/questoes/98/forum", json={"texto_md": "novo post"})
    assert r.status_code == 201, r.text
    assert r.json()["autor_apelido"] == "prof-x"
