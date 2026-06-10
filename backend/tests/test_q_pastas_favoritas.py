from __future__ import annotations

import pytest

from models import CadernoQuestoes, Questao
from q_router import _to_meili_filter


# ─── _to_meili_filter ────────────────────────────────────


def test_filtro_generico_or_dentro_and_entre():
    f = _to_meili_filter({"banca": ["FGV", "CESPE"], "ano": [2024]})
    assert f == '(banca = "FGV" OR banca = "CESPE") AND (ano = 2024)'


def test_filtro_status_excluir_vira_negacao():
    f = _to_meili_filter({"status_excluir": ["ANULADA", "DESATUALIZADA"]})
    assert f == '(status != "ANULADA" AND status != "DESATUALIZADA")'


def test_filtro_vazio_retorna_none():
    assert _to_meili_filter({}) is None
    assert _to_meili_filter({"banca": []}) is None


# ─── /api/q/pastas + /api/q/cadernos?pasta= ──────────────


@pytest.mark.asyncio
async def test_pastas_agrupa_e_normaliza_sem_classificacao(client, db_session):
    db_session.add_all(
        [
            CadernoQuestoes(nome="C1", pasta="OAB 2026", question_ids=[1, 2], total=2),
            CadernoQuestoes(nome="C2", pasta="OAB 2026", question_ids=[3], total=1),
            CadernoQuestoes(nome="C3", pasta=None, question_ids=[4], total=1),
            CadernoQuestoes(nome="C4", pasta="", question_ids=[5], total=1),
        ]
    )
    await db_session.commit()

    r = await client.get("/api/q/pastas")
    assert r.status_code == 200
    pastas = {p["pasta"]: p for p in r.json()}
    assert pastas["OAB 2026"] == {"pasta": "OAB 2026", "cadernos": 2, "total_questoes": 3}
    # NULL e "" agregadas na mesma "Sem classificação" (pasta None)
    assert pastas[None] == {"pasta": None, "cadernos": 2, "total_questoes": 2}


@pytest.mark.asyncio
async def test_listar_cadernos_filtra_por_pasta(client, db_session):
    db_session.add_all(
        [
            CadernoQuestoes(nome="C1", pasta="OAB", question_ids=[1], total=1),
            CadernoQuestoes(nome="C2", pasta=None, question_ids=[2], total=1),
        ]
    )
    await db_session.commit()

    r = await client.get("/api/q/cadernos", params={"pasta": "OAB"})
    assert [c["nome"] for c in r.json()] == ["C1"]

    r = await client.get("/api/q/cadernos", params={"pasta": ""})
    assert [c["nome"] for c in r.json()] == ["C2"]

    r = await client.get("/api/q/cadernos")
    assert {c["nome"] for c in r.json()} == {"C1", "C2"}


# ─── favoritas ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_favoritar_toggle_e_listagem(client, db_session):
    db_session.add(Questao(id=10, enunciado_md="Q10"))
    await db_session.commit()

    r = await client.get("/api/q/favoritas")
    assert r.json() == {"ids": [], "total": 0}

    r = await client.post("/api/q/10/favoritar")
    assert r.status_code == 200
    assert r.json() == {"questao_id": 10, "favorita": True}

    r = await client.get("/api/q/favoritas")
    assert r.json() == {"ids": [10], "total": 1}

    r = await client.post("/api/q/10/favoritar")
    assert r.json() == {"questao_id": 10, "favorita": False}

    r = await client.get("/api/q/favoritas")
    assert r.json() == {"ids": [], "total": 0}


@pytest.mark.asyncio
async def test_favoritar_questao_inexistente_404(client):
    r = await client.post("/api/q/999/favoritar")
    assert r.status_code == 404
