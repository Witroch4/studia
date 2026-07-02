"""Tela de estatísticas do caderno: resumo por questão distinta, árvore
matéria→assunto, comunidade, derivar estendido e zerar resoluções."""

from datetime import datetime

import pytest
from sqlalchemy import select

from models import (
    Assunto,
    CadernoQuestoes,
    Materia,
    Questao,
    QuestaoFavorita,
    Resolucao,
)

pytestmark = pytest.mark.asyncio


async def _seed(db_session):
    """Caderno 20 com 4 questões: 2 de Solos (assunto Sondagens), 1 de
    Estruturas (assunto Isostática) e 1 anulada (Solos, sem assunto)."""
    m_solos = Materia(id=1, nome="Mecânica de Solos")
    m_estr = Materia(id=2, nome="Análise Estrutural")
    a_sond = Assunto(id=11, materia_id=1, nome="Sondagens")
    a_iso = Assunto(id=21, materia_id=2, nome="Isostática")
    db_session.add_all([m_solos, m_estr, a_sond, a_iso])

    q1 = Questao(id=201, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q1</p>", gabarito="A", status="ATIVA", materia_id=1)
    q2 = Questao(id=202, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q2</p>", gabarito="B", status="ATIVA", materia_id=1)
    q3 = Questao(id=203, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q3</p>", gabarito="A", status="ATIVA", materia_id=2)
    q4 = Questao(id=204, tipo="MULTIPLA_ESCOLHA", enunciado_html="<p>q4</p>", gabarito="A", status="ANULADA", materia_id=1)
    q1.assuntos.append(a_sond)
    q2.assuntos.append(a_sond)
    q3.assuntos.append(a_iso)
    db_session.add_all([q1, q2, q3, q4])

    db_session.add(CadernoQuestoes(
        id=20, nome="Caderno Stats", owner_uid="admin-1", pasta="Estudos",
        question_ids=[201, 202, 203, 204], total=4,
    ))
    await db_session.commit()


def _resolucao(qid, acertou, *, quando, caderno_id=20, uid="admin-1", tempo=30):
    return Resolucao(
        questao_id=qid, caderno_id=caderno_id, usuario_uid=uid,
        resposta="A", acertou=acertou, tempo_segundos=tempo,
        created_at=datetime(2026, 7, 1, 12, 0, quando),
    )


async def test_resumo_conta_por_questao_distinta_e_ultima_resolucao(client, db_session):
    await _seed(db_session)
    # q1: errou primeiro, acertou depois → conta como ACERTO (última vale).
    db_session.add(_resolucao(201, False, quando=1))
    db_session.add(_resolucao(201, True, quando=2))
    # q2: errou.
    db_session.add(_resolucao(202, False, quando=3))
    # favorita q3
    db_session.add(QuestaoFavorita(questao_id=203, owner_uid="admin-1"))
    await db_session.commit()

    r = await client.get("/api/q/cadernos/20/stats-detalhe")
    assert r.status_code == 200, r.text
    body = r.json()

    resumo = body["resumo"]
    assert resumo["questoes_total"] == 4
    assert resumo["anuladas"] == 1
    assert resumo["resolvidas"] == 2      # q1 + q2 (distintas)
    assert resumo["acertos"] == 1         # q1 (última resolução)
    assert resumo["erros"] == 1           # q2
    assert resumo["em_branco"] == 1       # q3 (anulada fora da conta)
    assert resumo["favoritas"] == 1
    assert resumo["anotadas"] == 0

    # Compat: os campos antigos (por tentativa) continuam existindo.
    assert body["resolvidas"] == 3


async def test_arvore_agrupa_materia_e_assunto(client, db_session):
    await _seed(db_session)
    db_session.add(_resolucao(201, True, quando=1))
    db_session.add(_resolucao(202, False, quando=2))
    await db_session.commit()

    r = await client.get("/api/q/cadernos/20/stats-detalhe")
    assert r.status_code == 200, r.text
    arvore = {m["nome"]: m for m in r.json()["arvore"]}

    solos = arvore["Mecânica de Solos"]
    assert solos["total"] == 3            # inclui a anulada
    assert solos["anuladas"] == 1
    assert solos["resolvidas"] == 2
    assert solos["acertos"] == 1
    assert solos["erros"] == 1
    assuntos = {a["nome"]: a for a in solos["assuntos"]}
    assert assuntos["Sondagens"]["total"] == 2
    assert assuntos["Sondagens"]["acertos"] == 1

    estruturas = arvore["Análise Estrutural"]
    assert estruturas["total"] == 1
    assert estruturas["resolvidas"] == 0


async def test_stats_comunidade_exclui_o_proprio_usuario(client, db_session):
    await _seed(db_session)
    db_session.add(_resolucao(201, True, quando=1))                      # eu
    db_session.add(_resolucao(201, False, quando=2, uid="user-B", caderno_id=None))
    db_session.add(_resolucao(202, True, quando=3, uid="user-B", caderno_id=None))
    await db_session.commit()

    r = await client.get("/api/q/cadernos/20/stats-comunidade")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["usuarios"] == 1
    assert body["resolvidas"] == 2
    assert body["acertos"] == 1
    assert body["erros"] == 1
    # Dificuldade considera o universo (eu + user-B): 1 erro em 3 → 33.3%.
    assert body["dificuldade"] == pytest.approx(33.3, abs=0.1)


async def test_derivar_em_branco_e_selecao_por_materia_assunto(client, db_session):
    await _seed(db_session)
    db_session.add(_resolucao(201, True, quando=1))
    await db_session.commit()

    # Em branco: q2 e q3 (q1 resolvida, q4 anulada fora).
    r = await client.post("/api/q/cadernos/20/derivar", json={"tipo": "em_branco"})
    assert r.status_code == 200, r.text
    novo = await db_session.get(CadernoQuestoes, r.json()["id"])
    assert novo.question_ids == [202, 203]

    # Clone completo.
    r = await client.post("/api/q/cadernos/20/derivar", json={"tipo": "todas"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 4

    # Seleção: só o assunto Isostática (q3), todas as questões dele.
    r = await client.post(
        "/api/q/cadernos/20/derivar",
        json={"tipo": "todas", "assunto_ids": [21]},
    )
    assert r.status_code == 200, r.text
    novo = await db_session.get(CadernoQuestoes, r.json()["id"])
    assert novo.question_ids == [203]

    # Seleção por matéria: resolvidas de Solos → q1.
    r = await client.post(
        "/api/q/cadernos/20/derivar",
        json={"tipo": "resolvidas", "materia_ids": [1]},
    )
    assert r.status_code == 200, r.text
    novo = await db_session.get(CadernoQuestoes, r.json()["id"])
    assert novo.question_ids == [201]


async def test_zerar_resolucoes_do_caderno(client, db_session):
    await _seed(db_session)
    db_session.add(_resolucao(201, True, quando=1))
    db_session.add(_resolucao(202, False, quando=2))
    # Resolução de OUTRO usuário nunca é tocada.
    db_session.add(_resolucao(201, True, quando=3, uid="user-B"))
    await db_session.commit()

    r = await client.post("/api/q/cadernos/20/zerar-resolucoes", json={"tipo": "erradas"})
    assert r.status_code == 200, r.text
    assert r.json()["apagadas"] == 1

    r = await client.post("/api/q/cadernos/20/zerar-resolucoes", json={"tipo": "todas"})
    assert r.status_code == 200, r.text
    assert r.json()["apagadas"] == 1  # sobrou só a minha certa

    restantes = (await db_session.execute(
        select(Resolucao).where(Resolucao.caderno_id == 20)
    )).scalars().all()
    assert [x.usuario_uid for x in restantes] == ["user-B"]
