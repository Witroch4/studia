from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import httpx
from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.observability import get_logger
from app.tasks.brokers.studia import broker_studia_low
from app.tasks.enqueue import enqueue
from app.tasks.ledger import ensure_ledger_schema

log = get_logger(__name__)
_PUBLIC_POLICY_BUCKETS: set[str] = set()

TC_IMAGE_URL_SQL_PATTERN = (
    r"https?://(?:cdn\.tecconcursos\.com\.br/figuras|"
    r"s3-sa-east-1\.amazonaws\.com/figuras\.tecconcursos\.com\.br)/[a-f0-9-]+"
)

URL_PATTERN = re.compile(TC_IMAGE_URL_SQL_PATTERN, re.I)


@dataclass(frozen=True, slots=True)
class ImageTaskResult:
    status: str
    uuid: str
    bytes: int = 0
    minio_url: str | None = None
    error: str | None = None
    enqueued_next_uuid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def discover_image_urls(session: AsyncSession) -> set[str]:
    result = await session.execute(
        text(
            """
            SELECT DISTINCT m FROM (
              SELECT (regexp_matches(enunciado_html, :pattern, 'g'))[1] AS m
              FROM questoes WHERE enunciado_html LIKE '%tecconcursos.com.br%'
              UNION
              SELECT (regexp_matches(enunciado_md, :pattern, 'g'))[1] AS m
              FROM questoes WHERE enunciado_md LIKE '%tecconcursos.com.br%'
              UNION
              SELECT (regexp_matches(texto_html, :pattern, 'g'))[1] AS m
              FROM alternativas WHERE texto_html LIKE '%tecconcursos.com.br%'
              UNION
              SELECT (regexp_matches(texto_md, :pattern, 'g'))[1] AS m
              FROM alternativas WHERE texto_md LIKE '%tecconcursos.com.br%'
            ) t WHERE m IS NOT NULL
            """
        ),
        {"pattern": TC_IMAGE_URL_SQL_PATTERN},
    )
    return {row[0] for row in result.fetchall()}


async def upsert_image_assets(session: AsyncSession, urls: set[str]) -> int:
    count = 0
    for url in urls:
        uuid = uuid_from_url(url)
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO tc_image_assets (uuid, source_url, status, updated_at)
                    VALUES (:uuid, :source_url, 'pending', now())
                    ON CONFLICT (uuid) DO UPDATE
                    SET source_url = EXCLUDED.source_url,
                        updated_at = CASE
                          WHEN tc_image_assets.source_url IS DISTINCT FROM EXCLUDED.source_url
                          THEN now()
                          ELSE tc_image_assets.updated_at
                        END
                    RETURNING status, minio_url
                    """
                ),
                {"uuid": uuid, "source_url": url},
            )
        ).mappings().one()
        if row["status"] == "done" and row["minio_url"]:
            await _rewrite_single_url(session, source_url=url, minio_url=row["minio_url"])
        count += 1
    return count


async def list_enqueueable_image_assets(
    session: AsyncSession, *, limit: int
) -> list[dict[str, Any]]:
    settings = get_settings()
    rows = (
        await session.execute(
            text(
                """
                SELECT uuid, source_url, attempts
                FROM tc_image_assets
                WHERE status IN ('pending', 'failed')
                   OR (
                     status = 'queued'
                     AND updated_at <= now() - (:stale_seconds * interval '1 second')
                   )
                   OR (status = 'running' AND leased_until <= now())
                ORDER BY updated_at, uuid
                LIMIT :limit
                """
            ),
            {
                "limit": limit,
                "stale_seconds": settings.taskiq_studia_requeue_stale_seconds,
            },
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def count_active_image_assets(session: AsyncSession) -> int:
    settings = get_settings()
    value = (
        await session.execute(
            text(
                """
                SELECT count(*)
                FROM tc_image_assets
                WHERE (
                    status = 'queued'
                    AND updated_at > now() - (:stale_seconds * interval '1 second')
                  )
                  OR (
                    status = 'running'
                    AND COALESCE(leased_until, now()) > now()
                  )
                """
            ),
            {"stale_seconds": settings.taskiq_studia_requeue_stale_seconds},
        )
    ).scalar_one()
    return int(value or 0)


async def claim_enqueueable_image_assets(
    session: AsyncSession, *, limit: int
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    settings = get_settings()
    rows = (
        await session.execute(
            text(
                """
                WITH picked AS (
                  SELECT uuid
                  FROM tc_image_assets
                  WHERE status IN ('pending', 'failed')
                     OR (
                       status = 'queued'
                       AND updated_at <= now() - (:stale_seconds * interval '1 second')
                     )
                     OR (status = 'running' AND leased_until <= now())
                  ORDER BY updated_at, uuid
                  LIMIT :limit
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE tc_image_assets asset
                SET status = 'queued',
                    task_id = NULL,
                    updated_at = now()
                FROM picked
                WHERE asset.uuid = picked.uuid
                RETURNING asset.uuid, asset.source_url, asset.attempts
                """
            ),
            {
                "limit": limit,
                "stale_seconds": settings.taskiq_studia_requeue_stale_seconds,
            },
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def mark_image_asset_queued(
    session: AsyncSession, *, uuid: str, task_id: str | None
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_image_assets
            SET status = 'queued',
                task_id = :task_id,
                updated_at = now()
            WHERE uuid = :uuid
              AND status IN ('pending', 'queued', 'failed')
            """
        ),
        {"uuid": uuid, "task_id": task_id},
    )


async def enqueue_image_assets_to_target(
    session_factory: async_sessionmaker,
    *,
    target_active: int | None = None,
    limit: int | None = None,
) -> int:
    settings = get_settings()
    target = max(target_active or settings.taskiq_studia_image_target_active, 0)
    if target <= 0:
        return 0

    async with session_factory.begin() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('tc_image_assets_enqueue'))")
        )
        active = await count_active_image_assets(session)
        budget = max(target - active, 0)
        if limit is not None:
            budget = min(budget, max(limit, 0))
        assets = await claim_enqueueable_image_assets(session, limit=budget)

    enqueued = 0
    for asset in assets:
        task = await enqueue(
            baixar_imagem_tc,
            priority="low",
            isolated_broker=True,
            uuid=asset["uuid"],
        )
        async with session_factory.begin() as session:
            await mark_image_asset_queued(
                session,
                uuid=asset["uuid"],
                task_id=getattr(task, "task_id", None),
            )
        enqueued += 1
    return enqueued


async def enqueue_next_image_asset(
    session_factory: async_sessionmaker, *, limit: int = 1
) -> int:
    return await enqueue_image_assets_to_target(
        session_factory,
        target_active=limit,
        limit=limit,
    )


async def fill_image_asset_queue(session_factory: async_sessionmaker) -> int:
    return await enqueue_image_assets_to_target(session_factory)


@broker_studia_low.task
async def baixar_imagem_tc(uuid: str) -> dict[str, Any]:
    log.info("image.task_received", uuid=uuid)
    result = await execute_image_asset_unit(uuid=uuid)
    return result.to_dict()


async def execute_image_asset_unit(
    *,
    uuid: str,
    chain_next: bool = True,
) -> ImageTaskResult:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            asset = await _lease_image_asset(session, uuid=uuid)
        if asset is None:
            return ImageTaskResult(status="skipped", uuid=uuid)

        try:
            downloaded = await _download_image(asset["source_url"])
            minio_url = await _put_minio(
                uuid=uuid,
                content=downloaded["content"],
                content_type=downloaded["content_type"],
            )
            object_key = minio_object_key(uuid, downloaded["content_type"])
            async with Session.begin() as session:
                await _mark_image_done(
                    session,
                    uuid=uuid,
                    minio_url=minio_url,
                    object_key=object_key,
                    content_type=downloaded["content_type"],
                    bytes_len=len(downloaded["content"]),
                )
                await _rewrite_single_url(
                    session,
                    source_url=asset["source_url"],
                    minio_url=minio_url,
                )

            enqueued_next_uuid = None
            if chain_next:
                try:
                    await fill_image_asset_queue(Session)
                except Exception as exc:  # noqa: BLE001
                    log.error("image.chain_enqueue_failed", uuid=uuid, err=str(exc))

            log.info(
                "image.done",
                uuid=uuid,
                bytes=len(downloaded["content"]),
                minio_url=minio_url,
            )
            return ImageTaskResult(
                status="done",
                uuid=uuid,
                bytes=len(downloaded["content"]),
                minio_url=minio_url,
                enqueued_next_uuid=enqueued_next_uuid,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            terminal_status = "not_found" if status_code == 404 else "failed"
            async with Session.begin() as session:
                await _mark_image_failed(
                    session,
                    uuid=uuid,
                    status=terminal_status,
                    http_status=status_code,
                    error=str(exc),
                )
            return ImageTaskResult(status=terminal_status, uuid=uuid, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            async with Session.begin() as session:
                await _mark_image_failed(
                    session,
                    uuid=uuid,
                    status="failed",
                    http_status=None,
                    error=str(exc),
                )
            return ImageTaskResult(status="failed", uuid=uuid, error=str(exc))
    finally:
        await engine.dispose()


async def _lease_image_asset(
    session: AsyncSession, *, uuid: str
) -> dict[str, Any] | None:
    settings = get_settings()
    row = (
        await session.execute(
            text(
                """
                UPDATE tc_image_assets
                SET status = 'running',
                    attempts = attempts + 1,
                    leased_until = now() + (:lease_seconds * interval '1 second'),
                    last_error = NULL,
                    updated_at = now()
                WHERE uuid = :uuid
                  AND (
                    status IN ('pending', 'queued', 'failed')
                    OR (status = 'running' AND leased_until <= now())
                  )
                RETURNING uuid, source_url, attempts
                """
            ),
            {
                "uuid": uuid,
                "lease_seconds": settings.taskiq_studia_ack_wait_seconds,
            },
        )
    ).mappings().first()
    return dict(row) if row else None


async def _download_image(source_url: str) -> dict[str, Any]:
    settings = get_settings()
    kwargs: dict[str, Any] = {"http2": True, "follow_redirects": True, "timeout": 30.0}
    if settings.residential_proxy_url:
        kwargs["proxy"] = settings.residential_proxy_url
    async with httpx.AsyncClient(**kwargs) as client:
        response = await client.get(source_url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
    return {"content": response.content, "content_type": content_type}


async def _put_minio(*, uuid: str, content: bytes, content_type: str) -> str:
    settings = get_settings()
    minio_endpoint = _env("MINIO_ENDPOINT", "minio:9000")
    access_key = _env("MINIO_ACCESS_KEY", "witalo")
    secret_key = _env("MINIO_SECRET_KEY", "")
    bucket = _env("MINIO_BUCKET", "studia")
    secure = _env("MINIO_SECURE", "false").lower() == "true"
    client = Minio(
        minio_endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )
    if not await _to_thread(client.bucket_exists, bucket):
        await _to_thread(client.make_bucket, bucket)
    await _ensure_public_figuras_policy(client, bucket)
    object_key = minio_object_key(uuid, content_type)
    await _to_thread(
        client.put_object,
        bucket,
        object_key,
        BytesIO(content),
        len(content),
        content_type=content_type,
    )
    public_url = _env("MINIO_PUBLIC_URL", "https://objstoreapi.witdev.com.br")
    return f"{public_url}/{bucket}/{object_key}"


async def _ensure_public_figuras_policy(client: Minio, bucket: str) -> None:
    if bucket in _PUBLIC_POLICY_BUCKETS:
        return
    await _to_thread(
        client.set_bucket_policy,
        bucket,
        json.dumps(public_figuras_policy(bucket)),
    )
    _PUBLIC_POLICY_BUCKETS.add(bucket)
    log.info("minio.policy_set", bucket=bucket, prefix="figuras/")


def public_figuras_policy(bucket: str) -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/figuras/*"],
            }
        ],
    }


async def _mark_image_done(
    session: AsyncSession,
    *,
    uuid: str,
    minio_url: str,
    object_key: str,
    content_type: str,
    bytes_len: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_image_assets
            SET status = 'done',
                minio_url = :minio_url,
                minio_object_key = :object_key,
                content_type = :content_type,
                bytes = :bytes_len,
                http_status = 200,
                last_error = NULL,
                leased_until = NULL,
                finished_at = now(),
                updated_at = now()
            WHERE uuid = :uuid
            """
        ),
        {
            "uuid": uuid,
            "minio_url": minio_url,
            "object_key": object_key,
            "content_type": content_type,
            "bytes_len": bytes_len,
        },
    )


async def _mark_image_failed(
    session: AsyncSession,
    *,
    uuid: str,
    status: str,
    http_status: int | None,
    error: str,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tc_image_assets
            SET status = :status,
                http_status = :http_status,
                last_error = :error,
                leased_until = NULL,
                updated_at = now()
            WHERE uuid = :uuid
            """
        ),
        {
            "uuid": uuid,
            "status": status,
            "http_status": http_status,
            "error": error,
        },
    )


async def _rewrite_single_url(
    session: AsyncSession, *, source_url: str, minio_url: str
) -> None:
    for table, column in [
        ("questoes", "enunciado_html"),
        ("questoes", "enunciado_md"),
        ("alternativas", "texto_html"),
        ("alternativas", "texto_md"),
    ]:
        await session.execute(
            text(
                f"""
                UPDATE {table}
                SET {column} = REPLACE({column}, :source_url, :minio_url)
                WHERE {column} LIKE '%' || :source_url || '%'
                """
            ),
            {"source_url": source_url, "minio_url": minio_url},
        )


def uuid_from_url(url: str) -> str:
    return urlparse(url).path.rsplit("/", 1)[-1]


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


def _env(key: str, default: str) -> str:
    import os

    return os.environ.get(key) or default


async def _to_thread(func, *args, **kwargs):
    import asyncio

    return await asyncio.to_thread(func, *args, **kwargs)
