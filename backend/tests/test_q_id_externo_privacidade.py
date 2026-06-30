from __future__ import annotations

import pytest

from auth import CurrentUser
from models import Banca, CadernoQuestoes, Questao, Resolucao
from tests.conftest import ADMIN_USER, USER_B

pytestmark = pytest.mark.asyncio


async def test_buscar_questao_externo_so_admin_recebe_id_externo(client, db_session, auth_state):
    db_session.add(Questao(id=910, id_externo=990910, status="ATIVA", gabarito="A"))
    await db_session.commit()

    auth_state["user"] = USER_B
    comum = (await client.get("/api/q/questoes/buscar-externo/990910?is_admin=true&role=admin")).json()
    assert comum["found"] is True
    assert comum["questao"]["id"] == 910
    assert "id_externo" not in comum["questao"]

    auth_state["user"] = CurrentUser(id="user-B", email="user-B@t", name="user-B", role="admin", banned=False)
    admin = (await client.get("/api/q/questoes/buscar-externo/990910")).json()
    assert admin["questao"]["id_externo"] == 990910


async def test_caderno_indice_e_gabarito_so_admin_recebem_id_externo(client, db_session, auth_state):
    db_session.add(
        CadernoQuestoes(
            id=91,
            nome="Privacidade",
            owner_uid="user-B",
            question_ids=[911],
            total=1,
        )
    )
    db_session.add(Questao(id=911, id_externo=990911, enunciado_md="Preview", status="ATIVA", gabarito="B"))
    await db_session.commit()

    auth_state["user"] = USER_B
    indice = (await client.get("/api/q/cadernos/91/indice")).json()
    assert indice["items"][0]["questao_id"] == 911
    assert "id_externo" not in indice["items"][0]
    gabarito = (await client.get("/api/q/cadernos/91/gabarito")).json()
    assert gabarito["items"][0]["questao_id"] == 911
    assert "id_externo" not in gabarito["items"][0]

    auth_state["user"] = CurrentUser(id="user-B", email="user-B@t", name="user-B", role="admin", banned=False)
    indice_admin = (await client.get("/api/q/cadernos/91/indice")).json()
    assert indice_admin["items"][0]["id_externo"] == 990911
    gabarito_admin = (await client.get("/api/q/cadernos/91/gabarito")).json()
    assert gabarito_admin["items"][0]["id_externo"] == 990911


async def test_stats_detalhe_so_admin_recebe_id_externo(client, db_session, auth_state):
    db_session.add(Banca(id=91, sigla="BNC", nome="Banca", slug="bnc"))
    db_session.add(
        CadernoQuestoes(
            id=92,
            nome="Estatisticas",
            owner_uid="user-B",
            question_ids=[912],
            total=1,
        )
    )
    db_session.add(Questao(id=912, id_externo=990912, banca_id=91, status="ATIVA", gabarito="C"))
    db_session.add(
        Resolucao(
            questao_id=912,
            caderno_id=92,
            usuario_uid="user-B",
            resposta="C",
            acertou=True,
            tempo_segundos=10,
        )
    )
    await db_session.commit()

    auth_state["user"] = USER_B
    comum = (await client.get("/api/q/cadernos/92/stats-detalhe")).json()
    assert comum["ultimas_resolucoes"][0]["questao_id"] == 912
    assert "id_externo" not in comum["ultimas_resolucoes"][0]

    auth_state["user"] = CurrentUser(id="user-B", email="user-B@t", name="user-B", role="admin", banned=False)
    admin = (await client.get("/api/q/cadernos/92/stats-detalhe")).json()
    assert admin["ultimas_resolucoes"][0]["id_externo"] == 990912


async def test_search_remove_id_externo_para_nao_admin(client, auth_state, monkeypatch):
    import q_router

    async def fake_search(_payload):
        return {
            "hits": [{"id": 913, "id_externo": 990913, "enunciado": "Q"}],
            "estimatedTotalHits": 1,
            "facetDistribution": {},
            "processingTimeMs": 1,
        }

    monkeypatch.setattr(q_router, "_meili_search", fake_search)

    auth_state["user"] = USER_B
    comum = (
        await client.post(
            "/api/q/search?is_admin=true&role=admin",
            json={"q": "", "filtros": {}, "is_admin": True, "role": "admin"},
        )
    ).json()
    assert comum["hits"] == [{"id": 913, "enunciado": "Q"}]

    auth_state["user"] = ADMIN_USER
    admin = (await client.post("/api/q/search", json={"q": "", "filtros": {}})).json()
    assert admin["hits"][0]["id_externo"] == 990913
