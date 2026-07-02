"""Testes do endpoint POST /api/flashcards/import (dedup em reimporte)."""

import pytest

MD = """
flashcard:Engenharia Civil:Fundacoes - Conceitos

frente:
O que e tensao admissivel?

verso:
Satisfaz ELU + ELS ao mesmo tempo.

flashcard:Engenharia Civil:Fundacoes - NBR 6122

frente:
Quais fatores a NBR 6122 exige observar?

verso:
Solo, agua, geometria e solicitacoes.
"""


def _upload(md: str):
    return {"file": ("cards.md", md.encode("utf-8"), "text/markdown")}


@pytest.mark.asyncio
async def test_import_reimporte_nao_duplica(client):
    r1 = await client.post("/api/flashcards/import", files=_upload(MD))
    assert r1.status_code == 200
    assert r1.json()["imported"] == 2

    # Mesmo arquivo de novo: nada duplica, tudo e pulado.
    r2 = await client.post("/api/flashcards/import", files=_upload(MD))
    assert r2.status_code == 200
    body = r2.json()
    assert body["imported"] == 0
    assert body["skipped"] == 2

    decks = (await client.get("/api/decks")).json()
    deck = next(d for d in decks if d["id"] == "engenharia-civil")
    assert deck["total"] == 2


@pytest.mark.asyncio
async def test_import_card_novo_entra_e_duplicado_e_pulado(client):
    r1 = await client.post("/api/flashcards/import", files=_upload(MD))
    assert r1.json()["imported"] == 2

    md_com_novo = MD + """
flashcard:Engenharia Civil:Fundacoes - Sapatas

frente:
Area comprimida minima no ELU?

verso:
50% da area total da base.
"""
    r2 = await client.post("/api/flashcards/import", files=_upload(md_com_novo))
    body = r2.json()
    assert body["imported"] == 1
    assert body["skipped"] == 2
    assert body["cards"][0]["assunto"] == "Fundacoes - Sapatas"
