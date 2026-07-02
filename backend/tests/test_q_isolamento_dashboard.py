"""Isolamento multiusuário + Dashboard real (TAREFA-multiusuario-dashboard.md).

Correção de privacidade: cada usuário só enxerga os próprios dados pessoais
(Minhas Pastas/cadernos salvos, favoritas, resoluções, estatísticas, anotações,
dashboard). Catálogo (Questões, Guias, cadernos materializados de guia) continua
compartilhado.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from auth import CurrentUser
from models import (
    CadernoQuestoes,
    Guia,
    GuiaCaderno,
    Materia,
    Questao,
    QuestaoAnotacao,
    QuestaoFavorita,
    Resolucao,
)

pytestmark = pytest.mark.asyncio


def _u(uid: str, role: str = "user") -> CurrentUser:
    return CurrentUser(id=uid, email=f"{uid}@t", name=uid, role=role, banned=False)


ADMIN = _u("admin-1", "admin")
A = _u("user-A")
B = _u("user-B")


# ─── Cadernos / Minhas Pastas por usuário ────────────────


async def test_listar_cadernos_so_do_dono(client, db_session, auth_state):
    db_session.add_all(
        [
            CadernoQuestoes(nome="do A", owner_uid="user-A", question_ids=[1], total=1),
            CadernoQuestoes(nome="do B", owner_uid="user-B", question_ids=[2], total=1),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    r = await client.get("/api/q/cadernos")
    assert r.status_code == 200
    assert [c["nome"] for c in r.json()] == ["do A"]

    auth_state["user"] = B
    r = await client.get("/api/q/cadernos")
    assert [c["nome"] for c in r.json()] == ["do B"]


async def test_listar_pastas_so_do_dono(client, db_session, auth_state):
    db_session.add_all(
        [
            CadernoQuestoes(nome="A1", pasta="OAB", owner_uid="user-A", question_ids=[1], total=1),
            CadernoQuestoes(nome="B1", pasta="ENEM", owner_uid="user-B", question_ids=[2], total=1),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    r = await client.get("/api/q/pastas")
    assert {p["pasta"] for p in r.json()} == {"OAB"}

    auth_state["user"] = B
    r = await client.get("/api/q/pastas")
    assert {p["pasta"] for p in r.json()} == {"ENEM"}


async def test_cadernos_exige_login(client, auth_state):
    auth_state["user"] = None
    r = await client.get("/api/q/cadernos")
    assert r.status_code == 401


async def test_gerar_caderno_grava_owner_do_usuario(client, db_session, auth_state, monkeypatch):
    import q_router

    async def fake_search(payload):
        return {"hits": [{"id": 1}, {"id": 2}, {"id": 3}]}

    monkeypatch.setattr(q_router, "_meili_search", fake_search)

    auth_state["user"] = A
    r = await client.post("/api/q/cadernos", json={"nome": "Meu caderno", "ordem": "id"})
    assert r.status_code == 200
    cad_id = r.json()["id"]

    cad = (await db_session.get(CadernoQuestoes, cad_id))
    assert cad.owner_uid == "user-A"

    # B não vê o caderno do A
    auth_state["user"] = B
    r = await client.get("/api/q/cadernos")
    assert all(c["id"] != cad_id for c in r.json())


# ─── Acesso a um caderno: dono OU catálogo de guia ───────


async def test_detalhe_caderno_dono_acessa(client, db_session, auth_state):
    db_session.add(CadernoQuestoes(id=50, nome="priv A", owner_uid="user-A", question_ids=[1], total=1))
    await db_session.commit()
    auth_state["user"] = A
    r = await client.get("/api/q/cadernos/50")
    assert r.status_code == 200
    assert r.json()["nome"] == "priv A"


async def test_detalhe_caderno_de_outro_da_404(client, db_session, auth_state):
    db_session.add(CadernoQuestoes(id=51, nome="priv A", owner_uid="user-A", question_ids=[1], total=1))
    await db_session.commit()
    auth_state["user"] = B
    r = await client.get("/api/q/cadernos/51")
    assert r.status_code == 404


async def test_detalhe_caderno_de_guia_eh_compartilhado(client, db_session, auth_state):
    # Caderno materializado de um guia (sem dono pessoal) é catálogo: qualquer um acessa.
    db_session.add(CadernoQuestoes(id=52, nome="Guia cad", owner_uid=None, question_ids=[1], total=1))
    db_session.add(Guia(id=1, tc_guia_id=999, nome="Guia X"))
    db_session.add(GuiaCaderno(id=1, guia_id=1, tc_caderno_id=12345, nome="Cap 1", caderno_id=52))
    await db_session.commit()

    auth_state["user"] = B  # usuário novo, sem nada salvo
    r = await client.get("/api/q/cadernos/52")
    assert r.status_code == 200
    assert r.json()["nome"] == "Guia cad"


async def test_caderno_de_guia_nao_aparece_em_minhas_pastas(client, db_session, auth_state):
    # Catálogo de guia é estudado via aba Guias, não polui "Minhas Pastas" de ninguém.
    db_session.add(CadernoQuestoes(id=53, nome="Guia cad", owner_uid=None, question_ids=[1], total=1))
    db_session.add(Guia(id=2, tc_guia_id=998, nome="Guia Y"))
    db_session.add(GuiaCaderno(id=2, guia_id=2, tc_caderno_id=22345, nome="Cap 1", caderno_id=53))
    await db_session.commit()

    auth_state["user"] = B
    r = await client.get("/api/q/cadernos")
    assert r.json() == []


# ─── Favoritas por usuário ───────────────────────────────


async def test_favoritas_isoladas_por_usuario(client, db_session, auth_state):
    db_session.add(Questao(id=10, enunciado_md="Q10"))
    await db_session.commit()

    auth_state["user"] = A
    r = await client.post("/api/q/10/favoritar")
    assert r.json() == {"questao_id": 10, "favorita": True}
    assert (await client.get("/api/q/favoritas")).json() == {"ids": [10], "total": 1}

    # B não vê a favorita do A e pode favoritar a MESMA questão (sem colisão de unique)
    auth_state["user"] = B
    assert (await client.get("/api/q/favoritas")).json() == {"ids": [], "total": 0}
    r = await client.post("/api/q/10/favoritar")
    assert r.json() == {"questao_id": 10, "favorita": True}
    assert (await client.get("/api/q/favoritas")).json() == {"ids": [10], "total": 1}

    # A continua com a dele
    auth_state["user"] = A
    assert (await client.get("/api/q/favoritas")).json() == {"ids": [10], "total": 1}


# ─── Estatísticas por usuário ────────────────────────────


async def test_estatisticas_questao_so_do_usuario(client, db_session, auth_state):
    db_session.add(Questao(id=20, enunciado_md="Q20"))
    db_session.add_all(
        [
            Resolucao(id=1, questao_id=20, usuario_uid="user-A", acertou=True),
            Resolucao(id=2, questao_id=20, usuario_uid="user-A", acertou=False),
            Resolucao(id=3, questao_id=20, usuario_uid="user-B", acertou=True),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    r = await client.get("/api/q/20/estatisticas")
    assert r.json() == {"resolvidas": 2, "acertos": 1, "erros": 1}

    auth_state["user"] = B
    r = await client.get("/api/q/20/estatisticas")
    assert r.json() == {"resolvidas": 1, "acertos": 1, "erros": 0}


async def test_estatisticas_caderno_so_do_usuario(client, db_session, auth_state):
    db_session.add(CadernoQuestoes(id=60, nome="cad", owner_uid="user-A", question_ids=[30], total=1))
    db_session.add(Questao(id=30, enunciado_md="Q30"))
    db_session.add_all(
        [
            Resolucao(id=10, questao_id=30, caderno_id=60, usuario_uid="user-A", acertou=True),
            Resolucao(id=11, questao_id=30, caderno_id=60, usuario_uid="user-B", acertou=False),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    r = await client.get("/api/q/cadernos/60/estatisticas")
    assert r.status_code == 200
    body = r.json()
    assert body["resolvidas"] == 1
    assert body["acertos"] == 1
    assert body["erros"] == 0


async def test_stats_detalhe_so_do_usuario(client, db_session, auth_state):
    db_session.add(CadernoQuestoes(id=61, nome="cad", owner_uid="user-A", question_ids=[31], total=1))
    db_session.add(Questao(id=31, enunciado_md="Q31"))
    db_session.add_all(
        [
            Resolucao(id=20, questao_id=31, caderno_id=61, usuario_uid="user-A", acertou=True, tempo_segundos=40),
            Resolucao(id=21, questao_id=31, caderno_id=61, usuario_uid="user-B", acertou=False, tempo_segundos=99),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    r = await client.get("/api/q/cadernos/61/stats-detalhe")
    assert r.status_code == 200
    body = r.json()
    assert body["resolvidas"] == 1
    assert body["acertos"] == 1
    assert body["tempo_total_segundos"] == 40


# ─── Anotações por usuário ───────────────────────────────


async def test_anotacoes_isoladas_por_usuario(client, db_session, auth_state):
    db_session.add(CadernoQuestoes(id=70, nome="cad", owner_uid="user-A", question_ids=[40], total=1))
    # Catálogo de guia para B poder acessar o mesmo caderno (estudo compartilhado).
    db_session.add(Guia(id=3, tc_guia_id=997, nome="Guia Z"))
    db_session.add(GuiaCaderno(id=3, guia_id=3, tc_caderno_id=33345, nome="Cap", caderno_id=70))
    db_session.add(Questao(id=40, enunciado_md="Q40"))
    await db_session.commit()

    payload_a = {
        "canvas_json": {"version": 1, "cardSize": None, "strokes": [{"id": "a"}]},
        "strikes_json": {"version": 1, "targets": []},
    }
    payload_b = {
        "canvas_json": {"version": 1, "cardSize": None, "strokes": [{"id": "b"}]},
        "strikes_json": {"version": 1, "targets": []},
    }

    auth_state["user"] = A
    await client.put("/api/q/cadernos/70/questoes/40/annotations", json=payload_a)
    auth_state["user"] = B
    await client.put("/api/q/cadernos/70/questoes/40/annotations", json=payload_b)

    auth_state["user"] = A
    ra = await client.get("/api/q/cadernos/70/questoes/40/annotations")
    assert ra.json()["canvas_json"]["strokes"] == [{"id": "a"}]

    auth_state["user"] = B
    rb = await client.get("/api/q/cadernos/70/questoes/40/annotations")
    assert rb.json()["canvas_json"]["strokes"] == [{"id": "b"}]


# ─── Dashboard ───────────────────────────────────────────


async def test_dashboard_usuario_novo_tudo_zero(client, auth_state):
    auth_state["user"] = B
    r = await client.get("/api/q/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["resolvidas"] == 0
    assert body["acertos"] == 0
    assert body["erros"] == 0
    assert body["taxa"] == 0
    assert body["total_horas_segundos"] == 0
    assert body["streak_dias"] == 0
    assert body["por_disciplina"] == []
    assert body["atividade_recente"] == []
    assert body["ultimas_pastas"] == []


async def test_dashboard_exige_login(client, auth_state):
    auth_state["user"] = None
    r = await client.get("/api/q/dashboard")
    assert r.status_code == 401


async def test_dashboard_agrega_e_isola_por_usuario(client, db_session, auth_state):
    db_session.add(Materia(id=1, nome="Direito Constitucional"))
    db_session.add(Questao(id=80, enunciado_md="Q80", materia_id=1))
    hoje = datetime.now()
    ontem = hoje - timedelta(days=1)
    db_session.add_all(
        [
            Resolucao(id=30, questao_id=80, usuario_uid="user-A", acertou=True, tempo_segundos=30, created_at=hoje),
            Resolucao(id=31, questao_id=80, usuario_uid="user-A", acertou=False, tempo_segundos=20, created_at=ontem),
            # B não deve vazar para o dashboard de A
            Resolucao(id=32, questao_id=80, usuario_uid="user-B", acertou=True, tempo_segundos=999, created_at=hoje),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    r = await client.get("/api/q/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["resolvidas"] == 2
    assert body["acertos"] == 1
    assert body["erros"] == 1
    assert body["taxa"] == 50.0
    assert body["total_horas_segundos"] == 50
    assert body["streak_dias"] == 2
    disc = {d["nome"]: d for d in body["por_disciplina"]}
    assert "Direito Constitucional" in disc
    assert disc["Direito Constitucional"]["total"] == 2
    assert disc["Direito Constitucional"]["acertos"] == 1
    assert disc["Direito Constitucional"]["erros"] == 1
    assert disc["Direito Constitucional"]["tempo_segundos"] == 50


async def test_dashboard_ultimos_cadernos_por_recencia(client, db_session, auth_state):
    """Últimos cadernos acessados = cadernos com Resolução mais recente do
    usuário, ordenados por recência; isolados por usuário."""
    db_session.add(Questao(id=90, enunciado_md="Q90"))
    db_session.add_all(
        [
            CadernoQuestoes(id=100, nome="Const", pasta="OAB", owner_uid="user-A", question_ids=[90], total=1),
            CadernoQuestoes(id=101, nome="Mat", pasta="ENEM", owner_uid="user-A", question_ids=[90], total=1),
            CadernoQuestoes(id=102, nome="Solto", pasta=None, owner_uid="user-A", question_ids=[90], total=1),
        ]
    )
    hoje = datetime.now()
    db_session.add_all(
        [
            Resolucao(id=40, questao_id=90, caderno_id=101, usuario_uid="user-A", acertou=True, created_at=hoje - timedelta(days=3)),
            Resolucao(id=41, questao_id=90, caderno_id=102, usuario_uid="user-A", acertou=True, created_at=hoje - timedelta(days=1)),
            Resolucao(id=42, questao_id=90, caderno_id=100, usuario_uid="user-A", acertou=True, created_at=hoje),
            # B em OAB não deve vazar para o de A
            Resolucao(id=43, questao_id=90, caderno_id=100, usuario_uid="user-B", acertou=True, created_at=hoje),
            # Resolução avulsa (sem caderno) é ignorada (não tem caderno)
            Resolucao(id=44, questao_id=90, caderno_id=None, usuario_uid="user-A", acertou=True, created_at=hoje),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    body = (await client.get("/api/q/dashboard")).json()
    cadernos = body["ultimas_pastas"]
    # Const/OAB (hoje) > Solto/None (ontem) > Mat/ENEM (3d)
    assert [c["caderno_id"] for c in cadernos] == [100, 102, 101]
    assert [c["nome"] for c in cadernos] == ["Const", "Solto", "Mat"]
    assert [c["pasta"] for c in cadernos] == ["OAB", None, "ENEM"]
    assert all(c["ultimo_acesso"] for c in cadernos)

    # B só enxerga a própria atividade
    auth_state["user"] = B
    body_b = (await client.get("/api/q/dashboard")).json()
    assert [c["caderno_id"] for c in body_b["ultimas_pastas"]] == [100]


# ─── Dashboard por disciplina (estatísticas da matéria) ──


async def test_dashboard_disciplina_exige_login(client, auth_state):
    auth_state["user"] = None
    r = await client.get("/api/q/dashboard/disciplina/1")
    assert r.status_code == 401


async def test_dashboard_disciplina_inexistente_404(client, auth_state):
    auth_state["user"] = A
    r = await client.get("/api/q/dashboard/disciplina/99999")
    assert r.status_code == 404


async def test_dashboard_disciplina_agrega_por_assunto_e_isola(client, db_session, auth_state):
    from models import Assunto

    db_session.add(Materia(id=1, nome="Direito Constitucional"))
    db_session.add(Materia(id=2, nome="Matemática"))
    assunto = Assunto(id=1, materia_id=1, nome="Controle de Constitucionalidade")
    db_session.add(assunto)
    q_com_assunto = Questao(id=80, enunciado_md="Q80", materia_id=1)
    q_com_assunto.assuntos = [assunto]
    db_session.add(q_com_assunto)
    db_session.add(Questao(id=81, enunciado_md="Q81", materia_id=1))
    db_session.add(Questao(id=82, enunciado_md="Q82", materia_id=2))
    # commit em duas etapas: garante questões no banco antes das resoluções
    # (sem relationship Resolucao→Questao o unit-of-work não ordena os INSERTs)
    await db_session.commit()
    hoje = datetime.now()
    db_session.add_all(
        [
            Resolucao(id=30, questao_id=80, usuario_uid="user-A", acertou=True, tempo_segundos=30, created_at=hoje),
            Resolucao(id=31, questao_id=81, usuario_uid="user-A", acertou=False, tempo_segundos=20, created_at=hoje),
            # Outra matéria não entra na conta desta
            Resolucao(id=32, questao_id=82, usuario_uid="user-A", acertou=True, tempo_segundos=99, created_at=hoje),
            # B não vaza para o A
            Resolucao(id=33, questao_id=80, usuario_uid="user-B", acertou=True, tempo_segundos=999, created_at=hoje),
        ]
    )
    await db_session.commit()

    auth_state["user"] = A
    r = await client.get("/api/q/dashboard/disciplina/1")
    assert r.status_code == 200
    body = r.json()
    assert body["materia_id"] == 1
    assert body["nome"] == "Direito Constitucional"
    assert body["resolvidas"] == 2
    assert body["acertos"] == 1
    assert body["erros"] == 1
    assert body["taxa"] == 50.0
    assert body["tempo_segundos"] == 50
    assuntos = {a["nome"]: a for a in body["por_assunto"]}
    assert assuntos["Controle de Constitucionalidade"]["total"] == 1
    assert assuntos["Controle de Constitucionalidade"]["acertos"] == 1
    assert assuntos["Controle de Constitucionalidade"]["erros"] == 0
    assert len(body["atividade_recente"]) == 1
    assert body["atividade_recente"][0]["resolvidas"] == 2

    # /dashboard agora expõe materia_id para linkar a página da matéria
    body_dash = (await client.get("/api/q/dashboard")).json()
    disc = {d["nome"]: d for d in body_dash["por_disciplina"]}
    assert disc["Direito Constitucional"]["materia_id"] == 1

    # B só enxerga o próprio desempenho
    auth_state["user"] = B
    body_b = (await client.get("/api/q/dashboard/disciplina/1")).json()
    assert body_b["resolvidas"] == 1
    assert body_b["acertos"] == 1
