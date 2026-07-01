"""Meta diária: conta ilimitada (PRO/admin) que bate 15 questões distintas no
dia recebe meta_diaria.batida_agora=True UMA vez (transição 14→15). Grátis
nunca dispara (trava em 10)."""

from datetime import datetime, timedelta, timezone

import pytest

from auth import CurrentUser
from models import Assinatura, CadernoQuestoes, Questao

pytestmark = pytest.mark.asyncio

USER_A = CurrentUser(id="user-A", email="user-A@studia.test", name="user-A", role="user", banned=False)


async def _seed_caderno(db_session, *, caderno_id: int, owner_uid: str, n: int) -> list[int]:
    """Cria um caderno + n questões distintas (gabarito A). Retorna os ids."""
    base = caderno_id * 1000
    ids = list(range(base, base + n))
    db_session.add(CadernoQuestoes(id=caderno_id, nome="Meta", owner_uid=owner_uid, question_ids=ids, total=n))
    for qid in ids:
        db_session.add(Questao(
            id=qid, id_externo=qid, tipo="MULTIPLA_ESCOLHA",
            enunciado_html="<p>Q</p>", gabarito="A", status="ATIVA",
        ))
    await db_session.commit()
    return ids


async def test_ilimitado_dispara_na_15a_e_so_nela(client, db_session):
    # usuário default do conftest = admin-1 (ilimitado).
    ids = await _seed_caderno(db_session, caderno_id=500, owner_uid="admin-1", n=16)
    for i, qid in enumerate(ids, start=1):
        r = await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 500})
        assert r.status_code == 200, r.text
        md = r.json()["meta_diaria"]
        assert md["meta"] == 15
        assert md["total"] == i
        assert md["batida_agora"] is (i == 15)  # true só na 15ª; 14 e 16 = false


async def test_repetir_a_15a_nao_redispara(client, db_session):
    ids = await _seed_caderno(db_session, caderno_id=501, owner_uid="admin-1", n=15)
    for qid in ids:
        await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 501})
    # repetir a 15ª questão (caminho idempotente) NÃO pode redisparar.
    r = await client.post(f"/api/q/{ids[14]}/responder", json={"resposta": "B", "caderno_id": 501})
    body = r.json()
    assert body["ja_resolvida"] is True
    assert body["meta_diaria"]["batida_agora"] is False
    assert body["meta_diaria"]["total"] == 15


async def test_gratis_nunca_dispara(client, db_session, auth_state):
    auth_state["user"] = USER_A  # plano grátis
    ids = await _seed_caderno(db_session, caderno_id=502, owner_uid="user-A", n=11)
    for qid in ids[:10]:
        r = await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 502})
        assert r.status_code == 200
        assert r.json()["meta_diaria"]["batida_agora"] is False
    # 11ª questão nova → 402 (limite grátis); nunca chega a 15.
    r11 = await client.post(f"/api/q/{ids[10]}/responder", json={"resposta": "A", "caderno_id": 502})
    assert r11.status_code == 402


async def test_combos_ocultos_disparam_nos_marcos_exatos(client, db_session):
    """Metas ocultas: 25→combo 2, 35→combo 3, 45→combo 4; fora dos marcos, None."""
    ids = await _seed_caderno(db_session, caderno_id=504, owner_uid="admin-1", n=46)
    esperado = {25: 2, 35: 3, 45: 4}
    for i, qid in enumerate(ids, start=1):
        r = await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 504})
        assert r.status_code == 200, r.text
        md = r.json()["meta_diaria"]
        assert md["combo"] == esperado.get(i), f"questão {i}: combo={md['combo']}"


async def test_repetir_marco_de_combo_nao_redispara(client, db_session):
    ids = await _seed_caderno(db_session, caderno_id=505, owner_uid="admin-1", n=25)
    for qid in ids:
        await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 505})
    # repetir a 25ª (caminho idempotente) NÃO pode redisparar o combo x2.
    r = await client.post(f"/api/q/{ids[24]}/responder", json={"resposta": "B", "caderno_id": 505})
    body = r.json()
    assert body["ja_resolvida"] is True
    assert body["meta_diaria"]["combo"] is None
    assert body["meta_diaria"]["total"] == 25


async def test_assinante_dispara_meta(client, db_session, auth_state):
    auth_state["user"] = USER_A
    db_session.add(Assinatura(
        usuario_uid="user-A", status="active",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    ids = await _seed_caderno(db_session, caderno_id=503, owner_uid="user-A", n=15)
    last = None
    for qid in ids:
        last = await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 503})
    assert last.json()["meta_diaria"]["batida_agora"] is True
