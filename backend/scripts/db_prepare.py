"""Bootstrap do banco studIA — leva o Postgres de zero a pronto-pra-produção.

Roda como one-shot antes do `docker stack deploy` (ver build.sh). Idempotente
e seguro para reexecução. Faz, em ordem:

    1. Espera o PostgreSQL aceitar conexões (com retries)
    2. Adquire um advisory lock (serializa bootstrap entre réplicas Swarm)
    3. Cria o database 'studia' se ele não existir
    4. Habilita a extensão pgvector + roda as migrações (migrate.py:
       create_all de tabelas novas + ALTER incremental de colunas faltantes)
    5. VERIFICA que toda tabela definida nos models existe no banco — se faltar
       qualquer uma, sai com código 1 (aborta o deploy em build.sh).

O passo 5 é a garantia operacional: o deploy nunca sobe com schema defasado.
Se a imagem do backend não tiver os models novos (ex.: `guias`), o create_all
não cria a tabela, a verificação falha e o `set -e` do build.sh interrompe o
`docker stack deploy` — em vez de subir um backend que dá 500 em produção.

Uso:
    python -m scripts.db_prepare

Lê DATABASE_URL do ambiente (mesmo formato do backend:
postgresql+asyncpg://user:pass@host:5432/studia).
"""

import asyncio
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)
RETRIES = int(os.environ.get("DB_CONNECT_RETRIES", "30"))
RETRY_DELAY_S = float(os.environ.get("DB_CONNECT_SLEEP_MS", "2000")) / 1000
BOOTSTRAP_LOCK_ID = int(os.environ.get("DB_PREPARE_LOCK_ID", "2026061001"))

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def _admin_url(url: str) -> str:
    """URL apontando para o database administrativo 'postgres'."""
    base, _ = url.rsplit("/", 1)
    return f"{base}/postgres"


def _label(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.hostname or 'postgres'}:{parsed.port or 5432}"


def _print(step: str, msg: str, symbol: str = "✓") -> None:
    print(f"  {symbol} [{step}] {msg}", flush=True)


async def run_alembic() -> None:
    """Roda Alembic. Auto-stamp de bancos legados (tabelas existem, sem alembic_version)."""
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            # Checa se a tabela alembic_version existe E tem pelo menos 1 registro.
            # Tabela existente mas vazia (estado inconsistente) é tratada como legado.
            alembic_table = (
                await conn.execute(text("SELECT to_regclass('public.alembic_version')"))
            ).scalar()
            if alembic_table:
                version_count = (
                    await conn.execute(text("SELECT count(*) FROM alembic_version"))
                ).scalar()
            else:
                version_count = 0
            has_version = bool(version_count)
            has_legacy = bool(
                (await conn.execute(text("SELECT to_regclass('public.questoes')"))).scalar()
            )
    finally:
        await engine.dispose()

    env = {**os.environ, "DATABASE_URL": DATABASE_URL}
    if not has_version and has_legacy:
        _print("alembic", "banco legado detectado — stamp head (adoção sem DDL)")
        subprocess.run(["alembic", "stamp", "head"], cwd=BACKEND_DIR, env=env, check=True)
    subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND_DIR, env=env, check=True)
    _print("alembic", "upgrade head aplicado")


async def wait_for_postgres(admin_url: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        for attempt in range(1, RETRIES + 1):
            try:
                async with engine.connect() as conn:
                    version = (await conn.execute(text("SHOW server_version"))).scalar()
                    _print("postgres", f"{_label(admin_url)} conectado — PostgreSQL {version}")
                    return
            except Exception as exc:  # noqa: BLE001
                if attempt < RETRIES:
                    print(
                        f"  ... aguardando PostgreSQL {_label(admin_url)} "
                        f"({attempt}/{RETRIES}): {type(exc).__name__}",
                        flush=True,
                    )
                    await asyncio.sleep(RETRY_DELAY_S)
                else:
                    _print("postgres", f"{_label(admin_url)} indisponível após {RETRIES} tentativas", "✗")
                    sys.exit(1)
    finally:
        await engine.dispose()


async def ensure_database(admin_url: str, db_name: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = (
                await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": db_name},
                )
            ).scalar()
            if exists:
                _print("db", f"database '{db_name}' já existe")
            else:
                try:
                    await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                    _print("db", f"database '{db_name}' criado")
                except Exception as exc:  # noqa: BLE001
                    if "already exists" in str(exc):
                        _print("db", f"database '{db_name}' existe (corrida)")
                    else:
                        raise
    finally:
        await engine.dispose()


@asynccontextmanager
async def bootstrap_lock(admin_url: str):
    """Serializa o bootstrap entre containers/réplicas concorrentes (Swarm)."""
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    conn = await engine.connect()
    try:
        await conn.execute(
            text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": BOOTSTRAP_LOCK_ID}
        )
        _print("lock", f"advisory lock {BOOTSTRAP_LOCK_ID} adquirido")
        yield
    finally:
        try:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": BOOTSTRAP_LOCK_ID},
            )
        finally:
            await conn.close()
            await engine.dispose()


async def verify_schema() -> None:
    """Garante que TODA tabela definida nos models existe no banco.

    Esta é a trava operacional: se a imagem do backend não tiver um model novo
    (ex.: `guias`), o create_all não cria a tabela e esta verificação sai com
    código 1 — o `set -e` do build.sh aborta o `docker stack deploy` e produção
    nunca sobe com schema defasado.
    """
    from models import Base  # mesmos models que o backend usa em runtime

    expected = {t.name for t in Base.metadata.sorted_tables}
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            ).scalars().all()
        present = set(rows)
    finally:
        await engine.dispose()

    missing = sorted(expected - present)
    if missing:
        _print("verify", f"tabelas faltando no banco: {', '.join(missing)}", "✗")
        _print("verify", "a imagem do backend está defasada ou a migração falhou", "✗")
        sys.exit(1)
    _print("verify", f"{len(expected)} tabelas dos models presentes")


async def ensure_scraper_compat_columns() -> None:
    """Garante colunas do ledger do scraper que o backend consulta.

    `tc_jobs` é criada/migrada pelo serviço scraper (ledger). Mas o backend já
    consulta `tc_jobs.paused_by_user` (pausar/retomar coleta). Para o backend
    nunca dar 500 caso suba antes do scraper aplicar o ledger novo, garantimos a
    coluna aqui de forma idempotente (IF EXISTS — não cria a tabela se ausente).
    """
    engine = create_async_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "ALTER TABLE IF EXISTS tc_jobs "
                    "ADD COLUMN IF NOT EXISTS paused_by_user BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        _print("compat", "tc_jobs.paused_by_user garantida (pausar/retomar coleta)")
    except Exception as exc:  # noqa: BLE001
        _print("compat", f"skip tc_jobs.paused_by_user ({type(exc).__name__})", "!")
    finally:
        await engine.dispose()

    # Texto livre do TC (nome/escolaridade/area) sem limite confiável: alarga
    # colunas legadas VARCHAR(...) para TEXT. migrate.py não altera tipo de
    # coluna existente, então um cargo com area longa derrubava a faixa inteira
    # (StringDataRightTruncationError). ALTER ... TYPE TEXT é idempotente.
    engine = create_async_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            for col in ("nome", "escolaridade", "area"):
                await conn.execute(
                    text(f'ALTER TABLE IF EXISTS cargos ALTER COLUMN "{col}" TYPE TEXT')
                )
        _print("compat", "cargos.nome/escolaridade/area → TEXT (sem truncar coleta)")
    except Exception as exc:  # noqa: BLE001
        _print("compat", f"skip cargos TEXT ({type(exc).__name__})", "!")
    finally:
        await engine.dispose()


async def ensure_meili_settings() -> None:
    """Best-effort: cria o índice Meili e aplica os settings (filtráveis/facetas).

    Faz `/api/q/count` e `/search` nunca darem 500 por atributo não-filtrável,
    sem depender de reindex. NÃO empurra documentos — isso é o `sync_meili`
    (--reindex), pesado e sob demanda. Se o Meili estiver fora no boot, loga e
    segue; nunca derruba o backend.
    """
    try:
        from meilisearch_python_sdk import AsyncClient

        from meili_index import INDEX_NAME, PRIMARY_KEY
        from sync_meili import MEILI_KEY, MEILI_URL, _apply_settings

        async with AsyncClient(MEILI_URL, MEILI_KEY) as client:
            try:
                await client.create_index(INDEX_NAME, primary_key=PRIMARY_KEY)
            except Exception:
                pass  # índice já existe
            await _apply_settings(client.index(INDEX_NAME))
        _print("meili", f"settings aplicados em {MEILI_URL} (filtráveis/facetas)")
    except Exception as exc:  # noqa: BLE001
        _print(
            "meili",
            f"settings não aplicados ({type(exc).__name__}) — Meili indisponível no boot?",
            "!",
        )


async def main() -> None:
    admin_url = _admin_url(DATABASE_URL)
    db_name = _database_name(DATABASE_URL)
    print(f"db_prepare → alvo '{db_name}' em {_label(DATABASE_URL)}", flush=True)

    await wait_for_postgres(admin_url)
    await ensure_database(admin_url, db_name)

    async with bootstrap_lock(admin_url):
        # Alembic é a autoridade de schema (pgvector + tabelas vêm das migrações).
        await run_alembic()

        # Trava: aborta se o schema não bater com os models do backend.
        await verify_schema()

        # Compat com o ledger do scraper (coluna que o backend consulta).
        await ensure_scraper_compat_columns()

    # Meili: aplica settings (idempotente, leve). Best-effort, fora do lock.
    await ensure_meili_settings()

    print("✔ db_prepare concluído", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
