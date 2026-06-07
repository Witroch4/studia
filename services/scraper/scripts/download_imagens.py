"""Baixa figuras do CDN do TecConcursos → MinIO + reescreve URLs no banco.

Estratégia:
  1. Extrai URLs únicas de `cdn.tecconcursos.com.br/figuras/*` de:
     - questoes.enunciado_html / .enunciado_md
     - alternativas.texto_html / .texto_md
  2. Dedup por UUID
  3. Para cada nova: baixa via proxy residencial + upload MinIO
  4. Track em state SQLite `imagens_baixadas`
  5. Ao final: SQL UPDATE em batch substituindo URLs em todos os textos

Pause/resume via lock file (/state/PAUSE_IMG).

Uso:
    python scripts/download_imagens.py
    python scripts/download_imagens.py --apenas-novas      # só URLs ainda não baixadas
    python scripts/download_imagens.py --reescrever-only   # só atualiza textos (skip download)
    python scripts/download_imagens.py --dry-run

Env vars (do .env.prod):
    DATABASE_URL, MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET (default: studia), MINIO_PUBLIC_URL (default: https://objstoreapi.witdev.com.br),
    RESIDENTIAL_PROXY_URL (opcional).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from minio import Minio
from minio.error import S3Error
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.observability import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


DATABASE_URL = os.environ["DATABASE_URL"]
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "witalo")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "studia")
MINIO_PUBLIC_URL = os.environ.get("MINIO_PUBLIC_URL", "https://objstoreapi.witdev.com.br")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"
PROXY = os.environ.get("RESIDENTIAL_PROXY_URL")

STATE_DB = Path(os.environ.get("SCRAPE_STATE_PATH", "/state/scrape_state.db"))
PAUSE_FILE = Path("/state/PAUSE_IMG")

URL_PATTERN = re.compile(r"https?://cdn\.tecconcursos\.com\.br/figuras/[a-f0-9-]+", re.I)


def state_conn() -> sqlite3.Connection:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(STATE_DB))
    c.execute("""
        CREATE TABLE IF NOT EXISTS imagens_baixadas (
            uuid TEXT PRIMARY KEY,
            url_origem TEXT,
            url_minio TEXT,
            content_type TEXT,
            bytes INTEGER,
            ts INTEGER
        )
    """)
    return c


def get_minio() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def ensure_bucket(mc: Minio):
    if not mc.bucket_exists(MINIO_BUCKET):
        mc.make_bucket(MINIO_BUCKET)
        log.info("minio.bucket_created", bucket=MINIO_BUCKET)
        # Política pública pra figuras (sem auth na leitura)
        import json
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/figuras/*"],
            }],
        }
        mc.set_bucket_policy(MINIO_BUCKET, json.dumps(policy))
        log.info("minio.policy_set", bucket=MINIO_BUCKET, prefix="figuras/")


async def extrair_urls_unicas(engine) -> set[str]:
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT DISTINCT m FROM (
              SELECT (regexp_matches(enunciado_html, '(https?://cdn\\.tecconcursos\\.com\\.br/figuras/[a-f0-9-]+)', 'g'))[1] AS m
              FROM questoes WHERE enunciado_html LIKE '%cdn.tecconcursos%'
              UNION
              SELECT (regexp_matches(enunciado_md, '(https?://cdn\\.tecconcursos\\.com\\.br/figuras/[a-f0-9-]+)', 'g'))[1] AS m
              FROM questoes WHERE enunciado_md LIKE '%cdn.tecconcursos%'
              UNION
              SELECT (regexp_matches(texto_html, '(https?://cdn\\.tecconcursos\\.com\\.br/figuras/[a-f0-9-]+)', 'g'))[1] AS m
              FROM alternativas WHERE texto_html LIKE '%cdn.tecconcursos%'
              UNION
              SELECT (regexp_matches(texto_md, '(https?://cdn\\.tecconcursos\\.com\\.br/figuras/[a-f0-9-]+)', 'g'))[1] AS m
              FROM alternativas WHERE texto_md LIKE '%cdn.tecconcursos%'
            ) t WHERE m IS NOT NULL
        """))
        return {row[0] for row in result.fetchall()}


def uuid_from_url(url: str) -> str:
    """Extrai o UUID final do path."""
    return urlparse(url).path.rsplit("/", 1)[-1]


def url_minio(uuid: str, content_type: str | None) -> str:
    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }.get((content_type or "").lower().split(";")[0], "")
    return f"{MINIO_PUBLIC_URL}/{MINIO_BUCKET}/figuras/{uuid}{ext}"


def minio_object_key(uuid: str, content_type: str | None) -> str:
    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }.get((content_type or "").lower().split(";")[0], "")
    return f"figuras/{uuid}{ext}"


async def baixar_e_upar(
    client: httpx.AsyncClient, mc: Minio, url: str, sem: asyncio.Semaphore
) -> dict | None:
    """Baixa do CDN TC, upa pro MinIO. Retorna dict info ou None se falhou."""
    uuid = uuid_from_url(url)
    async with sem:
        try:
            r = await client.get(url, timeout=30.0)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "application/octet-stream").split(";")[0]
            data = r.content
            obj_key = minio_object_key(uuid, content_type)
            from io import BytesIO
            mc.put_object(
                MINIO_BUCKET,
                obj_key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return {
                "uuid": uuid,
                "url_origem": url,
                "url_minio": url_minio(uuid, content_type),
                "content_type": content_type,
                "bytes": len(data),
            }
        except Exception as e:  # noqa: BLE001
            log.error("imagem.fail", uuid=uuid, url=url, err=str(e))
            return None


async def reescrever_urls_no_banco(engine, mapping: dict[str, str]):
    """SQL UPDATE em batch substituindo URLs em todos os campos relevantes."""
    if not mapping:
        log.info("reescrever.skip", motivo="mapping_vazio")
        return

    log.info("reescrever.iniciando", urls=len(mapping))

    async with engine.begin() as conn:
        for old_url, new_url in mapping.items():
            # Usa REPLACE em texto — funciona pra HTTP, HTTPS, qualquer aspas
            await conn.execute(
                text("UPDATE questoes SET enunciado_html = REPLACE(enunciado_html, :o, :n) WHERE enunciado_html LIKE '%' || :o || '%'"),
                {"o": old_url, "n": new_url},
            )
            await conn.execute(
                text("UPDATE questoes SET enunciado_md = REPLACE(enunciado_md, :o, :n) WHERE enunciado_md LIKE '%' || :o || '%'"),
                {"o": old_url, "n": new_url},
            )
            await conn.execute(
                text("UPDATE alternativas SET texto_html = REPLACE(texto_html, :o, :n) WHERE texto_html LIKE '%' || :o || '%'"),
                {"o": old_url, "n": new_url},
            )
            await conn.execute(
                text("UPDATE alternativas SET texto_md = REPLACE(texto_md, :o, :n) WHERE texto_md LIKE '%' || :o || '%'"),
                {"o": old_url, "n": new_url},
            )

    log.info("reescrever.ok", urls=len(mapping))


async def main(apenas_novas: bool, reescrever_only: bool, dry_run: bool):
    engine = create_async_engine(DATABASE_URL)
    mc = get_minio()
    ensure_bucket(mc)

    log.info("inicio", apenas_novas=apenas_novas, reescrever_only=reescrever_only, dry_run=dry_run)

    urls_todas = await extrair_urls_unicas(engine)
    log.info("urls.encontradas", total=len(urls_todas))

    sc = state_conn()
    ja_baixadas = {
        row[0]: row[1]
        for row in sc.execute("SELECT uuid, url_minio FROM imagens_baixadas").fetchall()
    }
    log.info("urls.ja_baixadas", total=len(ja_baixadas))

    # mapping: url_origem -> url_minio (pra reescrever)
    mapping: dict[str, str] = {}
    for url in urls_todas:
        uuid = uuid_from_url(url)
        if uuid in ja_baixadas:
            mapping[url] = ja_baixadas[uuid]

    # Download das pendentes
    pendentes = [u for u in urls_todas if uuid_from_url(u) not in ja_baixadas]
    log.info("urls.pendentes", total=len(pendentes))

    if reescrever_only:
        log.info("modo.reescrever_only — pulando downloads")
    elif dry_run:
        log.info("modo.dry_run — não baixa nada")
        log.info("amostra_pendentes", urls=list(pendentes)[:10])
    elif pendentes:
        sem = asyncio.Semaphore(5)  # 5 downloads simultâneos
        client_kwargs = {"http2": True, "follow_redirects": True}
        if PROXY:
            client_kwargs["proxy"] = PROXY
            log.info("proxy.enabled", proxy_host=urlparse(PROXY).hostname)

        async with httpx.AsyncClient(**client_kwargs) as client:
            for i, url in enumerate(pendentes, 1):
                # Pausa cooperativa
                while PAUSE_FILE.exists():
                    log.info("paused", lock=str(PAUSE_FILE))
                    await asyncio.sleep(15)

                result = await baixar_e_upar(client, mc, url, sem)
                if result:
                    sc.execute(
                        "INSERT OR REPLACE INTO imagens_baixadas (uuid, url_origem, url_minio, content_type, bytes, ts) "
                        "VALUES (?,?,?,?,?,strftime('%s','now'))",
                        (result["uuid"], result["url_origem"], result["url_minio"], result["content_type"], result["bytes"]),
                    )
                    sc.commit()
                    mapping[url] = result["url_minio"]

                if i % 50 == 0:
                    log.info("progresso", baixadas=i, total_pendentes=len(pendentes))
                    await asyncio.sleep(1.5)  # respiro a cada 50

    # Reescrever URLs nos textos
    if not dry_run:
        await reescrever_urls_no_banco(engine, mapping)

    log.info("fim", baixadas_sessao=len(pendentes) if not dry_run and not reescrever_only else 0,
             urls_total=len(urls_todas), urls_mapeadas=len(mapping))

    sc.close()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apenas-novas", action="store_true", help="só URLs ainda sem baixar")
    parser.add_argument("--reescrever-only", action="store_true", help="skip download, só UPDATE textos")
    parser.add_argument("--dry-run", action="store_true", help="não baixa nem atualiza")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.apenas_novas, args.reescrever_only, args.dry_run))
    except KeyboardInterrupt:
        sys.exit(130)
