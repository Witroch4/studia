# studIA TaskIQ/NATS Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first operational TaskIQ/NATS foundation for studIA so TC cadernos and images can be processed as persistent, idempotent units instead of container-sized scripts.

**Architecture:** Keep TC execution inside `services/scraper`, because that service already owns Playwright, TC login, residential proxy, direct Postgres persistence, and MinIO image code. Add NATS JetStream brokers, a Redis-backed enqueue facade, and a Postgres ledger. A caderno is a job; each `questaoInicial` range of 200 questions is a unit keyed by `(caderno_id, inicio, page_size)`.

**Tech Stack:** Python 3.12, FastAPI, TaskIQ, `taskiq-nats`, Redis result/idempotency backend, NATS JetStream, PostgreSQL via SQLAlchemy async, Docker Compose.

---

## File Structure

Create these files:

- `services/scraper/app/tasks/__init__.py`  
  Package marker for scraper TaskIQ modules.
- `services/scraper/app/tasks/planning.py`  
  Pure range-planning helpers. No network, no database.
- `services/scraper/app/tasks/ledger.py`  
  Raw SQL migration and repository helpers for `tc_jobs`, `tc_caderno_units`, `tc_image_assets`, and `tc_image_job_assets`.
- `services/scraper/app/tasks/idempotency.py`  
  Redis `SET NX EX` helper and stable idempotency-key builders.
- `services/scraper/app/tasks/enqueue.py`  
  Canonical enqueue facade. Adds labels, claims idempotency, then publishes through the chosen broker.
- `services/scraper/app/tasks/brokers/__init__.py`  
  Broker package marker.
- `services/scraper/app/tasks/brokers/studia.py`  
  `broker_studia_default` and `broker_studia_low` using `PullBasedJetStreamBroker`.
- `services/scraper/app/tasks/dummy.py`  
  Smoke task for Phase 1 verification.
- `services/scraper/app/tasks/smoke.py`  
  CLI smoke script: migrate ledger, enqueue dummy task, poll result.
- `services/scraper/tests/test_taskiq_planning.py`  
  Unit tests for caderno range planning.

Modify these files:

- `services/scraper/pyproject.toml`  
  Add `taskiq`, `taskiq-nats`, `nats-py`, `taskiq-redis`, `redis`, and `pytest`.
- `services/scraper/app/config.py`  
  Add NATS, TaskIQ, Redis, and caderno range settings.
- `services/scraper/app/main.py`  
  Add a short control-plane endpoint `POST /enqueue/caderno` that validates input and enqueues planning only.
- `docker-compose.dev.yml`  
  Add scraper worker services for `default` and `low`; add NATS service only if shared `platform-nats` is not available in the dev environment.
- `services/scraper/docker-compose.prod.yml`  
  Replace permanent `scrape_lote.py` command with API + worker services.

Do not modify `services/scraper/app/client.py` in this phase; it has unrelated local changes.

---

### Task 1: Add Scraper TaskIQ Dependencies and Settings

**Files:**
- Modify: `services/scraper/pyproject.toml`
- Modify: `services/scraper/app/config.py`

- [ ] **Step 1: Add dependencies**

In `services/scraper/pyproject.toml`, add these dependencies under `[tool.poetry.dependencies]`:

```toml
taskiq = "^0.12.0"
taskiq-nats = "^0.6.0"
nats-py = "^2.11.0"
taskiq-redis = "^1.2.0"
redis = "^7.2.0"
pytest = "^8.3.0"
pytest-asyncio = "^0.24.0"
```

- [ ] **Step 2: Add TaskIQ settings**

In `services/scraper/app/config.py`, add these fields to `Settings`:

```python
    # TaskIQ/NATS studIA
    nats_servers: str = "nats://nats:4222"
    taskiq_result_redis_url: str = "redis://redis:6379/2"
    taskiq_idempotency_redis_url: str = "redis://redis:6379/2"
    taskiq_idempotency_ttl_seconds: int = 604800
    taskiq_studia_stream: str = "TASKIQ_STUDIA"
    taskiq_studia_default_subject: str = "taskiq.studia.default"
    taskiq_studia_low_subject: str = "taskiq.studia.low"
    taskiq_studia_default_durable: str = "studia-default-workers"
    taskiq_studia_low_durable: str = "studia-low-workers"
    taskiq_studia_default_pull_batch: int = 1
    taskiq_studia_default_max_ack_pending: int = 1
    taskiq_studia_low_pull_batch: int = 16
    taskiq_studia_low_max_ack_pending: int = 64
    taskiq_studia_ack_wait_seconds: int = 1800
    taskiq_studia_max_deliver: int = 3
    tc_page_size: int = 200
    tc_block_401_452_seconds: int = 86400
    tc_block_403_429_seconds: int = 7200
```

Also add this property inside the `Settings` class, below the TaskIQ fields:

```python
    @property
    def nats_servers_list(self) -> list[str]:
        return [server.strip() for server in self.nats_servers.split(",") if server.strip()]
```

- [ ] **Step 3: Verify dependency lock/install**

Run:

```bash
cd services/scraper
poetry lock
poetry install
```

Expected: Poetry resolves dependencies without conflicts.

- [ ] **Step 4: Commit**

```bash
git add services/scraper/pyproject.toml services/scraper/poetry.lock services/scraper/app/config.py
git commit -m "feat(scraper): add taskiq nats settings"
```

---

### Task 2: Add Deterministic Caderno Range Planning

**Files:**
- Create: `services/scraper/app/tasks/__init__.py`
- Create: `services/scraper/app/tasks/planning.py`
- Create: `services/scraper/tests/test_taskiq_planning.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/tests/test_taskiq_planning.py`:

```python
from app.tasks.planning import CadernoRange, build_caderno_ranges


def test_build_caderno_ranges_for_15298_questions():
    ranges = build_caderno_ranges(expected_total=15298, page_size=200)

    assert len(ranges) == 77
    assert ranges[0] == CadernoRange(
        inicio=0,
        page_size=200,
        position_start=1,
        position_end=200,
        is_last=False,
    )
    assert ranges[5] == CadernoRange(
        inicio=1000,
        page_size=200,
        position_start=1001,
        position_end=1200,
        is_last=False,
    )
    assert ranges[6] == CadernoRange(
        inicio=1200,
        page_size=200,
        position_start=1201,
        position_end=1400,
        is_last=False,
    )
    assert ranges[-1] == CadernoRange(
        inicio=15200,
        page_size=200,
        position_start=15201,
        position_end=15298,
        is_last=True,
    )


def test_build_caderno_ranges_for_29774_questions():
    ranges = build_caderno_ranges(expected_total=29774, page_size=200)

    assert len(ranges) == 149
    assert ranges[-1].inicio == 29600
    assert ranges[-1].position_start == 29601
    assert ranges[-1].position_end == 29774
    assert ranges[-1].is_last is True


def test_build_caderno_ranges_rejects_invalid_values():
    import pytest

    with pytest.raises(ValueError, match="expected_total"):
        build_caderno_ranges(expected_total=0, page_size=200)

    with pytest.raises(ValueError, match="page_size"):
        build_caderno_ranges(expected_total=100, page_size=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd services/scraper
poetry run pytest tests/test_taskiq_planning.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.tasks'`.

- [ ] **Step 3: Implement planning helper**

Create `services/scraper/app/tasks/__init__.py` as an empty file.

Create `services/scraper/app/tasks/planning.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CadernoRange:
    inicio: int
    page_size: int
    position_start: int
    position_end: int
    is_last: bool


def build_caderno_ranges(*, expected_total: int, page_size: int) -> list[CadernoRange]:
    if expected_total <= 0:
        raise ValueError("expected_total must be > 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")

    ranges: list[CadernoRange] = []
    for inicio in range(0, expected_total, page_size):
        position_start = inicio + 1
        position_end = min(inicio + page_size, expected_total)
        ranges.append(
            CadernoRange(
                inicio=inicio,
                page_size=page_size,
                position_start=position_start,
                position_end=position_end,
                is_last=position_end == expected_total,
            )
        )
    return ranges
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd services/scraper
poetry run pytest tests/test_taskiq_planning.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/tasks/__init__.py services/scraper/app/tasks/planning.py services/scraper/tests/test_taskiq_planning.py
git commit -m "feat(scraper): add caderno range planner"
```

---

### Task 3: Add Postgres Ledger Migration and Repository

**Files:**
- Create: `services/scraper/app/tasks/ledger.py`

- [ ] **Step 1: Create ledger module**

Create `services/scraper/app/tasks/ledger.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.tasks.planning import CadernoRange, build_caderno_ranges


LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS tc_jobs (
  id BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  source TEXT NOT NULL,
  external_id TEXT,
  expected_total INTEGER,
  page_size INTEGER NOT NULL DEFAULT 200,
  requested_by INTEGER,
  params JSONB NOT NULL DEFAULT '{}',
  total_units INTEGER NOT NULL DEFAULT 0,
  done_units INTEGER NOT NULL DEFAULT 0,
  failed_units INTEGER NOT NULL DEFAULT 0,
  blocked_units INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  blocked_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tc_jobs_active_caderno
ON tc_jobs (kind, external_id)
WHERE kind = 'caderno' AND status IN ('pending', 'running', 'blocked');

CREATE TABLE IF NOT EXISTS tc_caderno_units (
  id BIGSERIAL PRIMARY KEY,
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  caderno_id BIGINT NOT NULL,
  inicio INTEGER NOT NULL,
  page_size INTEGER NOT NULL DEFAULT 200,
  position_start INTEGER NOT NULL,
  position_end INTEGER NOT NULL,
  status TEXT NOT NULL,
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  questoes_ok INTEGER NOT NULL DEFAULT 0,
  questoes_novas INTEGER NOT NULL DEFAULT 0,
  questoes_atualizadas INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER,
  block_reason TEXT,
  blocked_until TIMESTAMPTZ,
  last_error TEXT,
  leased_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  UNIQUE (caderno_id, inicio, page_size)
);

CREATE INDEX IF NOT EXISTS idx_tc_caderno_units_job_status
ON tc_caderno_units (job_id, status, inicio);

CREATE INDEX IF NOT EXISTS idx_tc_caderno_units_blocked_until
ON tc_caderno_units (status, blocked_until);

CREATE TABLE IF NOT EXISTS tc_image_assets (
  uuid TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  status TEXT NOT NULL,
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  minio_url TEXT,
  minio_object_key TEXT,
  content_type TEXT,
  bytes INTEGER,
  http_status INTEGER,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tc_image_assets_status
ON tc_image_assets (status, updated_at);

CREATE TABLE IF NOT EXISTS tc_image_job_assets (
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  image_uuid TEXT NOT NULL REFERENCES tc_image_assets(uuid) ON DELETE CASCADE,
  PRIMARY KEY (job_id, image_uuid)
);
"""


@dataclass(frozen=True, slots=True)
class CadernoJob:
    id: int
    caderno_id: int
    expected_total: int | None
    total_units: int
    status: str


async def ensure_ledger_schema(conn: AsyncConnection) -> None:
    for stmt in LEDGER_DDL.split(";"):
        sql = stmt.strip()
        if sql:
            await conn.execute(text(sql))


async def upsert_caderno_job(
    session: AsyncSession,
    *,
    caderno_id: int,
    expected_total: int | None,
    page_size: int,
    requested_by: int | None = None,
) -> CadernoJob:
    ranges = (
        build_caderno_ranges(expected_total=expected_total, page_size=page_size)
        if expected_total is not None
        else [CadernoRange(inicio=0, page_size=page_size, position_start=1, position_end=page_size, is_last=False)]
    )
    total_units = len(ranges) if expected_total is not None else 0

    external_id = str(caderno_id)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"tc:caderno:{external_id}"},
    )

    row = (
        await session.execute(
            text(
                """
                SELECT id, external_id, expected_total, total_units, status
                FROM tc_jobs
                WHERE kind = 'caderno'
                  AND external_id = :external_id
                  AND status IN ('pending', 'running', 'blocked')
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"external_id": external_id},
        )
    ).mappings().first()

    if row is None:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO tc_jobs (
                      kind, status, source, external_id, expected_total, page_size,
                      requested_by, total_units, params, updated_at
                    )
                    VALUES (
                      'caderno', 'pending', 'tc', :external_id, :expected_total, :page_size,
                      :requested_by, :total_units, '{}'::jsonb, now()
                    )
                    RETURNING id, external_id, expected_total, total_units, status
                    """
                ),
                {
                    "external_id": external_id,
                    "expected_total": expected_total,
                    "page_size": page_size,
                    "requested_by": requested_by,
                    "total_units": total_units,
                },
            )
        ).mappings().one()

    job_id = int(row["id"])
    for item in ranges:
        await session.execute(
            text(
                """
                INSERT INTO tc_caderno_units (
                  job_id, caderno_id, inicio, page_size, position_start, position_end,
                  status, updated_at
                )
                VALUES (
                  :job_id, :caderno_id, :inicio, :page_size, :position_start,
                  :position_end, 'pending', now()
                )
                ON CONFLICT (caderno_id, inicio, page_size) DO NOTHING
                """
            ),
            {
                "job_id": job_id,
                "caderno_id": caderno_id,
                "inicio": item.inicio,
                "page_size": item.page_size,
                "position_start": item.position_start,
                "position_end": item.position_end,
            },
        )

    await refresh_caderno_job_counts(session, job_id=job_id)

    fresh = (
        await session.execute(
            text(
                """
                SELECT id, external_id, expected_total, total_units, status
                FROM tc_jobs
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id},
        )
    ).mappings().one()
    return CadernoJob(
        id=int(fresh["id"]),
        caderno_id=int(fresh["external_id"]),
        expected_total=fresh["expected_total"],
        total_units=int(fresh["total_units"] or 0),
        status=str(fresh["status"]),
    )


async def refresh_caderno_job_counts(session: AsyncSession, *, job_id: int) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_jobs j
            SET
              done_units = s.done_units,
              failed_units = s.failed_units,
              blocked_units = s.blocked_units,
              updated_at = now()
            FROM (
              SELECT
                job_id,
                count(*) FILTER (WHERE status = 'done') AS done_units,
                count(*) FILTER (WHERE status = 'failed') AS failed_units,
                count(*) FILTER (WHERE status = 'blocked') AS blocked_units
              FROM tc_caderno_units
              WHERE job_id = :job_id
              GROUP BY job_id
            ) s
            WHERE j.id = s.job_id
            """
        ),
        {"job_id": job_id},
    )


async def get_next_caderno_unit(session: AsyncSession, *, caderno_id: int) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT id, job_id, caderno_id, inicio, page_size, status
                FROM tc_caderno_units
                WHERE caderno_id = :caderno_id
                  AND (
                    status IN ('pending', 'failed')
                    OR (status = 'blocked' AND blocked_until <= now())
                  )
                ORDER BY inicio
                LIMIT 1
                """
            ),
            {"caderno_id": caderno_id},
        )
    ).mappings().first()
    return dict(row) if row else None
```

- [ ] **Step 2: Run schema migration manually in dev**

Run this once the dev database is available:

```bash
cd services/scraper
poetry run python - <<'PY'
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.tasks.ledger import ensure_ledger_schema

async def main():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await ensure_ledger_schema(conn)
    await engine.dispose()

asyncio.run(main())
PY
```

Expected: command exits with code 0.

- [ ] **Step 3: Verify caderno planning inserts exact ranges**

Run:

```bash
cd services/scraper
poetry run python - <<'PY'
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.tasks.ledger import ensure_ledger_schema, upsert_caderno_job, get_next_caderno_unit

async def main():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await ensure_ledger_schema(conn)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session.begin() as session:
        job = await upsert_caderno_job(session, caderno_id=95872884, expected_total=15298, page_size=200)
        unit = await get_next_caderno_unit(session, caderno_id=95872884)
        count = (await session.execute(text("SELECT count(*) FROM tc_caderno_units WHERE job_id=:job_id"), {"job_id": job.id})).scalar_one()
        print({"job_id": job.id, "total_units": job.total_units, "unit_count": count, "next_inicio": unit["inicio"]})
    await engine.dispose()

asyncio.run(main())
PY
```

Expected output includes:

```text
'total_units': 77
'unit_count': 77
'next_inicio': 0
```

- [ ] **Step 4: Commit**

```bash
git add services/scraper/app/tasks/ledger.py
git commit -m "feat(scraper): add taskiq ledger schema"
```

---

### Task 4: Add Brokers and Canonical Enqueue

**Files:**
- Create: `services/scraper/app/tasks/brokers/__init__.py`
- Create: `services/scraper/app/tasks/brokers/studia.py`
- Create: `services/scraper/app/tasks/idempotency.py`
- Create: `services/scraper/app/tasks/enqueue.py`

- [ ] **Step 1: Create idempotency helper**

Create `services/scraper/app/tasks/idempotency.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings

IDEMPOTENCY_KEY_LABEL = "idempotency_key"
IDEMPOTENCY_NAMESPACE = "studia:taskiq:idempotency"


def build_idempotency_key(prefix: str, *parts: object) -> str:
    payload = json.dumps([prefix, *parts], sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    task_id: str
    claimed: bool
    redis_key: str


class IdempotencyStore:
    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    async def claim(self, *, idempotency_key: str, task_id: str) -> IdempotencyClaim:
        redis_key = f"{IDEMPOTENCY_NAMESPACE}:{idempotency_key}"
        claimed = await self.redis.set(redis_key, task_id, ex=self.ttl_seconds, nx=True)
        if claimed:
            return IdempotencyClaim(task_id=task_id, claimed=True, redis_key=redis_key)
        existing = await self.redis.get(redis_key)
        return IdempotencyClaim(task_id=str(existing), claimed=False, redis_key=redis_key)


_store: IdempotencyStore | None = None


def get_idempotency_store() -> IdempotencyStore:
    global _store
    if _store is None:
        settings = get_settings()
        redis = Redis.from_url(settings.taskiq_idempotency_redis_url, decode_responses=True)
        _store = IdempotencyStore(redis, ttl_seconds=settings.taskiq_idempotency_ttl_seconds)
    return _store
```

- [ ] **Step 2: Create brokers**

Create `services/scraper/app/tasks/brokers/__init__.py` as an empty file.

Create `services/scraper/app/tasks/brokers/studia.py`:

```python
from __future__ import annotations

from nats.js.api import ConsumerConfig, StreamConfig
from taskiq_nats import PullBasedJetStreamBroker
from taskiq_redis import RedisAsyncResultBackend

from app.config import get_settings


def _result_backend() -> RedisAsyncResultBackend:
    return RedisAsyncResultBackend(redis_url=get_settings().taskiq_result_redis_url)


def _stream_config() -> StreamConfig:
    settings = get_settings()
    return StreamConfig(
        name=settings.taskiq_studia_stream,
        subjects=[
            settings.taskiq_studia_default_subject,
            settings.taskiq_studia_low_subject,
        ],
    )


def _build_broker(*, subject: str, durable: str, pull_batch: int, max_ack_pending: int) -> PullBasedJetStreamBroker:
    settings = get_settings()
    return PullBasedJetStreamBroker(
        servers=settings.nats_servers_list,
        subject=subject,
        stream_name=settings.taskiq_studia_stream,
        durable=durable,
        pull_consume_batch=pull_batch,
        stream_config=_stream_config(),
        consumer_config=ConsumerConfig(
            durable_name=durable,
            filter_subject=subject,
            ack_wait=settings.taskiq_studia_ack_wait_seconds,
            max_deliver=settings.taskiq_studia_max_deliver,
            max_ack_pending=max_ack_pending,
        ),
    ).with_result_backend(_result_backend())


settings = get_settings()

broker_studia_default = _build_broker(
    subject=settings.taskiq_studia_default_subject,
    durable=settings.taskiq_studia_default_durable,
    pull_batch=settings.taskiq_studia_default_pull_batch,
    max_ack_pending=settings.taskiq_studia_default_max_ack_pending,
)

broker_studia_low = _build_broker(
    subject=settings.taskiq_studia_low_subject,
    durable=settings.taskiq_studia_low_durable,
    pull_batch=settings.taskiq_studia_low_pull_batch,
    max_ack_pending=settings.taskiq_studia_low_max_ack_pending,
)
```

- [ ] **Step 3: Create enqueue facade**

Create `services/scraper/app/tasks/enqueue.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from taskiq.task import AsyncTaskiqTask

from app.tasks.brokers.studia import broker_studia_default, broker_studia_low
from app.tasks.idempotency import IDEMPOTENCY_KEY_LABEL, get_idempotency_store

Priority = Literal["default", "low"]


def _resolve_broker(priority: Priority):
    if priority == "default":
        return broker_studia_default
    if priority == "low":
        return broker_studia_low
    raise ValueError(f"Unsupported priority: {priority}")


async def enqueue(task: Any, *, priority: Priority = "default", labels: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    broker = _resolve_broker(priority)
    kicker = task.kicker().with_broker(broker)

    if labels:
        kicker.labels.update(labels)

    idempotency_key = kicker.labels.get(IDEMPOTENCY_KEY_LABEL)
    if isinstance(idempotency_key, str) and idempotency_key.strip():
        task_id = broker.id_generator()
        claim = await get_idempotency_store().claim(idempotency_key=idempotency_key, task_id=task_id)
        if not claim.claimed:
            return AsyncTaskiqTask(
                task_id=claim.task_id,
                result_backend=broker.result_backend,
                return_type=task.return_type,
            )
        kicker = kicker.with_task_id(claim.task_id)

    return await kicker.kiq(**kwargs)
```

- [ ] **Step 4: Verify imports**

Run:

```bash
cd services/scraper
poetry run python - <<'PY'
from app.tasks.brokers.studia import broker_studia_default, broker_studia_low
from app.tasks.enqueue import enqueue

print(type(broker_studia_default).__name__)
print(type(broker_studia_low).__name__)
print(enqueue.__name__)
PY
```

Expected:

```text
PullBasedJetStreamBroker
PullBasedJetStreamBroker
enqueue
```

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/tasks/brokers services/scraper/app/tasks/idempotency.py services/scraper/app/tasks/enqueue.py
git commit -m "feat(scraper): add studia nats brokers"
```

---

### Task 5: Add Smoke Task and Smoke CLI

**Files:**
- Create: `services/scraper/app/tasks/dummy.py`
- Create: `services/scraper/app/tasks/smoke.py`

- [ ] **Step 1: Create dummy task**

Create `services/scraper/app/tasks/dummy.py`:

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.tasks.brokers.studia import broker_studia_default
from app.tasks.ledger import ensure_ledger_schema


@broker_studia_default.task
async def taskiq_dummy_ping(marker: str) -> dict[str, str]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await ensure_ledger_schema(conn)
    await engine.dispose()
    return {"status": "ok", "marker": marker}
```

- [ ] **Step 2: Create smoke CLI**

Create `services/scraper/app/tasks/smoke.py`:

```python
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.tasks.dummy import taskiq_dummy_ping
from app.tasks.enqueue import enqueue
from app.tasks.idempotency import build_idempotency_key
from app.tasks.ledger import ensure_ledger_schema, get_next_caderno_unit, upsert_caderno_job


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await ensure_ledger_schema(conn)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session.begin() as session:
        job = await upsert_caderno_job(
            session,
            caderno_id=95872884,
            expected_total=15298,
            page_size=200,
        )
        unit = await get_next_caderno_unit(session, caderno_id=95872884)
        print({"job_id": job.id, "total_units": job.total_units, "next_inicio": unit["inicio"]})

    marker = str(uuid.uuid4())
    task = await enqueue(
        taskiq_dummy_ping,
        priority="default",
        labels={"idempotency_key": build_idempotency_key("dummy", marker)},
        marker=marker,
    )
    print({"task_id": task.task_id, "marker": marker})
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Run smoke without worker**

Run:

```bash
cd services/scraper
poetry run python -m app.tasks.smoke
```

Expected:

```text
'total_units': 77
'next_inicio': 0
'task_id': '<non-empty task id>'
```

The task will remain pending if no worker is running. This is acceptable for this step.

- [ ] **Step 4: Commit**

```bash
git add services/scraper/app/tasks/dummy.py services/scraper/app/tasks/smoke.py
git commit -m "feat(scraper): add taskiq smoke task"
```

---

### Task 6: Add Control-Plane Enqueue Endpoint

**Files:**
- Modify: `services/scraper/app/main.py`

- [ ] **Step 1: Add request/response models**

In `services/scraper/app/main.py`, near the existing FastAPI body models, add:

```python
class EnqueueCadernoBody(BaseModel):
    caderno_id: int
    expected_total: int | None = None
    page_size: int = 200
    requested_by: int | None = None


class EnqueueCadernoResponse(BaseModel):
    job_id: int
    status: str
    total_units: int
```

- [ ] **Step 2: Add endpoint**

In `services/scraper/app/main.py`, below `health()`, add:

```python
@api.post("/enqueue/caderno", response_model=EnqueueCadernoResponse)
async def enqueue_caderno(body: EnqueueCadernoBody) -> EnqueueCadernoResponse:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.tasks.ledger import ensure_ledger_schema, get_next_caderno_unit, upsert_caderno_job
    from app.tasks.dummy import taskiq_dummy_ping
    from app.tasks.enqueue import enqueue
    from app.tasks.idempotency import build_idempotency_key

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await ensure_ledger_schema(conn)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session.begin() as session:
        job = await upsert_caderno_job(
            session,
            caderno_id=body.caderno_id,
            expected_total=body.expected_total,
            page_size=body.page_size,
            requested_by=body.requested_by,
        )
        unit = await get_next_caderno_unit(session, caderno_id=body.caderno_id)

    if unit is not None:
        await enqueue(
            taskiq_dummy_ping,
            priority="default",
            labels={"idempotency_key": build_idempotency_key("tc-page", body.caderno_id, unit["inicio"], body.page_size)},
            marker=f"caderno:{body.caderno_id}:inicio:{unit['inicio']}",
        )

    await engine.dispose()
    return EnqueueCadernoResponse(job_id=job.id, status=job.status, total_units=job.total_units)
```

This endpoint intentionally enqueues the dummy task in Phase 1. Phase 2 replaces it with `coletar_pagina_caderno_tc`.

- [ ] **Step 3: Verify endpoint import**

Run:

```bash
cd services/scraper
poetry run python - <<'PY'
from app.main import api

routes = [route.path for route in api.routes]
assert "/enqueue/caderno" in routes
print("ok")
PY
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add services/scraper/app/main.py
git commit -m "feat(scraper): add caderno enqueue endpoint"
```

---

### Task 7: Wire Dev and Production Services

**Files:**
- Modify: `docker-compose.dev.yml`
- Modify: `services/scraper/docker-compose.prod.yml`

- [ ] **Step 1: Add dev workers**

In `docker-compose.dev.yml`, add these services after `scraper`:

```yaml
  scraper-worker-default:
    build:
      context: ./services/scraper
    container_name: studia-scraper-worker-default-dev
    volumes:
      - ./services/scraper:/app
      - ./backend:/backend:ro
      - scraper_state:/state
    command: taskiq worker app.tasks.brokers.studia:broker_studia_default --workers 1 --fs-discover --tasks-pattern 'app/tasks/**/*.py'
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=INFO
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia
      - NATS_SERVERS=nats://nats:4222
      - TASKIQ_RESULT_REDIS_URL=redis://redis:6379/2
      - TASKIQ_IDEMPOTENCY_REDIS_URL=redis://redis:6379/2
    networks:
      - shared

  scraper-worker-low:
    build:
      context: ./services/scraper
    container_name: studia-scraper-worker-low-dev
    volumes:
      - ./services/scraper:/app
      - ./backend:/backend:ro
      - scraper_state:/state
    command: taskiq worker app.tasks.brokers.studia:broker_studia_low --workers 5 --fs-discover --tasks-pattern 'app/tasks/**/*.py'
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=INFO
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia
      - NATS_SERVERS=nats://nats:4222
      - TASKIQ_RESULT_REDIS_URL=redis://redis:6379/2
      - TASKIQ_IDEMPOTENCY_REDIS_URL=redis://redis:6379/2
    networks:
      - shared
```

If the shared network does not expose a service named `nats`, add a network alias to the existing platform NATS container or set `NATS_SERVERS=nats://platform-nats:4222`.

- [ ] **Step 2: Replace production scraper service**

In `services/scraper/docker-compose.prod.yml`, replace the single `scraper` service command with three services:

```yaml
services:
  scraper-api:
    build:
      context: .
    container_name: tc-scraper-api-prod
    restart: unless-stopped
    env_file:
      - .env.prod
    volumes:
      - ./state:/state
      - ./scripts:/app/scripts:ro
    networks:
      - shared
    command: python -m app.main api-serve --host 0.0.0.0 --port 8090
    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
      - TC_STORAGE_STATE_PATH=/state/storage_state.json
      - SCRAPE_STATE_PATH=/state/scrape_state.db
      - DISCOVERY_DUMP_DIR=/state/discovery
      - RESIDENTIAL_PROXY_URL=socks5h://tc-scraper:${RP_SERVICE_SECRET}@residential-proxy:1080

  scraper-worker-default:
    build:
      context: .
    container_name: tc-scraper-worker-default-prod
    restart: unless-stopped
    env_file:
      - .env.prod
    volumes:
      - ./state:/state
      - ./scripts:/app/scripts:ro
    networks:
      - shared
    command: taskiq worker app.tasks.brokers.studia:broker_studia_default --workers 1 --fs-discover --tasks-pattern 'app/tasks/**/*.py'
    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
      - TC_STORAGE_STATE_PATH=/state/storage_state.json
      - SCRAPE_STATE_PATH=/state/scrape_state.db
      - DISCOVERY_DUMP_DIR=/state/discovery
      - RESIDENTIAL_PROXY_URL=socks5h://tc-scraper:${RP_SERVICE_SECRET}@residential-proxy:1080

  scraper-worker-low:
    build:
      context: .
    container_name: tc-scraper-worker-low-prod
    restart: unless-stopped
    env_file:
      - .env.prod
    volumes:
      - ./state:/state
      - ./scripts:/app/scripts:ro
    networks:
      - shared
    command: taskiq worker app.tasks.brokers.studia:broker_studia_low --workers 5 --fs-discover --tasks-pattern 'app/tasks/**/*.py'
    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
      - TC_STORAGE_STATE_PATH=/state/storage_state.json
      - SCRAPE_STATE_PATH=/state/scrape_state.db
      - DISCOVERY_DUMP_DIR=/state/discovery
      - RESIDENTIAL_PROXY_URL=socks5h://tc-scraper:${RP_SERVICE_SECRET}@residential-proxy:1080
```

Keep the existing `networks:` block unchanged.

- [ ] **Step 3: Validate compose config**

Run:

```bash
docker compose -f docker-compose.dev.yml config >/tmp/studia-dev-compose.yml
docker compose -f services/scraper/docker-compose.prod.yml config >/tmp/studia-scraper-prod-compose.yml
```

Expected: both commands exit 0.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.dev.yml services/scraper/docker-compose.prod.yml
git commit -m "chore(scraper): wire taskiq worker services"
```

---

### Task 8: End-to-End Phase 1 Verification

**Files:**
- No new files.

- [ ] **Step 1: Run unit tests**

```bash
cd services/scraper
poetry run pytest tests/test_taskiq_planning.py -q
```

Expected: `3 passed`.

- [ ] **Step 2: Rebuild scraper services**

```bash
docker compose -f docker-compose.dev.yml build scraper scraper-worker-default scraper-worker-low
```

Expected: build succeeds.

- [ ] **Step 3: Start scraper API and default worker**

```bash
docker compose -f docker-compose.dev.yml up -d scraper scraper-worker-default
```

Expected: containers stay running.

- [ ] **Step 4: Run smoke enqueue**

```bash
docker compose -f docker-compose.dev.yml exec scraper python -m app.tasks.smoke
```

Expected output includes:

```text
'total_units': 77
'next_inicio': 0
'task_id': '<non-empty task id>'
```

- [ ] **Step 5: Verify worker consumed dummy task**

```bash
docker compose -f docker-compose.dev.yml logs --tail=200 scraper-worker-default
```

Expected: logs include execution of `taskiq_dummy_ping`.

- [ ] **Step 6: Verify ledger ranges in Postgres**

```bash
docker exec postgres psql -U postgres -d studia -c "
SELECT caderno_id, count(*) AS units, min(inicio) AS first_inicio, max(inicio) AS last_inicio
FROM tc_caderno_units
WHERE caderno_id = 95872884
GROUP BY caderno_id;
"
```

Expected:

```text
caderno_id | units | first_inicio | last_inicio
95872884   | 77    | 0            | 15200
```

- [ ] **Step 7: Document Phase 1 smoke commands**

Append this section to `services/scraper/RUN-SSH.md`:

````markdown
## TaskIQ/NATS Phase 1 smoke

Local/dev smoke:

```bash
docker compose -f docker-compose.dev.yml build scraper scraper-worker-default scraper-worker-low
docker compose -f docker-compose.dev.yml up -d scraper scraper-worker-default
docker compose -f docker-compose.dev.yml exec scraper python -m app.tasks.smoke
docker compose -f docker-compose.dev.yml logs --tail=200 scraper-worker-default
```

Expected ledger check:

```bash
docker exec postgres psql -U postgres -d studia -c "
SELECT caderno_id, count(*) AS units, min(inicio) AS first_inicio, max(inicio) AS last_inicio
FROM tc_caderno_units
WHERE caderno_id = 95872884
GROUP BY caderno_id;
"
```
````

Then commit:

```bash
git add services/scraper/RUN-SSH.md
git commit -m "docs(scraper): document taskiq phase one smoke"
```

---

## Self-Review

Spec coverage:

- NATS JetStream base: Tasks 1, 4, 7, 8.
- Postgres ledger: Task 3.
- Range control by caderno index: Task 2 and Task 3.
- No caderno restart from zero: Task 3 `get_next_caderno_unit()` orders by `inicio` and filters only non-`done` units.
- No Control Center: not included.
- Images ledger tables: Task 3 creates base tables; image tasks wait for Phase 3.

Known implementation warning:

- Task 3 intentionally uses `pg_advisory_xact_lock(hashtext('tc:caderno:{id}'))` instead of `ON CONFLICT`, because the active-job guard is a partial unique index. Keep that advisory lock around the `SELECT` and `INSERT`; otherwise concurrent enqueue calls can create duplicate active caderno jobs.

Phase 1 completion means the queue, ledger, and smoke path work. It does not yet scrape real TC pages; that starts in Phase 2.
