import pytest, httpx
from sqlalchemy import select
import q_router
from models import Questao, QuestaoComentario, QuestaoTcImport


def _mock_scraper(monkeypatch, comentarios):
    def handler(req):
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
