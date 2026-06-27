import pytest
import httpx
import q_router


from models import CadernoQuestoes


@pytest.mark.asyncio
async def test_admin_enfileira_comentarios(db_session, client, monkeypatch):
    db_session.add(
        CadernoQuestoes(
            id=300,
            owner_uid="u1",
            tc_caderno_id=42,
            question_ids=[11, 12, 13],
            total=3,
            nome="X",
        )
    )
    await db_session.commit()

    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["json"] = req.content
        return httpx.Response(
            200,
            json={
                "job_id": 9,
                "status": "running",
                "total_units": 3,
                "enqueued_units": 1,
            },
        )

    real = httpx.AsyncClient
    monkeypatch.setattr(
        q_router.httpx,
        "AsyncClient",
        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}),
    )

    r = await client.post("/api/q/cadernos/300/importar-comentarios-tc")
    assert r.status_code == 202
    assert r.json()["job_id"] == 9
    assert "enqueue/comentarios" in captured["url"]


@pytest.mark.asyncio
async def test_caderno_nao_encontrado_404(db_session, client, monkeypatch):
    r = await client.post("/api/q/cadernos/9999/importar-comentarios-tc")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_caderno_sem_questoes_422(db_session, client, monkeypatch):
    db_session.add(
        CadernoQuestoes(
            id=301,
            owner_uid="u1",
            tc_caderno_id=43,
            question_ids=[],
            total=0,
            nome="Vazio",
        )
    )
    await db_session.commit()

    r = await client.post("/api/q/cadernos/301/importar-comentarios-tc")
    assert r.status_code == 422
