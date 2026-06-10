"""Sincroniza questões do Postgres para Meilisearch (full reindex).

Schema e documento vivem em `meili_index.py` (fonte única, compartilhada com o
scraper). Aqui só orquestra: aplica settings do índice e indexa em batch.

Uso:
    python sync_meili.py              # full reindex
    python sync_meili.py --limit 100  # smoke
"""

from __future__ import annotations

import argparse
import asyncio
import os

import httpx
from meilisearch_python_sdk import AsyncClient

from database import async_session
from meili_index import (
    FILTERABLE,
    INDEX_NAME,
    MAX_TOTAL_HITS,
    MAX_VALUES_PER_FACET,
    PRIMARY_KEY,
    SEARCHABLE,
    SORTABLE,
    STOP_WORDS,
    build_docs,
)

MEILI_URL = os.getenv("MEILI_URL", "http://localhost:7700")
MEILI_KEY = os.getenv("MEILI_KEY", "dev_master_key_studia_2026")
BATCH = 500


async def _apply_settings(index) -> None:
    await index.update_filterable_attributes(FILTERABLE)
    await index.update_sortable_attributes(SORTABLE)
    await index.update_searchable_attributes(SEARCHABLE)
    await index.update_stop_words(STOP_WORDS)
    # maxTotalHits e maxValuesPerFacet via REST: os métodos do SDK variam entre
    # versões e os defaults (1000 / 100) truncavam contagem global e facetas.
    async with httpx.AsyncClient() as hc:
        headers = {"Authorization": f"Bearer {MEILI_KEY}"}
        resp = await hc.patch(
            f"{MEILI_URL}/indexes/{INDEX_NAME}/settings/pagination",
            headers=headers,
            json={"maxTotalHits": MAX_TOTAL_HITS},
        )
        resp.raise_for_status()
        resp = await hc.patch(
            f"{MEILI_URL}/indexes/{INDEX_NAME}/settings/faceting",
            headers=headers,
            json={"maxValuesPerFacet": MAX_VALUES_PER_FACET},
        )
        resp.raise_for_status()


async def main(limit: int | None) -> None:
    print(f"Conectando Meili em {MEILI_URL}")
    async with AsyncClient(MEILI_URL, MEILI_KEY) as client:
        try:
            await client.create_index(INDEX_NAME, primary_key=PRIMARY_KEY)
        except Exception:
            pass  # já existe
        index = client.index(INDEX_NAME)

        await _apply_settings(index)

        print("Carregando questões do Postgres...")
        async with async_session() as db:
            docs = await build_docs(db, limit=limit)
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
