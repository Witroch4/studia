"""Sincroniza questões do Postgres para Meilisearch.

Indexa em batch. Schema do índice `questoes` segue spec §5.2 — filterable
em banca, órgão, cargo, ano, matéria, assunto, tipo, status.

Uso:
    python sync_meili.py              # full reindex
    python sync_meili.py --limit 100  # smoke
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re

from meilisearch_python_sdk import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import async_session
from models import Alternativa, Assunto, Banca, Cargo, Materia, Orgao, Questao

MEILI_URL = os.getenv("MEILI_URL", "http://localhost:7700")
MEILI_KEY = os.getenv("MEILI_KEY", "dev_master_key_studia_2026")
INDEX_NAME = "questoes"
BATCH = 500


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


async def docs_from_db(limit: int | None) -> list[dict]:
    async with async_session() as db:
        stmt = (
            select(Questao)
            .options(
                selectinload(Questao.alternativas),
                selectinload(Questao.assuntos),
            )
            .order_by(Questao.id)
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()

        # Pré-carrega bancas/orgaos/cargos/materias (poucos relativos a questões)
        bancas = {b.id: b for b in (await db.execute(select(Banca))).scalars().all()}
        orgaos = {o.id: o for o in (await db.execute(select(Orgao))).scalars().all()}
        cargos = {c.id: c for c in (await db.execute(select(Cargo))).scalars().all()}
        materias = {m.id: m for m in (await db.execute(select(Materia))).scalars().all()}

        docs: list[dict] = []
        for q in rows:
            banca = bancas.get(q.banca_id) if q.banca_id else None
            orgao = orgaos.get(q.orgao_id) if q.orgao_id else None
            cargo = cargos.get(q.cargo_id) if q.cargo_id else None
            materia = materias.get(q.materia_id) if q.materia_id else None

            docs.append({
                "id": q.id,
                "id_externo": q.id_externo,
                "enunciado": strip_html(q.enunciado_md or q.enunciado_html)[:8000],
                "gabarito": q.gabarito,
                "tipo": q.tipo,
                "status": q.status,
                "banca": banca.sigla or banca.nome if banca else None,
                "orgao": orgao.sigla or orgao.nome if orgao else None,
                "cargo": cargo.nome if cargo else None,
                "ano": cargo.ano if cargo else None,
                "materia": materia.nome if materia else None,
                "assuntos": [a.nome for a in q.assuntos],
                "tem_alternativas": len(q.alternativas),
            })
        return docs


async def main(limit: int | None) -> None:
    print(f"Conectando Meili em {MEILI_URL}")
    async with AsyncClient(MEILI_URL, MEILI_KEY) as client:
        # Cria/atualiza índice
        try:
            await client.create_index(INDEX_NAME, primary_key="id")
        except Exception:
            pass  # já existe
        index = client.index(INDEX_NAME)

        await index.update_filterable_attributes([
            "banca", "orgao", "cargo", "ano", "materia",
            "assuntos", "tipo", "status",
        ])
        await index.update_sortable_attributes(["ano", "id"])
        await index.update_searchable_attributes(["enunciado", "assuntos", "materia"])
        await index.update_stop_words(["o", "a", "os", "as", "de", "da", "do"])
        # CRÍTICO: bumpar maxTotalHits — default 1000 trunca o count global.
        # Feito via REST direto (o método do client varia entre versões).
        import httpx as _httpx
        async with _httpx.AsyncClient() as _hc:
            _resp = await _hc.patch(
                f"{MEILI_URL}/indexes/{INDEX_NAME}/settings/pagination",
                headers={"Authorization": f"Bearer {MEILI_KEY}"},
                json={"maxTotalHits": 1000000},
            )
            _resp.raise_for_status()

        print("Carregando questões do Postgres...")
        docs = await docs_from_db(limit)
        print(f"  {len(docs)} questões a indexar")

        for i in range(0, len(docs), BATCH):
            chunk = docs[i:i + BATCH]
            task = await index.add_documents(chunk)
            print(f"  batch {i}-{i+len(chunk)} → task {task.task_uid}")

        print("Aguardando processamento Meili...")
        stats = await index.get_stats()
        print(f"  numero_documentos: {stats.number_of_documents}")
        print(f"  is_indexing: {stats.is_indexing}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.limit))
