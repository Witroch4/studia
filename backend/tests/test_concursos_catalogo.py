"""Catálogo de concorrências: visibilidade pública/privada e permissões.

Regras:
- Import exige login; `publico=true` só tem efeito para admin (user comum
  importa sempre privado).
- Listagem = catálogo público + privados do próprio usuário.
- Detalhe/simulação: público, dono ou admin; senão 403.
- Delete: só dono ou admin.
"""
import io

import pytest

from tests.conftest import ADMIN_USER, USER_A, USER_B

CSV_MINIMO = (
    "CARGO,POLO,MACROPOLO,INSCRIÇÃO,PONTOS,AC,PCD,PN,PI,PQ\n"
    "ENGENHEIRO,SP,SUDESTE,100,66,1,,,,\n"
    "ENGENHEIRO,RJ,SUDESTE,101,60,2,,1,,\n"
    "ENGENHEIRO,GO,CENTRO-OESTE,102,55,3,1,,,\n"
)


async def _importar(client, nome: str, publico: bool = False) -> dict:
    resp = await client.post(
        "/api/concursos/import",
        files={"file": (f"{nome}.csv", io.BytesIO(CSV_MINIMO.encode()), "text/csv")},
        data={"nome": nome, "publico": "true" if publico else "false"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_import_exige_login(client, auth_state):
    auth_state["user"] = None
    resp = await client.post(
        "/api/concursos/import",
        files={"file": ("x.csv", io.BytesIO(CSV_MINIMO.encode()), "text/csv")},
        data={"nome": "x"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_publica_no_catalogo(client, auth_state):
    auth_state["user"] = ADMIN_USER
    criado = await _importar(client, "CNU Catalogo", publico=True)
    assert criado["publico"] is True


@pytest.mark.asyncio
async def test_user_comum_nao_publica_mesmo_pedindo(client, auth_state):
    auth_state["user"] = USER_A
    criado = await _importar(client, "Tentativa Publica", publico=True)
    assert criado["publico"] is False


@pytest.mark.asyncio
async def test_lista_catalogo_mais_meus(client, auth_state):
    auth_state["user"] = ADMIN_USER
    pub = await _importar(client, "Publico Admin", publico=True)

    auth_state["user"] = USER_A
    meu = await _importar(client, "Privado A")

    auth_state["user"] = USER_B
    alheio = await _importar(client, "Privado B")

    auth_state["user"] = USER_A
    resp = await client.get("/api/concursos")
    assert resp.status_code == 200
    ids = {c["id"]: c for c in resp.json()}

    assert pub["id"] in ids and ids[pub["id"]]["publico"] is True
    assert meu["id"] in ids and ids[meu["id"]]["meu"] is True
    assert alheio["id"] not in ids
    # user comum não exclui o item do catálogo
    assert ids[pub["id"]]["pode_excluir"] is False
    assert ids[meu["id"]]["pode_excluir"] is True


@pytest.mark.asyncio
async def test_detalhe_e_simular_privado_alheio_403(client, auth_state):
    auth_state["user"] = USER_B
    alheio = await _importar(client, "Privado B")

    auth_state["user"] = USER_A
    resp = await client.get(f"/api/concursos/{alheio['id']}")
    assert resp.status_code == 403

    resp = await client.post(
        f"/api/concursos/{alheio['id']}/simular", json={"total_vagas": 2}
    )
    assert resp.status_code == 403

    # admin enxerga tudo
    auth_state["user"] = ADMIN_USER
    resp = await client.get(f"/api/concursos/{alheio['id']}")
    assert resp.status_code == 200
    assert resp.json()["publico"] is False


@pytest.mark.asyncio
async def test_publico_simula_para_qualquer_user(client, auth_state):
    auth_state["user"] = ADMIN_USER
    pub = await _importar(client, "Publico Admin", publico=True)

    auth_state["user"] = USER_A
    resp = await client.post(
        f"/api/concursos/{pub['id']}/simular", json={"total_vagas": 2}
    )
    assert resp.status_code == 200
    assert resp.json()["total_candidatos"] == 3


@pytest.mark.asyncio
async def test_delete_so_dono_ou_admin(client, auth_state):
    auth_state["user"] = ADMIN_USER
    pub = await _importar(client, "Publico Admin", publico=True)

    auth_state["user"] = USER_A
    meu = await _importar(client, "Privado A")

    # user comum não deleta o público de outro dono
    resp = await client.delete(f"/api/concursos/{pub['id']}")
    assert resp.status_code == 403

    # mas deleta o próprio
    resp = await client.delete(f"/api/concursos/{meu['id']}")
    assert resp.status_code == 200

    # admin deleta qualquer um
    auth_state["user"] = ADMIN_USER
    resp = await client.delete(f"/api/concursos/{pub['id']}")
    assert resp.status_code == 200
