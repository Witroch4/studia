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
