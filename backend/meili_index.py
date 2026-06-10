"""Fonte única do schema/documento do índice Meili `questoes`.

Compartilhado entre:
- `sync_meili.py` (full reindex via SDK Meili)
- `services/scraper` (indexação incremental por página, via httpx)

Por isso este módulo NÃO depende do SDK Meili nem de `database.py` — só dos
models e de SQLAlchemy. Cada caller injeta a própria `AsyncSession` e empurra
os documentos com o cliente que tiver à mão.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import Banca, Cargo, Materia, Orgao, Questao

INDEX_NAME = "questoes"
PRIMARY_KEY = "id"

FILTERABLE = [
    "banca", "orgao", "cargo", "ano", "materia", "assuntos", "tipo", "status",
    "area", "formacao", "escolaridade", "regiao",
    # "id" filterável p/ recortes `id IN [...]` (ex.: filtro de favoritas)
    "id",
]
SORTABLE = ["ano", "id"]
SEARCHABLE = ["enunciado", "assuntos", "materia"]
STOP_WORDS = ["o", "a", "os", "as", "de", "da", "do"]
# 289 bancas hoje; default do Meili (100) truncava o facet e sumia bancas como
# IDECAN. Mantém folga grande pra órgãos/assuntos também.
MAX_VALUES_PER_FACET = 2000
# default do Meili (1000) truncava a contagem global de questões.
MAX_TOTAL_HITS = 1_000_000


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _formacao(raw: dict | None) -> str | None:
    """`concursoEspecialidade` do payload TC ≈ formação/especialidade do cargo.

    O TC manda às vezes com aspas embutidas ('"Sem Especialidade"') e o valor
    "Sem Especialidade" não é informação — ambos viram None.
    """
    if not raw:
        return None
    v = str(raw.get("concursoEspecialidade") or "").strip().strip('"').strip()
    if not v or v.casefold() == "sem especialidade":
        return None
    return v


async def build_docs(
    db: Any,
    *,
    ids: Iterable[int] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Monta os documentos Meili para um conjunto de questões.

    `ids=None` → todas (full reindex). `ids=[...]` → só essas (incremental).
    Carrega apenas a taxonomia referenciada pelas questões do lote.
    """
    stmt = (
        select(Questao)
        .options(
            selectinload(Questao.alternativas),
            selectinload(Questao.assuntos),
        )
        .order_by(Questao.id)
    )
    id_list = list(ids) if ids is not None else None
    if id_list is not None:
        if not id_list:
            return []
        stmt = stmt.where(Questao.id.in_(id_list))
    if limit:
        stmt = stmt.limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    banca_ids = {q.banca_id for q in rows if q.banca_id}
    orgao_ids = {q.orgao_id for q in rows if q.orgao_id}
    cargo_ids = {q.cargo_id for q in rows if q.cargo_id}
    materia_ids = {q.materia_id for q in rows if q.materia_id}

    bancas = await _load_by_id(db, Banca, banca_ids)
    orgaos = await _load_by_id(db, Orgao, orgao_ids)
    cargos = await _load_by_id(db, Cargo, cargo_ids)
    materias = await _load_by_id(db, Materia, materia_ids)

    docs: list[dict[str, Any]] = []
    for q in rows:
        banca = bancas.get(q.banca_id)
        orgao = orgaos.get(q.orgao_id)
        cargo = cargos.get(q.cargo_id)
        materia = materias.get(q.materia_id)
        docs.append(
            {
                "id": q.id,
                "id_externo": q.id_externo,
                "enunciado": strip_html(q.enunciado_md or q.enunciado_html)[:8000],
                "gabarito": q.gabarito,
                "tipo": q.tipo,
                "status": q.status,
                "banca": (banca.sigla or banca.nome) if banca else None,
                "orgao": (orgao.sigla or orgao.nome) if orgao else None,
                "cargo": cargo.nome if cargo else None,
                "ano": cargo.ano if cargo else None,
                "materia": materia.nome if materia else None,
                "assuntos": [a.nome for a in q.assuntos],
                "area": (cargo.area if cargo else None) or (q.raw_json or {}).get("concursoArea"),
                "formacao": _formacao(q.raw_json),
                "escolaridade": cargo.escolaridade if cargo else None,
                "regiao": orgao.regiao if orgao else None,
                "tem_alternativas": len(q.alternativas),
            }
        )
    return docs


async def _load_by_id(db: Any, model: Any, ids: set[int]) -> dict[int, Any]:
    if not ids:
        return {}
    rows = (await db.execute(select(model).where(model.id.in_(ids)))).scalars().all()
    return {row.id: row for row in rows}


async def push_docs_http(
    docs: list[dict[str, Any]],
    *,
    meili_url: str,
    meili_key: str,
    timeout: float = 30.0,
) -> int:
    """Upsert best-effort dos documentos via REST (PUT = add-or-replace por id).

    Retorna quantos docs foram enviados. SDK-free de propósito (o scraper não
    embarca o meilisearch-sdk). Levanta em erro HTTP — o caller decide se engole.
    """
    if not docs:
        return 0
    import httpx

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.put(
            f"{meili_url}/indexes/{INDEX_NAME}/documents",
            params={"primaryKey": PRIMARY_KEY},
            headers={"Authorization": f"Bearer {meili_key}"},
            json=docs,
        )
        r.raise_for_status()
    return len(docs)
