import pytest
from app.tasks import comentarios as m

@pytest.mark.asyncio
async def test_pace_so_quando_bate_no_tc(monkeypatch):
    chamadas, sleeps = [], []
    async def fake_post(url, quadro):
        chamadas.append(quadro)
        # alunos já importado (sem TC), professores fez fetch (bateu no TC)
        return {"importados": 0 if quadro == "alunos" else 1,
                "ja_importado": quadro == "alunos"}
    async def fake_sleep(s): sleeps.append(s)
    # neutraliza o ledger (lease/mark) — testamos só a lógica de pacing/chamadas
    monkeypatch.setattr(m, "_lease", lambda **k: {"unit_id": 1, "job_id": 1})
    monkeypatch.setattr(m, "_mark_done", lambda **k: None)
    monkeypatch.setattr(m, "_enqueue_next", lambda **k: None)
    res = await m._processar_unit_comentarios(
        99, 1, sleep=fake_sleep, post=fake_post)
    assert chamadas == ["alunos", "professores"]
    assert len(sleeps) == 1            # dormiu só 1x (o quadro que bateu no TC)
    assert 5.0 <= sleeps[0] <= 15.0
    assert res["coments_professores"] == 1 and res["coments_alunos"] == 0
