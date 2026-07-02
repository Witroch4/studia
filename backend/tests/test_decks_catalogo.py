"""Decks multi-usuário + catálogo público (escopo, promoção, cópia)."""

import pytest

from tests.conftest import ADMIN_USER, USER_A, USER_B


def _upload(md: str):
    return {"file": ("cards.md", md.encode("utf-8"), "text/markdown")}


MD_A = """
flashcard:Engenharia Civil:Fundacoes

frente:
Pergunta A?

verso:
Resposta A.
"""

MD_B = """
flashcard:Engenharia Civil:Estruturas

frente:
Pergunta B?

verso:
Resposta B.
"""


async def _importa(client, auth_state, user, md):
    auth_state["user"] = user
    r = await client.post("/api/flashcards/import", files=_upload(md))
    assert r.status_code == 200, r.text
    return r.json()


# ─── Escopo de leitura ───────────────────────────────────


@pytest.mark.asyncio
async def test_user_nao_ve_deck_privado_de_outro(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)

    auth_state["user"] = USER_B
    body = (await client.get("/api/decks")).json()
    assert body["meus"] == []
    assert body["catalogo"] == []
    assert "usuarios" not in body


@pytest.mark.asyncio
async def test_dono_ve_seu_deck_em_meus(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)

    body = (await client.get("/api/decks")).json()
    assert len(body["meus"]) == 1
    deck = body["meus"][0]
    assert deck["nome"] == "Engenharia Civil"
    assert deck["meu"] is True
    assert deck["publico"] is False
    assert isinstance(deck["id"], int)


@pytest.mark.asyncio
async def test_catalogo_visivel_a_todos(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]

    auth_state["user"] = ADMIN_USER
    r = await client.post(f"/api/decks/{deck_id}/promover")
    assert r.status_code == 200

    auth_state["user"] = USER_B
    body = (await client.get("/api/decks")).json()
    assert [d["id"] for d in body["catalogo"]] == [deck_id]
    assert body["catalogo"][0]["pode_excluir"] is False

    # dono continua vendo em "meus" (com flag publico), não duplicado no catálogo
    auth_state["user"] = USER_A
    body = (await client.get("/api/decks")).json()
    assert [d["id"] for d in body["meus"]] == [deck_id]
    assert body["meus"][0]["publico"] is True
    assert body["catalogo"] == []


@pytest.mark.asyncio
async def test_admin_ve_secao_usuarios(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)

    auth_state["user"] = ADMIN_USER
    body = (await client.get("/api/decks")).json()
    assert "usuarios" in body
    donos = [g["dono"]["id"] for g in body["usuarios"]]
    assert USER_A.id in donos


@pytest.mark.asyncio
async def test_cards_de_deck_privado_de_outro_403(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]

    auth_state["user"] = USER_B
    r = await client.get(f"/api/flashcards/deck/{deck_id}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_cards_de_deck_publico_somente_leitura(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]
    auth_state["user"] = ADMIN_USER
    await client.post(f"/api/decks/{deck_id}/promover")

    auth_state["user"] = USER_B
    body = (await client.get(f"/api/flashcards/deck/{deck_id}")).json()
    assert body["total"] == 1
    assert body["somente_leitura"] is True

    auth_state["user"] = USER_A
    body = (await client.get(f"/api/flashcards/deck/{deck_id}")).json()
    assert body["somente_leitura"] is False


@pytest.mark.asyncio
async def test_todos_so_do_usuario(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    await _importa(client, auth_state, USER_B, MD_B)

    auth_state["user"] = USER_B
    body = (await client.get("/api/flashcards/todos")).json()
    assert body["total"] == 1
    assert body["cards"][0]["frente"].startswith("Pergunta B")


@pytest.mark.asyncio
async def test_delete_deck_de_outro_403_admin_pode(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]

    auth_state["user"] = USER_B
    assert (await client.delete(f"/api/decks/{deck_id}")).status_code == 403

    auth_state["user"] = ADMIN_USER
    assert (await client.delete(f"/api/decks/{deck_id}")).status_code == 200


@pytest.mark.asyncio
async def test_sem_login_401(client, auth_state):
    auth_state["user"] = None
    assert (await client.get("/api/decks")).status_code == 401
    assert (await client.post("/api/flashcards/import", files=_upload(MD_A))).status_code == 401


# ─── Escrita escopada ────────────────────────────────────


@pytest.mark.asyncio
async def test_import_mesmo_tema_gera_decks_separados_por_dono(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    await _importa(client, auth_state, USER_B, MD_A)  # mesmo tema/slug

    auth_state["user"] = USER_A
    a = (await client.get("/api/decks")).json()["meus"]
    auth_state["user"] = USER_B
    b = (await client.get("/api/decks")).json()["meus"]
    assert len(a) == 1 and len(b) == 1
    assert a[0]["id"] != b[0]["id"]
    assert a[0]["slug"] == b[0]["slug"] == "engenharia-civil"


@pytest.mark.asyncio
async def test_import_dedup_por_dono(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    r2 = await _importa(client, auth_state, USER_A, MD_A)
    assert r2["imported"] == 0 and r2["skipped"] == 1


@pytest.mark.asyncio
async def test_import_impedir_promocao_marca_deck_novo(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.post(
        "/api/flashcards/import",
        files=_upload(MD_A),
        data={"impedir_promocao": "true"},
    )
    assert r.status_code == 200
    deck = (await client.get("/api/decks")).json()["meus"][0]
    assert deck["permitir_promocao"] is False


@pytest.mark.asyncio
async def test_create_individual_escopado_com_impedir(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.post("/api/flashcards", json={
        "tema": "Hidráulica",
        "assunto": "Bombas",
        "frente": "P?",
        "verso": "R.",
        "impedir_promocao": True,
    })
    assert r.status_code == 200
    assert isinstance(r.json()["deck_id"], int)
    deck = (await client.get("/api/decks")).json()["meus"][0]
    assert deck["permitir_promocao"] is False

    # card em deck existente NÃO reseta a escolha
    r2 = await client.post("/api/flashcards", json={
        "tema": "Hidráulica", "assunto": "Bombas", "frente": "P2?", "verso": "R2.",
    })
    assert r2.status_code == 200
    deck = (await client.get("/api/decks")).json()["meus"][0]
    assert deck["permitir_promocao"] is False and deck["total"] == 2


# ─── Promoção / despromoção / PATCH ──────────────────────


@pytest.mark.asyncio
async def test_promover_user_comum_403(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]
    assert (await client.post(f"/api/decks/{deck_id}/promover")).status_code == 403


@pytest.mark.asyncio
async def test_promover_impedido_409(client, auth_state):
    auth_state["user"] = USER_A
    await client.post(
        "/api/flashcards/import", files=_upload(MD_A), data={"impedir_promocao": "true"}
    )
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]

    auth_state["user"] = ADMIN_USER
    assert (await client.post(f"/api/decks/{deck_id}/promover")).status_code == 409


@pytest.mark.asyncio
async def test_despromover_remove_do_catalogo(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]
    auth_state["user"] = ADMIN_USER
    await client.post(f"/api/decks/{deck_id}/promover")
    assert (await client.post(f"/api/decks/{deck_id}/despromover")).status_code == 200

    auth_state["user"] = USER_B
    assert (await client.get("/api/decks")).json()["catalogo"] == []


@pytest.mark.asyncio
async def test_patch_impedir_so_dono_e_despromove(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]
    auth_state["user"] = ADMIN_USER
    await client.post(f"/api/decks/{deck_id}/promover")

    # admin não muda a vontade do dono
    r = await client.patch(f"/api/decks/{deck_id}", json={"impedir_promocao": True})
    assert r.status_code == 403

    auth_state["user"] = USER_A
    r = await client.patch(f"/api/decks/{deck_id}", json={"impedir_promocao": True})
    assert r.status_code == 200
    deck = (await client.get("/api/decks")).json()["meus"][0]
    assert deck["permitir_promocao"] is False
    assert deck["publico"] is False  # impedir num deck público despromove


# ─── Copiar pro acervo ───────────────────────────────────


@pytest.mark.asyncio
async def test_copiar_deck_publico(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]
    auth_state["user"] = ADMIN_USER
    await client.post(f"/api/decks/{deck_id}/promover")

    auth_state["user"] = USER_B
    r = await client.post(f"/api/decks/{deck_id}/copiar")
    assert r.status_code == 200
    clone = r.json()
    assert clone["total"] == 1 and clone["id"] != deck_id

    body = (await client.get("/api/decks")).json()
    assert [d["id"] for d in body["meus"]] == [clone["id"]]
    assert body["meus"][0]["publico"] is False


@pytest.mark.asyncio
async def test_copiar_deck_privado_de_outro_403(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]

    auth_state["user"] = USER_B
    assert (await client.post(f"/api/decks/{deck_id}/copiar")).status_code == 403


@pytest.mark.asyncio
async def test_copiar_duas_vezes_sufixa_slug(client, auth_state):
    await _importa(client, auth_state, USER_A, MD_A)
    deck_id = (await client.get("/api/decks")).json()["meus"][0]["id"]
    auth_state["user"] = ADMIN_USER
    await client.post(f"/api/decks/{deck_id}/promover")

    auth_state["user"] = USER_B
    s1 = (await client.post(f"/api/decks/{deck_id}/copiar")).json()["slug"]
    s2 = (await client.post(f"/api/decks/{deck_id}/copiar")).json()["slug"]
    assert s1 == "engenharia-civil"
    assert s2 == "engenharia-civil-2"
