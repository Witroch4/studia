"""Perfil público /api/q/perfil/u/{apelido}: toggles e vazamento zero de identidade."""

import json
from datetime import datetime

import pytest
from sqlalchemy import text

from models import PerfilUsuario, Questao, QuestaoComentario

pytestmark = pytest.mark.asyncio


async def _seed_user_better_auth(db_session, uid: str, role: str | None = None):
    await db_session.execute(text(
        'INSERT INTO "user" (id, name, email, role) '
        "VALUES (:id, :name, :email, :role) ON CONFLICT (id) DO NOTHING"
    ), {"id": uid, "name": f"Nome Real {uid}", "email": f"{uid}@x.com", "role": role})
    await db_session.commit()


async def _seed_perfil(db_session, uid: str, apelido: str, **kw):
    await _seed_user_better_auth(db_session, uid, kw.pop("role", None))
    db_session.add(PerfilUsuario(owner_uid=uid, apelido=apelido, **kw))
    await db_session.commit()


async def test_perfil_publico_basico(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-A", "rochedo-16", role="professor")
    db_session.add(Questao(id=9100, id_externo=9100, tipo="MULTIPLA_ESCOLHA",
                           enunciado_html="<p>Q</p>", gabarito="A", status="ATIVA"))
    await db_session.commit()
    db_session.add(QuestaoComentario(questao_id=9100, origem="studia",
                                     owner_uid="user-A", texto_md="oi", score=7))
    await db_session.commit()

    auth_state["user"] = None  # endpoint é público, sem login
    r = await client.get("/api/q/perfil/u/rochedo-16")
    assert r.status_code == 200
    body = r.json()
    assert body["apelido"] == "rochedo-16"
    assert body["badge"] == "professor"
    assert body["membro_desde"] is not None
    assert body["pontuacao"]["forum"] == 7
    assert body["pontuacao"]["comentarios"] == 1
    assert body["estatisticas"] is not None
    # identidade real NUNCA vaza
    dump = json.dumps(body)
    assert "user-A" not in dump and "Nome Real" not in dump and "@x.com" not in dump


async def test_apelido_inexistente_404(client, auth_state):
    auth_state["user"] = None
    assert (await client.get("/api/q/perfil/u/nao-existe")).status_code == 404


async def test_perfil_privado_404_com_flag(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-B", "oculto", perfil_publico=False)
    auth_state["user"] = None
    r = await client.get("/api/q/perfil/u/oculto")
    assert r.status_code == 404
    assert r.json()["detail"] == {"privado": True}


async def test_toggles_de_foto_e_estatisticas(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-C", "reservado",
                       avatar_key="avatars/11111111-1111-1111-1111-111111111111.webp",
                       mostrar_foto=False, mostrar_estatisticas=False)
    auth_state["user"] = None
    body = (await client.get("/api/q/perfil/u/reservado")).json()
    assert body["avatar_url"] is None
    assert body["estatisticas"] is None
    assert "total" in body["pontuacao"]  # pontuação sempre presente


async def test_apelido_casa_case_insensitive(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-D", "rochedo-17")
    auth_state["user"] = None
    assert (await client.get("/api/q/perfil/u/ROCHEDO-17")).status_code == 200
