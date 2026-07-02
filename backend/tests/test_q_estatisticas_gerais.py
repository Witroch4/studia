"""Quartel-general: GET /api/q/estatisticas-gerais (agregado de todos os cadernos)."""

from datetime import datetime

import pytest

from models import Banca, CadernoQuestoes, Materia, Questao, QuestaoFavorita, Resolucao

pytestmark = pytest.mark.asyncio


async def _seed(db_session):
    db_session.add_all([
        Materia(id=1, nome="Português"),
        Materia(id=2, nome="Matemática"),
        Banca(id=1, nome="Cesgranrio", slug="cesgranrio", sigla="CESGRANRIO"),
    ])
    db_session.add_all([
        Questao(id=301, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q</p>", gabarito="A", status="ATIVA", materia_id=1, banca_id=1),
        Questao(id=302, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q</p>", gabarito="B", status="ATIVA", materia_id=1, banca_id=1),
        Questao(id=303, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q</p>", gabarito="A", status="ATIVA", materia_id=2, banca_id=1),
    ])
    db_session.add_all([
        CadernoQuestoes(id=30, nome="Caderno A", owner_uid="admin-1", question_ids=[301, 302], total=2),
        CadernoQuestoes(id=31, nome="Caderno B", owner_uid="admin-1", question_ids=[303], total=1),
        CadernoQuestoes(id=32, nome="Caderno Vazio", owner_uid="admin-1", question_ids=[], total=0),
    ])

    def res(qid, cad, acertou, seg, tempo=60, uid="admin-1"):
        return Resolucao(
            questao_id=qid, caderno_id=cad, usuario_uid=uid, resposta="A",
            acertou=acertou, tempo_segundos=tempo,
            created_at=datetime(2026, 7, 1, 12, 0, seg),
        )

    # q301: errou e depois acertou (última vale) — caderno 30.
    db_session.add(res(301, 30, False, 1))
    db_session.add(res(301, 30, True, 2))
    # q302: errou — caderno 30.
    db_session.add(res(302, 30, False, 3))
    # q303: acertou — caderno 31.
    db_session.add(res(303, 31, True, 4))
    # Resolução de OUTRO usuário nunca entra.
    db_session.add(res(302, 30, True, 5, uid="user-B"))

    db_session.add(QuestaoFavorita(questao_id=303, owner_uid="admin-1"))
    await db_session.commit()


async def test_estatisticas_gerais_agrega_tudo_do_usuario(client, db_session):
    await _seed(db_session)

    r = await client.get("/api/q/estatisticas-gerais")
    assert r.status_code == 200, r.text
    body = r.json()

    resumo = body["resumo"]
    assert resumo["resolvidas"] == 3          # questões distintas
    assert resumo["acertos"] == 2             # q301 (última) + q303
    assert resumo["erros"] == 1               # q302
    assert resumo["tentativas"] == 4          # inclui a re-tentativa, exclui user-B
    assert resumo["taxa"] == pytest.approx(66.7, abs=0.1)
    assert resumo["tempo_total_segundos"] == 240
    assert resumo["cadernos"] == 3
    assert resumo["cadernos_ativos"] == 2
    assert resumo["favoritas"] == 1

    cadernos = {c["id"]: c for c in body["cadernos"]}
    assert set(cadernos) == {30, 31, 32}
    assert cadernos[30]["resolvidas"] == 2
    assert cadernos[30]["acertos"] == 1
    assert cadernos[30]["erros"] == 1
    assert cadernos[30]["tempo_segundos"] == 180
    assert cadernos[32]["resolvidas"] == 0
    assert cadernos[32]["ultima_atividade"] is None

    materias = {g["nome"]: g for g in body["por_materia"]}
    assert materias["Português"]["resolvidas"] == 2
    assert materias["Português"]["acertos"] == 1
    assert materias["Matemática"]["acertos"] == 1

    bancas = {g["nome"]: g for g in body["por_banca"]}
    assert bancas["CESGRANRIO"]["resolvidas"] == 3

    assert body["por_dia"] == [{"data": "2026-07-01", "resolvidas": 4, "acertos": 2}]


async def test_estatisticas_gerais_usuario_novo_zerado(client, db_session):
    r = await client.get("/api/q/estatisticas-gerais")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resumo"]["resolvidas"] == 0
    assert body["resumo"]["taxa"] == 0
    assert body["por_dia"] == []
    assert body["por_materia"] == []
    assert body["cadernos"] == []
