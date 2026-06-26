import pytest
from sqlalchemy import select

from conftest import ADMIN_USER, USER_A, USER_B, make_user
from models import ComentarioVoto, Questao, QuestaoComentario

pytestmark = pytest.mark.asyncio


async def seed_questao(db_session, qid=99):
    db_session.add(
        Questao(id=qid, id_externo=qid, tipo="MULTIPLA_ESCOLHA",
                enunciado_html="<p>E</p>", gabarito="A", status="ATIVA")
    )
    await db_session.commit()


async def _criar_questao(db_session) -> int:
    """Cria uma questão sem id fixo (autoincrement) e retorna seu id."""
    q = Questao(tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>Q</p>",
                gabarito="A", status="ATIVA")
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)
    return q.id


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


async def test_nao_responde_comentario_removido(client, db_session):
    await seed_questao(db_session)
    raiz = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "raiz"})).json()
    await client.delete(f"/api/q/forum/{raiz['id']}")
    r = await client.post("/api/q/questoes/99/forum",
                          json={"texto_md": "resp", "parent_id": raiz["id"]})
    assert r.status_code == 400


# ── Task 4: GET por quadro, display de persona, eh_professor, contagens ──────

async def test_quadros_isolados_e_contagens(client, db_session):
    """quadros alunos/professores são isolados; detalhe separa contagens."""
    await seed_questao(db_session)

    # Semeia 1 comentário de aluno via POST normal (quadro default = alunos)
    r_aluno = await client.post("/api/q/questoes/99/forum",
                                json={"texto_md": "post de aluno"})
    assert r_aluno.status_code == 201

    # Semeia 1 comentário de professor via ORM (POST com quadro é Task 5)
    from forum_personas import POOL
    persona = POOL[0]
    db_session.add(QuestaoComentario(
        id=500,
        questao_id=99,
        origem="studia",
        owner_uid="admin-1",
        autor_nome="admin-1",
        texto_md="post de prof",
        forum_tipo="professores",
        persona_nome=persona,
        score=0,
    ))
    await db_session.commit()

    # GET de cada quadro só enxerga o seu
    a = (await client.get("/api/q/questoes/99/forum?quadro=alunos")).json()
    p = (await client.get("/api/q/questoes/99/forum?quadro=professores")).json()
    assert [c["texto_md"] for c in a["comentarios"]] == ["post de aluno"]
    assert [c["texto_md"] for c in p["comentarios"]] == ["post de prof"]

    # comentário do professor retorna display_name = persona e eh_professor=True
    pc = p["comentarios"][0]
    assert pc["display_name"] == persona
    assert pc["eh_professor"] is True

    # comentário de aluno retorna eh_professor=False
    ac = a["comentarios"][0]
    assert ac["eh_professor"] is False

    # detalhe da questão separa as contagens
    det = (await client.get("/api/q/99")).json()
    assert det["forum_count"] == 1           # só alunos
    assert det["forum_count_professores"] == 1


async def test_quadro_invalido_422(client):
    r = await client.get("/api/q/questoes/1/forum?quadro=xpto")
    assert r.status_code == 422


# ── Task 5: POST com quadro, gate de escrita e persona ───────────────────────

async def test_aluno_nao_escreve_no_quadro_professores(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    auth_state["user"] = USER_A  # role "user"
    r = await client.post(f"/api/q/questoes/{qid}/forum",
                          json={"texto_md": "tentativa", "quadro": "professores"})
    assert r.status_code == 403


async def test_professor_real_posta_com_nome_real(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    prof = make_user("prof-1", role="professor")
    auth_state["user"] = prof
    r = await client.post(f"/api/q/questoes/{qid}/forum",
                          json={"texto_md": "explicação do prof", "quadro": "professores"})
    assert r.status_code == 201
    # professor real => nome real, sem persona
    assert r.json()["display_name"] == prof.name
    assert r.json()["eh_professor"] is True


async def test_aluno_le_e_vota_em_post_de_professor(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    auth_state["user"] = ADMIN_USER
    r = await client.post(f"/api/q/questoes/{qid}/forum",
                          json={"texto_md": "resposta expert", "quadro": "professores"})
    cid = r.json()["id"]
    # aluno lê
    auth_state["user"] = USER_A
    lista = (await client.get(f"/api/q/questoes/{qid}/forum?quadro=professores")).json()
    assert lista["total"] == 1
    # aluno vota
    v = await client.post(f"/api/q/forum/{cid}/voto", json={"valor": 1})
    assert v.status_code == 200
    assert v.json()["score"] == 1


async def test_admin_posta_no_quadro_professores_recebe_persona(client, auth_state, db_session):
    """POST do admin no quadro professores => display_name é uma persona do POOL."""
    from forum_personas import POOL
    qid = await _criar_questao(db_session)
    auth_state["user"] = ADMIN_USER
    r = await client.post(
        f"/api/q/questoes/{qid}/forum",
        json={"texto_md": "explicação profunda sobre o tema", "quadro": "professores"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["display_name"] in POOL
    assert body["display_name"] != ADMIN_USER.name
    assert body["eh_professor"] is True

    # confirma via DB que persona_nome ficou gravado (não nulo)
    from models import QuestaoComentario
    stmt = select(QuestaoComentario).where(QuestaoComentario.id == body["id"])
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.persona_nome is not None
    assert row.persona_nome == body["display_name"]


async def test_resposta_nao_cruza_quadro(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    auth_state["user"] = ADMIN_USER
    raiz_aluno = (await client.post(f"/api/q/questoes/{qid}/forum",
                  json={"texto_md": "raiz aluno", "quadro": "alunos"})).json()["id"]
    # responder no quadro professores apontando p/ raiz do quadro alunos => 400
    r = await client.post(f"/api/q/questoes/{qid}/forum",
            json={"texto_md": "resp", "quadro": "professores", "parent_id": raiz_aluno})
    assert r.status_code == 400
