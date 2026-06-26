import pytest
from sqlalchemy import select

from conftest import ADMIN_USER, USER_A, USER_B
from models import ComentarioVoto, Questao, QuestaoComentario

pytestmark = pytest.mark.asyncio


async def seed_questao(db_session, qid=99):
    db_session.add(
        Questao(id=qid, id_externo=qid, tipo="MULTIPLA_ESCOLHA",
                enunciado_html="<p>E</p>", gabarito="A", status="ATIVA")
    )
    await db_session.commit()


async def test_forum_vazio_retorna_lista_vazia(client, db_session):
    await seed_questao(db_session)
    r = await client.get("/api/q/questoes/99/forum")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "comentarios": []}


async def test_forum_lista_post_e_resposta_aninhada(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="admin-1", autor_nome="admin-1", texto_md="raiz"))
    await db_session.commit()
    db_session.add(QuestaoComentario(id=2, questao_id=99, origem="studia",
                                     owner_uid="user-A", autor_nome="user-A",
                                     parent_id=1, texto_md="resposta"))
    await db_session.commit()

    r = await client.get("/api/q/questoes/99/forum")
    data = r.json()
    assert data["total"] == 2
    assert len(data["comentarios"]) == 1
    raiz = data["comentarios"][0]
    assert raiz["texto_md"] == "raiz"
    assert raiz["display_name"] == "admin-1"
    assert len(raiz["respostas"]) == 1
    assert raiz["respostas"][0]["texto_md"] == "resposta"


async def test_forum_anonimiza_comentario_do_tc(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="tc",
                                     autor_nome="Fulano Real TC", autor_tipo="aluno",
                                     texto_md="comentário tc", curtidas=5, score=5))
    await db_session.commit()
    r = await client.get("/api/q/questoes/99/forum")
    c = r.json()["comentarios"][0]
    assert c["display_name"] != "Fulano Real TC"  # nome original nunca vaza
    assert c["origem"] == "tc"
    assert c["score"] == 5


async def test_forum_ordena_por_pontos(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="x", autor_nome="x", texto_md="baixo", score=1))
    db_session.add(QuestaoComentario(id=2, questao_id=99, origem="studia",
                                     owner_uid="y", autor_nome="y", texto_md="alto", score=9))
    await db_session.commit()
    r = await client.get("/api/q/questoes/99/forum?ordenar=pontos")
    ids = [c["texto_md"] for c in r.json()["comentarios"]]
    assert ids == ["alto", "baixo"]


async def test_forum_count_no_detalhe(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="x", autor_nome="x", texto_md="a"))
    await db_session.commit()
    r = await client.get("/api/q/99")
    assert r.json()["forum_count"] == 1


# ── Task 4: criar comentário e resposta ──────────────────────────────────────

async def test_criar_comentario_raiz(client, db_session):
    await seed_questao(db_session)
    r = await client.post("/api/q/questoes/99/forum", json={"texto_md": "olá $x^2$"})
    assert r.status_code == 201
    body = r.json()
    assert body["texto_md"] == "olá $x^2$"
    assert body["parent_id"] is None
    assert body["display_name"] == "admin-1"  # usuário default do conftest


async def test_criar_resposta(client, db_session):
    await seed_questao(db_session)
    raiz = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "raiz"})).json()
    r = await client.post("/api/q/questoes/99/forum",
                          json={"texto_md": "resp", "parent_id": raiz["id"]})
    assert r.status_code == 201
    assert r.json()["parent_id"] == raiz["id"]


async def test_resposta_de_resposta_e_rejeitada(client, db_session):
    await seed_questao(db_session)
    raiz = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "raiz"})).json()
    resp = (await client.post("/api/q/questoes/99/forum",
                              json={"texto_md": "r1", "parent_id": raiz["id"]})).json()
    r = await client.post("/api/q/questoes/99/forum",
                          json={"texto_md": "r2", "parent_id": resp["id"]})
    assert r.status_code == 400


async def test_parent_de_outra_questao_e_rejeitado(client, db_session):
    await seed_questao(db_session, qid=99)
    await seed_questao(db_session, qid=88)
    raiz88 = (await client.post("/api/q/questoes/88/forum", json={"texto_md": "x"})).json()
    r = await client.post("/api/q/questoes/99/forum",
                          json={"texto_md": "y", "parent_id": raiz88["id"]})
    assert r.status_code == 400


async def test_texto_vazio_e_rejeitado(client, db_session):
    await seed_questao(db_session)
    r = await client.post("/api/q/questoes/99/forum", json={"texto_md": "   "})
    assert r.status_code == 422


# ── Task 5: editar e excluir ─────────────────────────────────────────────────

async def test_editar_proprio_comentario(client, db_session):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    r = await client.patch(f"/api/q/forum/{c['id']}", json={"texto_md": "v2"})
    assert r.status_code == 200
    assert r.json()["texto_md"] == "v2"
    assert r.json()["editado"] is True


async def test_editar_de_outro_usuario_proibido(client, db_session, auth_state):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    auth_state["user"] = USER_B
    r = await client.patch(f"/api/q/forum/{c['id']}", json={"texto_md": "hack"})
    assert r.status_code == 403


async def test_nao_edita_comentario_tc(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=50, questao_id=99, origem="tc",
                                     autor_nome="X", autor_tipo="aluno", texto_md="tc"))
    await db_session.commit()
    r = await client.patch("/api/q/forum/50", json={"texto_md": "edit"})
    assert r.status_code == 403


async def test_excluir_proprio(client, db_session):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    r = await client.delete(f"/api/q/forum/{c['id']}")
    assert r.status_code == 200
    # some do feed (folha deletada)
    assert (await client.get("/api/q/questoes/99/forum")).json()["total"] == 0


async def test_admin_exclui_de_qualquer_um(client, db_session, auth_state):
    await seed_questao(db_session)
    auth_state["user"] = USER_A
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    auth_state["user"] = ADMIN_USER
    r = await client.delete(f"/api/q/forum/{c['id']}")
    assert r.status_code == 200


async def test_excluir_raiz_com_resposta_vira_placeholder(client, db_session):
    await seed_questao(db_session)
    raiz = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "raiz"})).json()
    await client.post("/api/q/questoes/99/forum", json={"texto_md": "resp", "parent_id": raiz["id"]})
    await client.delete(f"/api/q/forum/{raiz['id']}")
    data = (await client.get("/api/q/questoes/99/forum")).json()
    assert len(data["comentarios"]) == 1
    assert data["comentarios"][0]["removido"] is True
    assert data["comentarios"][0]["texto_md"] is None
    assert len(data["comentarios"][0]["respostas"]) == 1


# ── Task 6: votar (toggle/trocar/remover) + recálculo de score ───────────────

async def test_votar_e_recalcular_score(client, db_session, auth_state):
    await seed_questao(db_session)
    auth_state["user"] = USER_A
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v"})).json()
    auth_state["user"] = USER_B
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 1})
    assert r.status_code == 200
    assert r.json() == {"score": 1, "meu_voto": 1}


async def test_trocar_e_remover_voto(client, db_session, auth_state):
    await seed_questao(db_session)
    auth_state["user"] = USER_A
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v"})).json()
    auth_state["user"] = USER_B
    await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 1})
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": -1})
    assert r.json() == {"score": -1, "meu_voto": -1}
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 0})
    assert r.json() == {"score": 0, "meu_voto": 0}


async def test_nao_pode_votar_no_proprio(client, db_session):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v"})).json()
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 1})
    assert r.status_code == 400


async def test_voto_soma_curtidas_do_tc(client, db_session, auth_state):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=70, questao_id=99, origem="tc", autor_nome="X",
                                     autor_tipo="aluno", texto_md="tc", curtidas=3, score=3))
    await db_session.commit()
    auth_state["user"] = USER_A
    r = await client.post("/api/q/forum/70/voto", json={"valor": 1})
    assert r.json()["score"] == 4  # 3 curtidas + 1 voto
