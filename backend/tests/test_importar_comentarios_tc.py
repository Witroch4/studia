import pytest, httpx
from datetime import datetime, timezone
from sqlalchemy import select
import q_router
from models import Questao, QuestaoComentario, QuestaoTcImport


def _mock_scraper(monkeypatch, comentarios):
    def handler(req):
        assert req.url.params.get("task") == "forum_lazy"
        return httpx.Response(200, json={"comentarios": comentarios})
    real = httpx.AsyncClient
    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)
    monkeypatch.setattr(q_router.httpx, "AsyncClient", fake_client)


@pytest.mark.asyncio
async def test_importa_e_e_idempotente(db_session, client, monkeypatch):
    db_session.add(Questao(id=10, id_externo=2272394, enunciado_md="x"))
    await db_session.commit()
    _mock_scraper(monkeypatch, [
        {"tc_comentario_id": 555, "tc_parent_id": None, "autor_nome": "Fulano",
         "autor_tipo": "aluno", "curtidas": 4, "md": "resp", "imagens": [],
         "publicado_em": None},
    ])
    r1 = await client.post("/api/q/questoes/10/importar-comentarios-tc?quadro=alunos")
    assert r1.status_code == 200 and r1.json()["importados"] == 1
    r2 = await client.post("/api/q/questoes/10/importar-comentarios-tc?quadro=alunos")
    assert r2.json()["ja_importado"] is True and r2.json()["importados"] == 0
    n = (await db_session.execute(select(QuestaoComentario).where(
        QuestaoComentario.tc_comentario_id == 555))).scalars().all()
    assert len(n) == 1  # não duplicou
    m = (await db_session.execute(select(QuestaoTcImport).where(
        QuestaoTcImport.questao_id == 10, QuestaoTcImport.quadro == "alunos"))).scalar_one()
    assert m.count == 1


@pytest.mark.asyncio
async def test_sem_id_externo_retorna_noop(db_session, client, monkeypatch):
    """Questão existente mas sem id_externo (guia manual) deve retornar 200 sem scrape."""
    db_session.add(Questao(id=20, id_externo=None, enunciado_md="questão manual"))
    await db_session.commit()

    # Garante que o scraper NÃO é chamado (monkeypatch levanta se for)
    def scraper_nao_deve_ser_chamado(req):
        raise AssertionError("scraper não deveria ser chamado para questão sem id_externo")
    real = httpx.AsyncClient
    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(scraper_nao_deve_ser_chamado)
        return real(*a, **k)
    monkeypatch.setattr(q_router.httpx, "AsyncClient", fake_client)

    r = await client.post("/api/q/questoes/20/importar-comentarios-tc?quadro=alunos")
    assert r.status_code == 200
    body = r.json()
    assert body["importados"] == 0
    assert body["ja_importado"] is False

    # Nenhum comentário deve ter sido criado
    comentarios = (await db_session.execute(
        select(QuestaoComentario).where(QuestaoComentario.questao_id == 20)
    )).scalars().all()
    assert len(comentarios) == 0


@pytest.mark.asyncio
async def test_questao_inexistente_retorna_404(client):
    """ID que não existe no banco deve retornar HTTP 404."""
    r = await client.post("/api/q/questoes/99999/importar-comentarios-tc?quadro=alunos")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_persiste_publicado_em_aluno(db_session, client, monkeypatch):
    """I-1: publicado_em no formato aluno (DD/MM/AAAA HH:MM:SS) deve ser persistido."""
    db_session.add(Questao(id=30, id_externo=9000001, enunciado_md="x"))
    await db_session.commit()
    _mock_scraper(monkeypatch, [
        {"tc_comentario_id": 701, "tc_parent_id": None, "autor_nome": "Aluno",
         "autor_tipo": "aluno", "curtidas": 0, "md": "texto", "imagens": [],
         "publicado_em": "02/12/2023 20:09:16"},
    ])
    r = await client.post("/api/q/questoes/30/importar-comentarios-tc?quadro=alunos")
    assert r.status_code == 200 and r.json()["importados"] == 1

    com = (await db_session.execute(
        select(QuestaoComentario).where(QuestaoComentario.tc_comentario_id == 701)
    )).scalar_one()
    expected = datetime(2023, 12, 2, 20, 9, 16, tzinfo=timezone.utc)
    assert com.publicado_em == expected, f"got {com.publicado_em!r}"


@pytest.mark.asyncio
async def test_persiste_publicado_em_professor(db_session, client, monkeypatch):
    """I-1: publicado_em no formato professor (AAAA-MM-DD) deve ser persistido."""
    db_session.add(Questao(id=31, id_externo=9000002, enunciado_md="y"))
    await db_session.commit()
    _mock_scraper(monkeypatch, [
        {"tc_comentario_id": -9000002, "tc_parent_id": None, "autor_nome": "Prof",
         "autor_tipo": "professor", "curtidas": 0, "md": "explicação", "imagens": [],
         "publicado_em": "2024-04-28"},
    ])
    r = await client.post("/api/q/questoes/31/importar-comentarios-tc?quadro=professores")
    assert r.status_code == 200 and r.json()["importados"] == 1

    com = (await db_session.execute(
        select(QuestaoComentario).where(QuestaoComentario.tc_comentario_id == -9000002)
    )).scalar_one()
    expected = datetime(2024, 4, 28, tzinfo=timezone.utc)
    assert com.publicado_em == expected, f"got {com.publicado_em!r}"
