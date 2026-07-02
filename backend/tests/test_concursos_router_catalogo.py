"""GET /api/q/concursos/catalogo: catálogo de concursos TC para usuário logado.

Diferente de `listar_concursos` (admin-only), esse endpoint é aberto a
qualquer usuário autenticado e só mostra concursos com ao menos um arquivo
de tipo EDITAL — sem edital não há o que extrair para o Mapa da Aprovação.

Nome do arquivo NÃO é `test_concursos_catalogo.py` de propósito: esse nome
já existe para a feature (não relacionada) de catálogo de concorrências
(`backend/tests/test_concursos_catalogo.py`, endpoints `/api/concursos/*`).
"""
from __future__ import annotations

import pytest

from models import TcConcurso, TcConcursoArquivo
from tests.conftest import make_user

pytestmark = pytest.mark.asyncio


async def _seed(db):
    com = TcConcurso(concurso_id_externo=1, nome_completo="Prefeitura A — IDECAN",
                      url_concurso="a", banca_nome="IDECAN", ano=2026)
    sem = TcConcurso(concurso_id_externo=2, nome_completo="Prefeitura B",
                      url_concurso="b", ano=2025)
    db.add_all([com, sem])
    await db.flush()
    db.add(TcConcursoArquivo(concurso_id=com.id, tipo="EDITAL", arquivo_id_externo=1,
                              uuid="u", nome_arquivo="e.pdf", minio_object_key="k"))
    db.add(TcConcursoArquivo(concurso_id=sem.id, tipo="PROVA_OBJETIVA", arquivo_id_externo=2,
                              uuid="u2", nome_arquivo="p.pdf", minio_object_key="k2"))
    await db.commit()
    return com, sem


async def test_catalogo_so_com_edital(client, db_session, auth_state):
    await _seed(db_session)
    auth_state["user"] = make_user("u1")  # usuário comum, não admin
    r = await client.get("/api/q/concursos/catalogo")
    assert r.status_code == 200
    nomes = [c["nome_completo"] for c in r.json()["items"]]
    assert nomes == ["Prefeitura A — IDECAN"]


async def test_catalogo_exige_login(client, auth_state):
    auth_state["user"] = None
    r = await client.get("/api/q/concursos/catalogo")
    assert r.status_code == 401


async def test_catalogo_busca(client, db_session, auth_state):
    await _seed(db_session)
    auth_state["user"] = make_user("u1")
    r = await client.get("/api/q/concursos/catalogo?busca=IDECAN")
    assert r.json()["total"] == 1


async def test_catalogo_paginacao(client, db_session, auth_state):
    await _seed(db_session)
    auth_state["user"] = make_user("u1")
    r = await client.get("/api/q/concursos/catalogo?page=1&page_size=1")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
