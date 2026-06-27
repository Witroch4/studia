import pytest, httpx
from app.tasks import comentarios as m

@pytest.mark.asyncio
async def test_pausa_solta_unit_e_para(monkeypatch):
    posts, released, enq = [], [], []
    monkeypatch.setattr(m, "_lease", lambda **k: {"unit_id": 9, "job_id": 1})
    monkeypatch.setattr(m, "_is_paused", lambda **k: True)
    monkeypatch.setattr(m, "_release", lambda **k: released.append(k["unit_id"]))
    monkeypatch.setattr(m, "_mark_done", lambda **k: None)
    monkeypatch.setattr(m, "_enqueue_next", lambda **k: enq.append(1))
    async def fake_post(q, quadro): posts.append(quadro); return {"importados": 0}
    res = await m._processar_unit_comentarios(50, 1, sleep=lambda *_: None, post=fake_post)
    assert res["status"] == "paused"
    assert posts == [] and released == [9] and enq == []  # não bateu no TC, soltou, não encadeou

@pytest.mark.asyncio
async def test_post_retry_5xx(monkeypatch):
    monkeypatch.setattr(m, "get_settings", lambda: type("S", (), {
        "backend_url": "http://b", "studia_internal_token": "t",
        "comentario_pause_min": 0.0, "comentario_pause_max": 0.0})())
    chamadas = {"n": 0}
    def handler(req):
        chamadas["n"] += 1
        return httpx.Response(502) if chamadas["n"] == 1 else httpx.Response(200, json={"importados": 2, "ja_importado": False})
    _RealAsyncClient = httpx.AsyncClient  # salva referência antes do patch
    monkeypatch.setattr(m.httpx, "AsyncClient",
                        lambda *a, **k: _RealAsyncClient(transport=httpx.MockTransport(handler)))
    out = await m._post_import(50, "alunos", _sleep=lambda *_: None)
    assert out["importados"] == 2 and chamadas["n"] == 2  # 1 retry após o 502
