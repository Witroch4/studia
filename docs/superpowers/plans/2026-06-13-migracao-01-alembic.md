# Migração studIA → padrão · Plano 01: Adotar Alembic

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o `migrate.py` caseiro por **Alembic** como autoridade única de schema, sem recriar tabelas em bancos já existentes (dev/prod) e sem subir deploy com schema defasado.

**Architecture:** Alembic em modo async (`env.py` lê `DATABASE_URL` do ambiente e usa `models.Base.metadata`). Uma migração **baseline** autogerada captura o schema atual; uma segunda migração porta o isolamento multiusuário (índices custom + backfill) que hoje vive no `migrate.py`. O `scripts/db_prepare.py` passa a rodar `alembic upgrade head` com **auto-stamp** de bancos legados (que já têm as tabelas, mas não têm `alembic_version`). Testes continuam em SQLite + `create_all`; o drift entre models e migrações é guardado por `alembic check`.

**Tech Stack:** Alembic, SQLAlchemy 2.x async, asyncpg, PostgreSQL + pgvector.

**Pré-requisito:** um PostgreSQL acessível para gerar a baseline e validar o upgrade. Use o do dev: `./dev.sh up:d` (Postgres no host:5433, container `postgres:5432`).

---

### Task 1: Adicionar Alembic às dependências

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Adicionar a dependência**

Em `backend/requirements.txt`, logo abaixo da linha `asyncpg==0.30.0`, adicione:

```
alembic>=1.13,<2
```

- [ ] **Step 2: Instalar no container e verificar**

Run:
```bash
./dev.sh up:d
./dev.sh shell backend -c "pip install -r requirements.txt && alembic --version"
```
Expected: imprime `alembic 1.1x.x` sem erro.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "build(alembic): adiciona alembic às deps do backend"
```

---

### Task 2: Esqueleto do Alembic (async)

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`

- [ ] **Step 1: Criar `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Criar `backend/alembic/env.py`** (lê `DATABASE_URL`, usa `Base.metadata`, registra o tipo `Vector` para o autogenerate)

```python
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importa os models p/ popular o metadata e registra o tipo Vector (pgvector)
# para que o autogenerate saiba renderizar colunas de embedding.
import models  # noqa: F401
from pgvector.sqlalchemy import Vector  # noqa: F401
from models import Base

config = context.config

db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3: Criar `backend/alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Criar `backend/alembic/versions/.gitkeep`** (arquivo vazio, para versionar o diretório)

- [ ] **Step 5: Verificar que o Alembic enxerga a config**

Run:
```bash
./dev.sh shell backend -c "cd /app && alembic history"
```
Expected: roda sem erro e imprime histórico vazio (nenhuma revisão ainda).

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat(alembic): esqueleto async (env.py usa Base.metadata + DATABASE_URL)"
```

---

### Task 3: Baseline — captura do schema atual

A baseline precisa ser autogerada contra um banco **vazio** (o dev já tem tabelas; autogenerate contra ele produziria diff vazio). Criamos um DB descartável só para gerar a baseline.

**Files:**
- Create: `backend/alembic/versions/<hash>_baseline.py` (gerado pelo autogenerate; ajustado à mão)

- [ ] **Step 1: Criar um DB vazio descartável**

Run:
```bash
./dev.sh shell backend -c 'cd /app && python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def m():
    e=create_async_engine(\"postgresql+asyncpg://postgres:postgres@postgres:5432/postgres\", isolation_level=\"AUTOCOMMIT\")
    async with e.connect() as c:
        await c.execute(text(\"DROP DATABASE IF EXISTS studia_baseline\"))
        await c.execute(text(\"CREATE DATABASE studia_baseline\"))
    await e.dispose()
asyncio.run(m())
print(\"studia_baseline criado\")
"'
```
Expected: `studia_baseline criado`.

- [ ] **Step 2: Autogerar a baseline contra o DB vazio**

Run:
```bash
./dev.sh shell backend -c 'cd /app && DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia_baseline alembic revision --autogenerate -m "baseline schema"'
```
Expected: cria `backend/alembic/versions/<hash>_baseline_schema.py` com `op.create_table(...)` para todas as ~28 tabelas dos models.

- [ ] **Step 3: Ajustar a baseline — habilitar pgvector ANTES das tabelas**

Abra o arquivo gerado e, na primeira linha de `upgrade()`, antes de qualquer `op.create_table`, adicione:

```python
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

E confirme que o topo do arquivo tem `import pgvector.sqlalchemy` (o `script.py.mako` já garante isso). Verifique que as colunas de embedding aparecem como `pgvector.sqlalchemy.Vector(dim=...)`.

- [ ] **Step 4: Validar a baseline contra o DB vazio (upgrade + check)**

Run:
```bash
./dev.sh shell backend -c 'cd /app && DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia_baseline alembic upgrade head && DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia_baseline alembic check'
```
Expected: `upgrade` cria tudo; `alembic check` imprime `No new upgrade operations detected.` (models == migração).

- [ ] **Step 5: Limpar o DB descartável**

Run:
```bash
./dev.sh shell backend -c 'cd /app && python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def m():
    e=create_async_engine(\"postgresql+asyncpg://postgres:postgres@postgres:5432/postgres\", isolation_level=\"AUTOCOMMIT\")
    async with e.connect() as c:
        await c.execute(text(\"DROP DATABASE IF EXISTS studia_baseline\"))
    await e.dispose()
asyncio.run(m())
"'
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(alembic): baseline do schema atual (pgvector + ~28 tabelas)"
```

---

### Task 4: Migração do isolamento multiusuário (índices custom + backfill)

Porta o passo `_migrar_isolamento` do `migrate.py` (índices únicos por usuário + backfill dos legados → admin) para uma migração Alembic, preservando a idempotência.

**Files:**
- Create: `backend/alembic/versions/<hash>_multiuser_isolation.py`

- [ ] **Step 1: Criar a migração vazia (encadeada na baseline)**

Run:
```bash
./dev.sh shell backend -c 'cd /app && alembic revision -m "multiuser isolation indexes + backfill"'
```
Expected: cria um arquivo com `down_revision` apontando para a baseline.

- [ ] **Step 2: Preencher `upgrade()`** com o DDL idempotente (copiado de `migrate.py:108-161`)

```python
def upgrade() -> None:
    ddl = [
        "DROP INDEX IF EXISTS uq_questao_anotacoes_scope",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_questao_anotacoes_scope_uid "
        "ON questao_anotacoes (COALESCE(usuario_uid, ''), COALESCE(caderno_id, 0), questao_id)",
        "DROP INDEX IF EXISTS ix_questoes_favoritas_questao_id",
        "CREATE INDEX IF NOT EXISTS ix_questoes_favoritas_questao_id ON questoes_favoritas (questao_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_favorita_owner_questao "
        "ON questoes_favoritas (COALESCE(owner_uid, ''), questao_id)",
        "CREATE INDEX IF NOT EXISTS ix_cadernos_questoes_owner_uid ON cadernos_questoes (owner_uid)",
        "CREATE INDEX IF NOT EXISTS ix_questoes_favoritas_owner_uid ON questoes_favoritas (owner_uid)",
        "CREATE INDEX IF NOT EXISTS ix_questao_anotacoes_usuario_uid ON questao_anotacoes (usuario_uid)",
        "CREATE INDEX IF NOT EXISTS ix_calculadora_historico_usuario_uid ON calculadora_historico (usuario_uid)",
    ]
    for stmt in ddl:
        op.execute(stmt)

    # Backfill legados → admin mais antigo. Idempotente; só roda se "user" existir
    # (Better Auth) e houver admin. Cadernos DE GUIA ficam owner_uid=NULL.
    op.execute(
        """
        DO $$
        DECLARE admin_id text;
        BEGIN
          IF to_regclass('public."user"') IS NULL THEN RETURN; END IF;
          SELECT id INTO admin_id FROM "user" WHERE role = 'admin' ORDER BY "createdAt" LIMIT 1;
          IF admin_id IS NULL THEN RETURN; END IF;
          UPDATE cadernos_questoes SET owner_uid = admin_id
            WHERE owner_uid IS NULL AND id NOT IN
              (SELECT caderno_id FROM guia_cadernos WHERE caderno_id IS NOT NULL);
          UPDATE questoes_favoritas SET owner_uid = admin_id WHERE owner_uid IS NULL;
          UPDATE questao_anotacoes SET usuario_uid = admin_id WHERE usuario_uid IS NULL;
          UPDATE resolucoes SET usuario_uid = admin_id WHERE usuario_uid IS NULL;
          UPDATE calculadora_historico SET usuario_uid = admin_id WHERE usuario_uid IS NULL;
        END $$;
        """
    )


def downgrade() -> None:
    for idx in (
        "uq_questao_anotacoes_scope_uid",
        "uq_favorita_owner_questao",
        "ix_cadernos_questoes_owner_uid",
        "ix_questoes_favoritas_owner_uid",
        "ix_questao_anotacoes_usuario_uid",
        "ix_calculadora_historico_usuario_uid",
    ):
        op.execute(f"DROP INDEX IF EXISTS {idx}")
```

- [ ] **Step 3: Validar contra DB vazio (baseline + esta migração + check)**

Run:
```bash
./dev.sh shell backend -c 'cd /app && python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def m():
    e=create_async_engine(\"postgresql+asyncpg://postgres:postgres@postgres:5432/postgres\", isolation_level=\"AUTOCOMMIT\")
    async with e.connect() as c:
        await c.execute(text(\"DROP DATABASE IF EXISTS studia_baseline\")); await c.execute(text(\"CREATE DATABASE studia_baseline\"))
    await e.dispose()
asyncio.run(m())
" && DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia_baseline alembic upgrade head && DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia_baseline alembic check'
```
Expected: `upgrade` aplica as duas migrações; `alembic check` → `No new upgrade operations detected.` Depois, limpe: `DROP DATABASE studia_baseline` (mesmo snippet do Task 3 Step 5).

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(alembic): migração de isolamento multiusuário (índices + backfill)"
```

---

### Task 5: `db_prepare` roda Alembic (com auto-stamp de legado)

Bancos legados (dev/prod) já têm as tabelas via `migrate.py`, mas não têm `alembic_version`. Rodar `upgrade head` neles tentaria recriar tabelas → erro. A solução: se `alembic_version` está ausente E uma tabela conhecida (`questoes`) já existe → `stamp head` (adota o legado sem rodar DDL); caso contrário → `upgrade head` (banco novo/vazio constrói tudo).

**Files:**
- Modify: `backend/scripts/db_prepare.py` (substitui o bloco `from migrate import migrate; await migrate()`, linhas 247-252)

- [ ] **Step 1: Adicionar a função de upgrade Alembic** no topo de `db_prepare.py` (após os imports existentes)

```python
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


async def run_alembic() -> None:
    """Roda Alembic. Auto-stamp de bancos legados (tabelas existem, sem alembic_version)."""
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            has_version = (
                await conn.execute(text("SELECT to_regclass('public.alembic_version')"))
            ).scalar()
            has_legacy = (
                await conn.execute(text("SELECT to_regclass('public.questoes')"))
            ).scalar()
    finally:
        await engine.dispose()

    env = {**os.environ, "DATABASE_URL": DATABASE_URL}
    if not has_version and has_legacy:
        _print("alembic", "banco legado detectado — stamp head (adoção sem DDL)")
        subprocess.run(["alembic", "stamp", "head"], cwd=BACKEND_DIR, env=env, check=True)
    subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND_DIR, env=env, check=True)
    _print("alembic", "upgrade head aplicado")
```

- [ ] **Step 2: Trocar a chamada em `main()`** — substitua as linhas 247-252:

```python
        # migrate.py importa `engine` ligado ao DATABASE_URL (studia já existe):
        # habilita pgvector, cria tabelas novas (create_all) e aplica ALTERs.
        from migrate import migrate

        await migrate()
        _print("migrate", "schema pronto (pgvector + tabelas)")
```

por:

```python
        # Alembic é a autoridade de schema (pgvector + tabelas vêm das migrações).
        await run_alembic()
```

- [ ] **Step 3: Validar `db_prepare` num DB legado simulado**

Run (cria DB com schema via create_all, sem alembic_version → deve dar stamp + upgrade sem erro):
```bash
./dev.sh shell backend -c 'cd /app && python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from models import Base
async def m():
    a=create_async_engine(\"postgresql+asyncpg://postgres:postgres@postgres:5432/postgres\", isolation_level=\"AUTOCOMMIT\")
    async with a.connect() as c:
        await c.execute(text(\"DROP DATABASE IF EXISTS studia_legacy\")); await c.execute(text(\"CREATE DATABASE studia_legacy\"))
    await a.dispose()
    e=create_async_engine(\"postgresql+asyncpg://postgres:postgres@postgres:5432/studia_legacy\")
    async with e.begin() as c:
        await c.execute(text(\"CREATE EXTENSION IF NOT EXISTS vector\")); await c.run_sync(Base.metadata.create_all)
    await e.dispose()
asyncio.run(m())
" && DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia_legacy python -m scripts.db_prepare'
```
Expected: log mostra `banco legado detectado — stamp head`, depois `upgrade head aplicado`, `verify` OK, `db_prepare concluído`. Limpe `DROP DATABASE studia_legacy` depois.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/db_prepare.py
git commit -m "feat(alembic): db_prepare roda alembic upgrade (auto-stamp de legado)"
```

---

### Task 6: `dev.sh migrate` usa o mesmo caminho

Unifica dev e prod no `db_prepare` (idempotente: espera Postgres, cria DB, roda Alembic com auto-stamp, aplica settings do Meili).

**Files:**
- Modify: `dev.sh` (função `cmd_migrate`, ~linha 291; e o hook de `up`, ~linha 127)

- [ ] **Step 1: Trocar o comando de migração**

Em `dev.sh`, onde hoje executa `python migrate.py`, troque por `python -m scripts.db_prepare`. Há dois pontos (a função `cmd_migrate` e o hook de `up`). Após a troca, `grep -n "migrate.py" dev.sh` deve retornar vazio.

- [ ] **Step 2: Validar no dev real**

Run:
```bash
./dev.sh migrate
```
Expected: `db_prepare` roda fim-a-fim contra o Postgres do dev; primeira execução faz `stamp head` (banco dev é legado); execuções seguintes só `upgrade head` (no-op).

- [ ] **Step 3: Rodar a suíte de testes (garantir que nada quebrou)**

Run:
```bash
./dev.sh shell backend -c "cd /app && pytest -q"
```
Expected: suíte verde (57 testes), igual a antes — testes usam SQLite/`create_all`, não tocam Alembic.

- [ ] **Step 4: Commit**

```bash
git add dev.sh
git commit -m "chore(alembic): dev.sh migrate usa db_prepare (caminho único dev/prod)"
```

---

### Task 7: Aposentar `migrate.py` + guarda de drift

**Files:**
- Delete: `backend/migrate.py`
- Create: `backend/tests/test_alembic_no_drift.py`

- [ ] **Step 1: Remover o `migrate.py`** (a lógica vive nas migrações agora)

Run:
```bash
git rm backend/migrate.py
```
Confirme que nada mais o importa: `grep -rn "from migrate\|import migrate" backend/` deve retornar vazio (o `db_prepare` já foi trocado no Task 5).

- [ ] **Step 2: Escrever o teste-guarda de drift** (sempre-ligado, contra `studia_test`)

```python
import os
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TEST_DB = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/studia_test",
)


def test_alembic_check_sem_drift():
    """alembic check contra o banco de teste: models == migrações (sem drift)."""
    env = {**os.environ, "DATABASE_URL": TEST_DB}
    up = subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert up.returncode == 0, up.stderr
    chk = subprocess.run(["alembic", "check"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert chk.returncode == 0, f"drift detectado:\n{chk.stdout}\n{chk.stderr}"
```

- [ ] **Step 3: Garantir o banco de teste e rodar o teste-guarda**

Run:
```bash
./dev.sh shell backend -c 'cd /app && python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def m():
    e=create_async_engine(\"postgresql+asyncpg://postgres:postgres@postgres:5432/postgres\", isolation_level=\"AUTOCOMMIT\")
    async with e.connect() as c:
        if not (await c.execute(text(\"SELECT 1 FROM pg_database WHERE datname=:n\"), {\"n\": \"studia_test\"})).scalar():
            await c.execute(text(\"CREATE DATABASE studia_test\"))
    await e.dispose()
asyncio.run(m())
" && pytest tests/test_alembic_no_drift.py -v'
```
Expected: `test_alembic_check_sem_drift PASSED`. O `studia_test` é **persistente** (não é destruído).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_alembic_no_drift.py
git rm backend/migrate.py
git commit -m "feat(alembic): aposenta migrate.py + teste-guarda de drift (alembic check)"
```

- [ ] **Step 5: Deploy (fecha o ciclo do CLAUDE.md) — rode por ÚLTIMO, após o Task 8**

Run:
```bash
git push origin main
./build.sh
```
Expected: `build.sh` builda, sobe imagens e roda `db_prepare` em prod — que agora faz `stamp head` no banco de prod legado (1ª vez) e `upgrade head`. `verify_schema` confirma as tabelas. Deploy conclui.

---

### Task 8: Testes em Postgres (conftest com rollback) + `./dev.sh test`

Troca o SQLite in-memory por um database Postgres persistente (`studia_test`) na
infra compartilhada, com isolamento por **transação + rollback** (sem recriar o
banco). Fidelidade total: pgvector e índices Postgres passam a ser exercitados.

**Files:**
- Modify: `backend/tests/conftest.py` (fixture `db_session`, linhas 30-40)
- Modify: `dev.sh` (novo subcomando `test`)

- [ ] **Step 1: Reescrever as fixtures de DB do `conftest.py`**

Substitua a fixture `db_session` (linhas 30-40) por engine de sessão + rollback por teste:

```python
import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/studia_test",
)


@pytest_asyncio.fixture(scope="session")
async def _engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    # Isolamento por teste: transação externa + savepoints internos; rollback no fim.
    conn = await _engine.connect()
    trans = await conn.begin()
    Session = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
```

Remova o `from models import Base` se ficar sem uso (o schema do `studia_test` vem
do Alembic, não de `create_all`).

- [ ] **Step 2: Adicionar `./dev.sh test`** (garante `studia_test` + Alembic + pytest)

Em `dev.sh`, adicione a função abaixo e registre `test) shift; cmd_test "$@" ;;` no
`case` de comandos (junto de `migrate)`):

```bash
cmd_test() {
  dc exec -T backend sh -lc '
    python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def m():
    e=create_async_engine(\"postgresql+asyncpg://postgres:postgres@postgres:5432/postgres\", isolation_level=\"AUTOCOMMIT\")
    async with e.connect() as c:
        if not (await c.execute(text(\"SELECT 1 FROM pg_database WHERE datname=:n\"),{\"n\":\"studia_test\"})).scalar():
            await c.execute(text(\"CREATE DATABASE studia_test\"))
    await e.dispose()
asyncio.run(m())
" &&
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia_test alembic upgrade head &&
    pytest '"$@"'
  '
}
```

- [ ] **Step 3: Rodar a suíte inteira no Postgres**

Run:
```bash
./dev.sh test -q
```
Expected: a suíte roda no `studia_test` (Postgres real). Alguns testes podem revelar
diferenças que o SQLite mascarava — corrija-os: é exatamente o ganho de fidelidade.
Meta: verde no Postgres.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py dev.sh
git commit -m "test(postgres): conftest em Postgres com rollback + ./dev.sh test (fim do SQLite)"
```

---

## Self-Review

- **Cobertura do spec (§15, item Alembic):** `migrate.py` → Alembic ✓ (Tasks 2-4, 7); `db_prepare` aponta p/ Alembic ✓ (Task 5); `dev.sh` ✓ (Task 6); pgvector preservado ✓ (Task 3 Step 3); isolamento multiusuário preservado ✓ (Task 4); trava de deploy (`verify_schema`) intacta ✓ (Task 5 mantém o resto do `db_prepare`).
- **Testes em Postgres (spec §17):** conftest passa de SQLite p/ `studia_test` real com isolamento por rollback ✓ (Task 8); teste-guarda de drift sempre-ligado ✓ (Task 7 Step 2). Fim da divergência SQLite≠Postgres.
- **Placeholders:** nenhum — todo passo tem comando/código exato.
- **Consistência:** `run_alembic()` (Task 5) e o teste (Task 7) usam os mesmos comandos `alembic upgrade head`/`alembic check`; a detecção de legado usa `to_regclass('public.questoes')` consistente.
- **Risco conhecido:** o autogenerate da baseline (Task 3) pode emitir `op.create_table` em ordem que viole FK; se ocorrer, o `upgrade` no Step 4 falha visivelmente e a ordem é ajustada à mão antes do commit. Por isso a baseline é validada contra DB vazio antes de seguir.

## Notas de execução

- Tasks 3, 4, 7 e 8 precisam do Postgres compartilhado de pé (já no ar: container `postgres` pgvector/pg17 `:5432`).
- A 1ª execução em qualquer banco legado (dev e prod) faz `stamp head` automático — não há recriação de tabela. Bancos novos (a futura instância compartilhada `minha_rede`, Plano 06) constroem tudo via `upgrade head`.
