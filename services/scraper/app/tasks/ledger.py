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

-- Pausa manual via UI: quando TRUE, o supervisor para de enfileirar novas
-- faixas deste job (units em voo terminam; o progresso fica salvo).
ALTER TABLE tc_jobs
ADD COLUMN IF NOT EXISTS paused_by_user BOOLEAN NOT NULL DEFAULT FALSE;

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

CREATE UNIQUE INDEX IF NOT EXISTS uq_tc_jobs_active_comentarios
ON tc_jobs (kind, external_id)
WHERE kind = 'comentarios' AND status IN ('pending', 'running', 'blocked');

CREATE TABLE IF NOT EXISTS tc_comentario_units (
  id BIGSERIAL PRIMARY KEY,
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  caderno_id BIGINT NOT NULL,
  questao_id BIGINT NOT NULL,
  status TEXT NOT NULL,
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  coments_alunos INTEGER NOT NULL DEFAULT 0,
  coments_professores INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER,
  block_reason TEXT,
  blocked_until TIMESTAMPTZ,
  last_error TEXT,
  leased_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  UNIQUE (job_id, questao_id)
);

CREATE INDEX IF NOT EXISTS idx_tc_comentario_units_job_status
ON tc_comentario_units (job_id, status, questao_id);

CREATE INDEX IF NOT EXISTS idx_tc_comentario_units_blocked_until
ON tc_comentario_units (status, blocked_until);

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
  leased_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

ALTER TABLE tc_image_assets
ADD COLUMN IF NOT EXISTS leased_until TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_tc_image_assets_status
ON tc_image_assets (status, updated_at);

CREATE TABLE IF NOT EXISTS tc_image_job_assets (
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  image_uuid TEXT NOT NULL REFERENCES tc_image_assets(uuid) ON DELETE CASCADE,
  PRIMARY KEY (job_id, image_uuid)
);

CREATE TABLE IF NOT EXISTS tc_caderno_questoes (
  caderno_id BIGINT NOT NULL,
  questao_id BIGINT NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
  posicao INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (caderno_id, questao_id)
);

CREATE INDEX IF NOT EXISTS idx_tc_caderno_questoes_caderno
ON tc_caderno_questoes (caderno_id, posicao);
"""


@dataclass(frozen=True, slots=True)
class CadernoJob:
    id: int
    caderno_id: int
    expected_total: int | None
    total_units: int
    status: str


async def ensure_ledger_schema(conn: AsyncConnection) -> None:
    # Remove comentários de linha ANTES de splitar: um `;` dentro de um
    # comentário `--` quebraria o split e geraria SQL inválido.
    sql_sem_comentarios = "\n".join(
        line.split("--", 1)[0] for line in LEDGER_DDL.splitlines()
    )
    for stmt in sql_sem_comentarios.split(";"):
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
    ranges = _planned_ranges(expected_total=expected_total, page_size=page_size)
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
                  AND status <> 'cancelled'
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
                      'caderno', 'pending', 'tc', :external_id, :expected_total,
                      :page_size, :requested_by, :total_units, '{}'::jsonb, now()
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
    elif expected_total is not None:
        row = (
            await session.execute(
                text(
                    """
                    UPDATE tc_jobs
                    SET
                      expected_total = :expected_total,
                      page_size = :page_size,
                      total_units = :total_units,
                      requested_by = COALESCE(requested_by, :requested_by),
                      updated_at = now()
                    WHERE id = :job_id
                    RETURNING id, external_id, expected_total, total_units, status
                    """
                ),
                {
                    "job_id": row["id"],
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
                  job_id, caderno_id, inicio, page_size, position_start,
                  position_end, status, updated_at
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
    return await get_caderno_job(session, job_id=job_id)


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


async def refresh_caderno_job_status(session: AsyncSession, *, job_id: int) -> None:
    await refresh_caderno_job_counts(session, job_id=job_id)
    await session.execute(
        text(
            """
            UPDATE tc_jobs j
            SET
              status = CASE
                WHEN j.total_units > 0 AND j.done_units >= j.total_units THEN 'done'
                WHEN EXISTS (
                  SELECT 1 FROM tc_caderno_units u
                  WHERE u.job_id = j.id
                    AND u.status = 'blocked'
                    AND COALESCE(u.blocked_until, now() + interval '1 second') > now()
                ) THEN 'blocked'
                WHEN NOT EXISTS (
                  SELECT 1 FROM tc_caderno_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('pending', 'queued', 'running')
                ) AND j.blocked_units > 0 THEN 'blocked'
                WHEN NOT EXISTS (
                  SELECT 1 FROM tc_caderno_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('pending', 'queued', 'running', 'blocked')
                ) AND j.failed_units > 0 THEN 'failed'
                WHEN EXISTS (
                  SELECT 1 FROM tc_caderno_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('running', 'queued', 'pending', 'failed', 'blocked')
                ) THEN 'running'
                ELSE j.status
              END,
              finished_at = CASE
                WHEN j.total_units > 0 AND j.done_units >= j.total_units THEN now()
                WHEN NOT EXISTS (
                  SELECT 1 FROM tc_caderno_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('pending', 'queued', 'running', 'blocked')
                ) AND j.failed_units > 0 THEN now()
                ELSE j.finished_at
              END,
              updated_at = now()
            WHERE j.id = :job_id
            """
        ),
        {"job_id": job_id},
    )


async def get_caderno_job(session: AsyncSession, *, job_id: int) -> CadernoJob:
    row = (
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
        id=int(row["id"]),
        caderno_id=int(row["external_id"]),
        expected_total=row["expected_total"],
        total_units=int(row["total_units"] or 0),
        status=str(row["status"]),
    )


async def get_next_caderno_unit(
    session: AsyncSession, *, caderno_id: int
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT id, job_id, caderno_id, inicio, page_size, status, attempts, block_reason
                FROM tc_caderno_units
                WHERE caderno_id = :caderno_id
                  AND (
                    status IN ('pending', 'failed')
                    OR (status = 'blocked' AND blocked_until <= now())
                    OR (status = 'running' AND leased_until <= now())
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM tc_caderno_units b
                    WHERE b.caderno_id = tc_caderno_units.caderno_id
                      AND b.status = 'blocked'
                      AND COALESCE(b.blocked_until, now() + interval '1 second') > now()
                      AND b.inicio < tc_caderno_units.inicio
                  )
                ORDER BY inicio
                LIMIT 1
                """
            ),
            {"caderno_id": caderno_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def list_enqueueable_caderno_units(
    session: AsyncSession, *, caderno_id: int, limit: int | None = None
) -> list[dict[str, Any]]:
    limit_sql = "LIMIT :limit" if limit is not None else ""
    params: dict[str, Any] = {"caderno_id": caderno_id}
    if limit is not None:
        params["limit"] = limit
    rows = (
        await session.execute(
            text(
                f"""
                SELECT id, job_id, caderno_id, inicio, page_size, status, attempts, block_reason
                FROM tc_caderno_units
                WHERE caderno_id = :caderno_id
                  AND (
                    status IN ('pending', 'failed')
                    OR (status = 'blocked' AND blocked_until <= now())
                    OR (status = 'running' AND leased_until <= now())
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM tc_caderno_units b
                    WHERE b.caderno_id = tc_caderno_units.caderno_id
                      AND b.status = 'blocked'
                      AND COALESCE(b.blocked_until, now() + interval '1 second') > now()
                      AND b.inicio < tc_caderno_units.inicio
                  )
                ORDER BY inicio
                {limit_sql}
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def lease_caderno_unit(
    session: AsyncSession,
    *,
    caderno_id: int,
    inicio: int,
    page_size: int,
    task_id: str | None,
    lease_seconds: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                UPDATE tc_caderno_units
                SET
                  status = 'running',
                  task_id = :task_id,
                  attempts = attempts + 1,
                  leased_until = now() + (:lease_seconds * interval '1 second'),
                  block_reason = NULL,
                  blocked_until = NULL,
                  last_error = NULL,
                  finished_at = NULL,
                  updated_at = now()
                WHERE caderno_id = :caderno_id
                  AND inicio = :inicio
                  AND page_size = :page_size
                  AND (
                    status IN ('pending', 'queued', 'failed')
                    OR (status = 'blocked' AND COALESCE(blocked_until, now()) <= now())
                    OR (status = 'running' AND leased_until <= now())
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM tc_caderno_units b
                    WHERE b.caderno_id = tc_caderno_units.caderno_id
                      AND b.status = 'blocked'
                      AND COALESCE(b.blocked_until, now() + interval '1 second') > now()
                      AND b.inicio < tc_caderno_units.inicio
                  )
                RETURNING id, job_id, caderno_id, inicio, page_size, attempts, status
                """
            ),
            {
                "caderno_id": caderno_id,
                "inicio": inicio,
                "page_size": page_size,
                "task_id": task_id,
                "lease_seconds": lease_seconds,
            },
        )
    ).mappings().first()
    if row is None:
        return None

    await session.execute(
        text(
            """
            UPDATE tc_jobs
            SET status = 'running', updated_at = now(), finished_at = NULL
            WHERE id = :job_id
              AND status IN ('pending', 'blocked', 'failed')
            """
        ),
        {"job_id": row["job_id"]},
    )
    return dict(row)


async def list_active_caderno_jobs(session: AsyncSession) -> list[CadernoJob]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, external_id, expected_total, total_units, status
                FROM tc_jobs
                WHERE kind = 'caderno'
                  AND status IN ('pending', 'running', 'blocked')
                  AND paused_by_user IS NOT TRUE
                ORDER BY id
                """
            )
        )
    ).mappings().all()
    return [
        CadernoJob(
            id=int(row["id"]),
            caderno_id=int(row["external_id"]),
            expected_total=row["expected_total"],
            total_units=int(row["total_units"] or 0),
            status=str(row["status"]),
        )
        for row in rows
    ]


async def set_caderno_job_paused(
    session: AsyncSession, *, job_id: int, paused: bool
) -> bool:
    """Marca/desmarca pausa manual do job. Retorna True se o job existe."""
    res = await session.execute(
        text(
            """
            UPDATE tc_jobs
            SET paused_by_user = :paused, updated_at = now()
            WHERE id = :job_id
            """
        ),
        {"paused": paused, "job_id": job_id},
    )
    return (res.rowcount or 0) > 0


async def is_caderno_paused(session: AsyncSession, *, caderno_id: int) -> bool:
    """True se o job ativo deste caderno está pausado pelo usuário."""
    row = (
        await session.execute(
            text(
                """
                SELECT paused_by_user
                FROM tc_jobs
                WHERE kind = 'caderno'
                  AND external_id = :cid
                  AND status IN ('pending', 'running', 'blocked')
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"cid": str(caderno_id)},
        )
    ).scalar_one_or_none()
    return bool(row)


async def release_unit_to_pending(session: AsyncSession, *, unit_id: int) -> None:
    """Devolve uma unit em voo pra 'pending' (sem perder progresso) — usado na pausa."""
    await session.execute(
        text(
            """
            UPDATE tc_caderno_units
            SET status = 'pending', leased_until = NULL, task_id = NULL, updated_at = now()
            WHERE id = :unit_id AND status IN ('running', 'queued')
            """
        ),
        {"unit_id": unit_id},
    )


async def is_comentario_paused(session: AsyncSession, *, caderno_id: int) -> bool:
    """True se o job ativo de comentários deste caderno está pausado."""
    row = (
        await session.execute(
            text(
                """
                SELECT paused_by_user FROM tc_jobs
                WHERE kind = 'comentarios' AND external_id = :cid
                  AND status IN ('pending', 'running', 'blocked')
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"cid": str(caderno_id)},
        )
    ).scalar_one_or_none()
    return bool(row)


async def release_comentario_unit_to_pending(session: AsyncSession, *, unit_id: int) -> None:
    """Devolve uma unit de comentários em voo pra 'pending' (sem perder progresso)."""
    await session.execute(
        text(
            """
            UPDATE tc_comentario_units
            SET status = 'pending', leased_until = NULL, task_id = NULL, updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {"unit_id": unit_id},
    )


async def record_caderno_membership(
    session: AsyncSession,
    *,
    caderno_id: int,
    members: list[tuple[int, int]],
) -> None:
    """Registra (questao_pk, posicao) de cada questão dentro do caderno TC.

    Idempotente: re-coleta atualiza a posição. `members` é uma lista de
    `(questao_pk, posicao_1based)`.
    """
    for questao_pk, posicao in members:
        await session.execute(
            text(
                """
                INSERT INTO tc_caderno_questoes (caderno_id, questao_id, posicao)
                VALUES (:caderno_id, :questao_id, :posicao)
                ON CONFLICT (caderno_id, questao_id)
                DO UPDATE SET posicao = EXCLUDED.posicao
                """
            ),
            {"caderno_id": caderno_id, "questao_id": questao_pk, "posicao": posicao},
        )


async def mark_caderno_unit_done(
    session: AsyncSession,
    *,
    unit_id: int,
    job_id: int,
    questoes_ok: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_caderno_units
            SET
              status = 'done',
              questoes_ok = :questoes_ok,
              http_status = NULL,
              block_reason = NULL,
              blocked_until = NULL,
              last_error = NULL,
              leased_until = NULL,
              finished_at = now(),
              updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {"unit_id": unit_id, "questoes_ok": questoes_ok},
    )
    await refresh_caderno_job_status(session, job_id=job_id)


async def mark_caderno_unit_blocked(
    session: AsyncSession,
    *,
    unit_id: int,
    job_id: int,
    reason: str,
    error: str,
    cooldown_seconds: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_caderno_units
            SET
              status = 'blocked',
              block_reason = :reason,
              blocked_until = now() + (:cooldown_seconds * interval '1 second'),
              last_error = :error,
              leased_until = NULL,
              updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {
            "unit_id": unit_id,
            "reason": reason,
            "error": error,
            "cooldown_seconds": cooldown_seconds,
        },
    )
    await refresh_caderno_job_status(session, job_id=job_id)


async def mark_caderno_unit_failed(
    session: AsyncSession,
    *,
    unit_id: int,
    job_id: int,
    error: str,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_caderno_units
            SET
              status = 'failed',
              last_error = :error,
              leased_until = NULL,
              updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {"unit_id": unit_id, "error": error},
    )
    await refresh_caderno_job_status(session, job_id=job_id)


def _planned_ranges(
    *, expected_total: int | None, page_size: int
) -> list[CadernoRange]:
    if expected_total is not None:
        return build_caderno_ranges(expected_total=expected_total, page_size=page_size)
    if page_size <= 0:
        raise ValueError("page_size must be > 0")
    return [
        CadernoRange(
            inicio=0,
            page_size=page_size,
            position_start=1,
            position_end=page_size,
            is_last=False,
        )
    ]


# ---------------------------------------------------------------------------
# Funções de job/unit de comentários (espelham as de caderno acima)
# ---------------------------------------------------------------------------

async def upsert_comentario_job(
    session: AsyncSession,
    *,
    caderno_id: int,
    questao_ids: list[int],
    requested_by: int | None = None,
) -> CadernoJob:
    """Cria/reaproveita job kind='comentarios' e insere uma unit por questão_id."""
    total_units = len(questao_ids)
    external_id = str(caderno_id)

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"tc:comentarios:{external_id}"},
    )

    row = (
        await session.execute(
            text(
                """
                SELECT id, external_id, expected_total, total_units, status
                FROM tc_jobs
                WHERE kind = 'comentarios'
                  AND external_id = :external_id
                  AND status <> 'cancelled'
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
                      'comentarios', 'pending', 'tc', :external_id, NULL,
                      1, :requested_by, :total_units, '{}'::jsonb, now()
                    )
                    RETURNING id, external_id, expected_total, total_units, status
                    """
                ),
                {
                    "external_id": external_id,
                    "requested_by": requested_by,
                    "total_units": total_units,
                },
            )
        ).mappings().one()
    else:
        row = (
            await session.execute(
                text(
                    """
                    UPDATE tc_jobs
                    SET
                      total_units = :total_units,
                      requested_by = COALESCE(requested_by, :requested_by),
                      updated_at = now()
                    WHERE id = :job_id
                    RETURNING id, external_id, expected_total, total_units, status
                    """
                ),
                {
                    "job_id": row["id"],
                    "requested_by": requested_by,
                    "total_units": total_units,
                },
            )
        ).mappings().one()

    job_id = int(row["id"])
    for questao_id in questao_ids:
        await session.execute(
            text(
                """
                INSERT INTO tc_comentario_units (
                  job_id, caderno_id, questao_id, status, updated_at
                )
                VALUES (
                  :job_id, :caderno_id, :questao_id, 'pending', now()
                )
                ON CONFLICT (job_id, questao_id) DO NOTHING
                """
            ),
            {
                "job_id": job_id,
                "caderno_id": caderno_id,
                "questao_id": questao_id,
            },
        )

    await refresh_comentario_job_counts(session, job_id=job_id)
    return await _get_comentario_job(session, job_id=job_id)


async def refresh_comentario_job_counts(session: AsyncSession, *, job_id: int) -> None:
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
              FROM tc_comentario_units
              WHERE job_id = :job_id
              GROUP BY job_id
            ) s
            WHERE j.id = s.job_id
            """
        ),
        {"job_id": job_id},
    )


async def refresh_comentario_job_status(session: AsyncSession, *, job_id: int) -> None:
    await refresh_comentario_job_counts(session, job_id=job_id)
    await session.execute(
        text(
            """
            UPDATE tc_jobs j
            SET
              status = CASE
                WHEN j.total_units > 0 AND j.done_units >= j.total_units THEN 'done'
                WHEN EXISTS (
                  SELECT 1 FROM tc_comentario_units u
                  WHERE u.job_id = j.id
                    AND u.status = 'blocked'
                    AND COALESCE(u.blocked_until, now() + interval '1 second') > now()
                ) THEN 'blocked'
                WHEN NOT EXISTS (
                  SELECT 1 FROM tc_comentario_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('pending', 'queued', 'running')
                ) AND j.blocked_units > 0 THEN 'blocked'
                WHEN NOT EXISTS (
                  SELECT 1 FROM tc_comentario_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('pending', 'queued', 'running', 'blocked')
                ) AND j.failed_units > 0 THEN 'failed'
                WHEN EXISTS (
                  SELECT 1 FROM tc_comentario_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('running', 'queued', 'pending', 'failed', 'blocked')
                ) THEN 'running'
                ELSE j.status
              END,
              finished_at = CASE
                WHEN j.total_units > 0 AND j.done_units >= j.total_units THEN now()
                WHEN NOT EXISTS (
                  SELECT 1 FROM tc_comentario_units u
                  WHERE u.job_id = j.id
                    AND u.status IN ('pending', 'queued', 'running', 'blocked')
                ) AND j.failed_units > 0 THEN now()
                ELSE j.finished_at
              END,
              updated_at = now()
            WHERE j.id = :job_id
            """
        ),
        {"job_id": job_id},
    )


async def _get_comentario_job(session: AsyncSession, *, job_id: int) -> CadernoJob:
    row = (
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
        id=int(row["id"]),
        caderno_id=int(row["external_id"]),
        expected_total=row["expected_total"],
        total_units=int(row["total_units"] or 0),
        status=str(row["status"]),
    )


async def list_enqueueable_comentario_units(
    session: AsyncSession, *, caderno_id: int, limit: int | None = None
) -> list[dict[str, Any]]:
    limit_sql = "LIMIT :limit" if limit is not None else ""
    params: dict[str, Any] = {"caderno_id": caderno_id}
    if limit is not None:
        params["limit"] = limit
    rows = (
        await session.execute(
            text(
                f"""
                SELECT id AS unit_id, job_id, caderno_id, questao_id, status, attempts, block_reason
                FROM tc_comentario_units
                WHERE caderno_id = :caderno_id
                  AND (
                    status IN ('pending', 'failed')
                    OR (status = 'blocked' AND blocked_until <= now())
                    OR (status = 'running' AND leased_until < now())
                  )
                ORDER BY questao_id
                {limit_sql}
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def lease_comentario_unit(
    session: AsyncSession,
    *,
    caderno_id: int,
    questao_id: int,
    ack_wait_seconds: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                UPDATE tc_comentario_units
                SET
                  status = 'running',
                  attempts = attempts + 1,
                  leased_until = now() + (:ack_wait_seconds * interval '1 second'),
                  block_reason = NULL,
                  blocked_until = NULL,
                  last_error = NULL,
                  finished_at = NULL,
                  updated_at = now()
                WHERE caderno_id = :caderno_id
                  AND questao_id = :questao_id
                  AND (
                    status IN ('pending', 'queued', 'failed')
                    OR (status = 'blocked' AND COALESCE(blocked_until, now()) <= now())
                    OR (status = 'running' AND leased_until <= now())
                  )
                RETURNING id AS unit_id, job_id, caderno_id, questao_id, attempts, status
                """
            ),
            {
                "caderno_id": caderno_id,
                "questao_id": questao_id,
                "ack_wait_seconds": ack_wait_seconds,
            },
        )
    ).mappings().first()
    if row is None:
        return None

    await session.execute(
        text(
            """
            UPDATE tc_jobs
            SET status = 'running', updated_at = now(), finished_at = NULL
            WHERE id = :job_id
              AND status IN ('pending', 'blocked', 'failed')
            """
        ),
        {"job_id": row["job_id"]},
    )
    return dict(row)


async def mark_comentario_unit_done(
    session: AsyncSession,
    *,
    unit_id: int,
    job_id: int,
    coments_alunos: int,
    coments_professores: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_comentario_units
            SET
              status = 'done',
              coments_alunos = :coments_alunos,
              coments_professores = :coments_professores,
              http_status = NULL,
              block_reason = NULL,
              blocked_until = NULL,
              last_error = NULL,
              leased_until = NULL,
              finished_at = now(),
              updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {
            "unit_id": unit_id,
            "coments_alunos": coments_alunos,
            "coments_professores": coments_professores,
        },
    )
    await refresh_comentario_job_status(session, job_id=job_id)


async def mark_comentario_unit_blocked(
    session: AsyncSession,
    *,
    unit_id: int,
    job_id: int,
    reason: str,
    blocked_until: Any,
    http_status: int | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_comentario_units
            SET
              status = 'blocked',
              block_reason = :reason,
              blocked_until = :blocked_until,
              http_status = :http_status,
              leased_until = NULL,
              updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {
            "unit_id": unit_id,
            "reason": reason,
            "blocked_until": blocked_until,
            "http_status": http_status,
        },
    )
    await refresh_comentario_job_status(session, job_id=job_id)


async def mark_comentario_unit_failed(
    session: AsyncSession,
    *,
    unit_id: int,
    job_id: int,
    error: str,
    http_status: int | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_comentario_units
            SET
              status = 'failed',
              last_error = :error,
              http_status = :http_status,
              leased_until = NULL,
              updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {"unit_id": unit_id, "error": error, "http_status": http_status},
    )
    await refresh_comentario_job_status(session, job_id=job_id)


async def list_active_comentario_jobs(session: AsyncSession) -> list[CadernoJob]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, external_id, expected_total, total_units, status
                FROM tc_jobs
                WHERE kind = 'comentarios'
                  AND status IN ('pending', 'running', 'blocked')
                  AND paused_by_user IS NOT TRUE
                ORDER BY id
                """
            )
        )
    ).mappings().all()
    return [
        CadernoJob(
            id=int(row["id"]),
            caderno_id=int(row["external_id"]),
            expected_total=row["expected_total"],
            total_units=int(row["total_units"] or 0),
            status=str(row["status"]),
        )
        for row in rows
    ]
