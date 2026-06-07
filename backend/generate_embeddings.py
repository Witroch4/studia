"""Gera embeddings (Gemini text-embedding-004, 768 dims) das questões.

Lê questões sem embedding, gera em batch via google-genai, escreve na coluna
`questoes.embedding` (pgvector).

Uso:
    python generate_embeddings.py            # todas pendentes
    python generate_embeddings.py --limit 50 # smoke
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re

from google import genai
from sqlalchemy import select, text

from database import async_session
from models import Questao

MODEL = "text-embedding-004"  # 768 dims, gratuito até quota
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BATCH = 100


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:8000]


async def gerar(limit: int | None) -> None:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não definido")
    client = genai.Client(api_key=GEMINI_API_KEY)

    async with async_session() as db:
        stmt = (
            select(Questao.id, Questao.enunciado_md, Questao.enunciado_html)
            .where(Questao.embedding_dim.is_(None))
            .order_by(Questao.id)
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).all()
        print(f"{len(rows)} questões sem embedding")

        ok = 0
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            texts = [strip_html(r[1] or r[2]) for r in chunk]
            ids = [r[0] for r in chunk]

            # google-genai SDK chamada síncrona — roda em executor
            def _embed():
                return client.models.embed_content(
                    model=MODEL,
                    contents=texts,
                )

            resp = await asyncio.to_thread(_embed)
            embeddings = [e.values for e in resp.embeddings]

            # Update em lote via UPDATE...FROM unnest
            await db.execute(
                text("""
                    UPDATE questoes
                    SET embedding = data.emb::vector,
                        embedding_dim = :dim,
                        embedding_model = :model
                    FROM (SELECT unnest(:ids::int[]) AS id, unnest(:embs::text[]) AS emb) AS data
                    WHERE questoes.id = data.id
                """),
                {
                    "ids": ids,
                    "embs": [str(e) for e in embeddings],
                    "dim": len(embeddings[0]),
                    "model": MODEL,
                },
            )
            await db.commit()
            ok += len(chunk)
            print(f"  batch {i}-{i+len(chunk)} embedded (total ok={ok})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(gerar(args.limit))
