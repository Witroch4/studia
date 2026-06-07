"""Bootstrap do banco studIA — leva o Postgres de zero a pronto-pra-produção.

Roda como one-shot antes do `docker stack deploy` (ver build.sh). Idempotente
e seguro para reexecução. Faz, em ordem:

    1. Espera o PostgreSQL aceitar conexões (com retries)
    2. Cria o database 'studia' se ele não existir
    3. Habilita a extensão pgvector + roda as migrações (migrate.py:
       create_all de tabelas novas + ALTER incremental de colunas faltantes)

Uso:
    python -m scripts.db_prepare

Lê DATABASE_URL do ambiente (mesmo formato do backend:
postgresql+asyncpg://user:pass@host:5432/studia).
"""

import asyncio
import os
import sys
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)
RETRIES = int(os.environ.get("DB_CONNECT_RETRIES", "30"))
RETRY_DELAY_S = float(os.environ.get("DB_CONNECT_SLEEP_MS", "2000")) / 1000


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


async def main() -> None:
    admin_url = _admin_url(DATABASE_URL)
    db_name = _database_name(DATABASE_URL)
    print(f"db_prepare → alvo '{db_name}' em {_label(DATABASE_URL)}", flush=True)

    await wait_for_postgres(admin_url)
    await ensure_database(admin_url, db_name)

    # migrate.py importa `engine` ligado ao DATABASE_URL (studia já existe agora):
    # habilita pgvector, cria tabelas novas (create_all) e aplica ALTERs faltantes.
    from migrate import migrate

    await migrate()
    _print("migrate", "schema pronto (pgvector + tabelas)")
    print("✔ db_prepare concluído", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
