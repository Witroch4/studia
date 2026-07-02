"""perfil_service: derivação de pontuação (fórum + metas/combos de resolucoes)."""

from datetime import datetime, timedelta

import pytest

import perfil_service
from models import PerfilUsuario, Questao, QuestaoComentario, Resolucao

pytestmark = pytest.mark.asyncio


def test_contar_marcos_marcos_cumulativos():
    # dia 30 → meta+X2; dia 45 → meta+X2+X3+X4; dia 14 → nada
    marcos = perfil_service.contar_marcos([30, 45, 14])
    assert marcos == {"metas": 2, "combos_x2": 2, "combos_x3": 1, "combos_x4": 1}


def test_pontos_estudo():
    marcos = {"metas": 2, "combos_x2": 2, "combos_x3": 1, "combos_x4": 1}
    # 2*10 + 2*20 + 1*30 + 1*40 = 130
    assert perfil_service.pontos_estudo(marcos) == 130


async def _seed_questoes(db_session, base: int, n: int) -> list[int]:
    ids = list(range(base, base + n))
    for qid in ids:
        db_session.add(Questao(id=qid, id_externo=qid, tipo="MULTIPLA_ESCOLHA",
                               enunciado_html="<p>Q</p>", gabarito="A", status="ATIVA"))
    await db_session.commit()
    return ids


async def _seed_dia(db_session, uid: str, qids: list[int], dia_utc: datetime, acertos: int):
    """Uma resolução por questão no timestamp dado (meio-dia local, longe do corte)."""
    for i, qid in enumerate(qids):
        db_session.add(Resolucao(questao_id=qid, usuario_uid=uid,
                                 resposta="A", acertou=(i < acertos), created_at=dia_utc))
    await db_session.commit()


async def test_pontos_forum_ignora_tc_e_deletados(db_session):
    qids = await _seed_questoes(db_session, 9000, 1)
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="studia",
                                     owner_uid="user-A", texto_md="a", score=5))
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="studia",
                                     owner_uid="user-A", texto_md="b", score=-2))
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="studia", owner_uid="user-A",
                                     texto_md="c", score=100, deleted_at=datetime.utcnow()))
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="tc",
                                     autor_nome="Fulano", texto_md="d", score=50))
    await db_session.commit()
    forum = await perfil_service.pontos_forum(db_session, "user-A")
    assert forum == {"pontos": 3, "comentarios": 2}


async def test_resumo_perfil_deriva_metas_e_combos(db_session):
    # 15:00 UTC = 12:00 America/Fortaleza — bem longe do corte de meia-noite.
    hoje = datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)
    ontem, anteontem = hoje - timedelta(days=1), hoje - timedelta(days=2)
    qids = await _seed_questoes(db_session, 10000, 45)
    await _seed_dia(db_session, "user-A", qids[:30], anteontem, acertos=20)  # meta + X2
    await _seed_dia(db_session, "user-A", qids[:45], ontem, acertos=40)      # meta + X2+X3+X4
    await _seed_dia(db_session, "user-A", qids[:14], hoje, acertos=10)       # nada
    resumo = await perfil_service.resumo_perfil(db_session, "user-A")
    p = resumo["pontuacao"]
    assert p["metas"] == 2 and p["combos_x2"] == 2
    assert p["combos_x3"] == 1 and p["combos_x4"] == 1
    assert p["estudo"] == 130
    assert p["forum"] == 0
    assert p["total"] == 130
    assert resumo["resolvidas"] == 30 + 45 + 14
    assert resumo["streak_dias"] == 3  # anteontem, ontem e hoje


async def test_resumo_repeticao_no_dia_nao_infla(db_session):
    """Repetir a MESMA questão várias vezes no dia conta 1 questão distinta."""
    hoje = datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)
    qids = await _seed_questoes(db_session, 11000, 1)
    for _ in range(20):
        db_session.add(Resolucao(questao_id=qids[0], usuario_uid="user-B",
                                 resposta="A", acertou=True, created_at=hoje))
    await db_session.commit()
    resumo = await perfil_service.resumo_perfil(db_session, "user-B")
    assert resumo["pontuacao"]["metas"] == 0
    assert resumo["pontuacao"]["estudo"] == 0


async def test_perfis_forum_por_uids_respeita_privacidade(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A", apelido="rochedo-16",
                                 avatar_key="avatars/x.webp", mostrar_foto=False))
    db_session.add(PerfilUsuario(owner_uid="user-B", apelido="oculto", perfil_publico=False))
    db_session.add(PerfilUsuario(owner_uid="user-C"))  # sem apelido
    await db_session.commit()
    perfis = await perfil_service.perfis_forum_por_uids(
        db_session, {"user-A", "user-B", "user-C", "user-Z"})
    assert set(perfis) == {"user-A"}
    assert perfis["user-A"]["apelido"] == "rochedo-16"
    assert perfis["user-A"]["avatar_url"] is None  # mostrar_foto=False
