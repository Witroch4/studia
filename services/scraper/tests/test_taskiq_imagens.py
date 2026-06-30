from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)

from app.tasks.imagens import (  # noqa: E402
    count_active_image_assets,
    enqueue_image_assets_to_target,
    discover_image_urls,
    execute_image_asset_unit,
    list_enqueueable_image_assets,
    minio_object_key,
    public_figuras_policy,
    upsert_image_assets,
    uuid_from_url,
)
from app.tasks.ledger import ensure_ledger_schema  # noqa: E402


@pytest.mark.asyncio
async def test_image_asset_discovery_and_upsert(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL)
    uuid = "11111111-2222-3333-4444-555555555555"
    url = f"https://cdn.tecconcursos.com.br/figuras/{uuid}"
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(text("DELETE FROM tc_image_assets WHERE uuid = :uuid"), {"uuid": uuid})
            await conn.execute(
                text(
                    """
                    INSERT INTO questoes (id_externo, enunciado_html, status)
                    VALUES (:id_externo, :html, 'ATIVA')
                    ON CONFLICT (id_externo) DO UPDATE
                    SET enunciado_html = EXCLUDED.enunciado_html
                    """
                ),
                {"id_externo": 990000001, "html": f"<img src=\"{url}\">"},
            )

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            urls = await discover_image_urls(session)
            assert url in urls
            await upsert_image_assets(session, {url})
            assets = await list_enqueueable_image_assets(session, limit=10)

        assert any(asset["uuid"] == uuid for asset in assets)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_image_asset_discovery_accepts_s3_figuras_bucket(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL)
    uuid = "fb576b90-a932-4a95-b152-7e82a67d0513"
    url = f"https://s3-sa-east-1.amazonaws.com/figuras.tecconcursos.com.br/{uuid}"
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(text("DELETE FROM tc_image_assets WHERE uuid = :uuid"), {"uuid": uuid})
            await conn.execute(
                text(
                    """
                    INSERT INTO questoes (id_externo, enunciado_html, status)
                    VALUES (:id_externo, :html, 'ATIVA')
                    ON CONFLICT (id_externo) DO UPDATE
                    SET enunciado_html = EXCLUDED.enunciado_html
                    """
                ),
                {"id_externo": 990000011, "html": f"<img src=\"{url}\">"},
            )

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            urls = await discover_image_urls(session)
            assert url in urls
            await upsert_image_assets(session, {url})
            assets = await list_enqueueable_image_assets(session, limit=10)

        assert any(asset["uuid"] == uuid for asset in assets)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_image_asset_upsert_rewrites_s3_url_when_uuid_already_done(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL)
    uuid = "abababab-bbbb-cccc-dddd-eeeeeeeeeeee"
    cdn_url = f"https://cdn.tecconcursos.com.br/figuras/{uuid}"
    s3_url = f"https://s3-sa-east-1.amazonaws.com/figuras.tecconcursos.com.br/{uuid}"
    minio_url = f"https://objstoreapi.witdev.com.br/studia/figuras/{uuid}.png"
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(text("DELETE FROM tc_image_assets WHERE uuid = :uuid"), {"uuid": uuid})
            await conn.execute(
                text(
                    """
                    INSERT INTO tc_image_assets (uuid, source_url, status, minio_url)
                    VALUES (:uuid, :source_url, 'done', :minio_url)
                    """
                ),
                {"uuid": uuid, "source_url": cdn_url, "minio_url": minio_url},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO questoes (id_externo, enunciado_html, status)
                    VALUES (:id_externo, :html, 'ATIVA')
                    ON CONFLICT (id_externo) DO UPDATE
                    SET enunciado_html = EXCLUDED.enunciado_html
                    """
                ),
                {"id_externo": 990000012, "html": f"<img src=\"{s3_url}\">"},
            )

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            await upsert_image_assets(session, {s3_url})
            assets = await list_enqueueable_image_assets(session, limit=10)

        async with engine.connect() as conn:
            html = (
                await conn.execute(
                    text("SELECT enunciado_html FROM questoes WHERE id_externo = 990000012")
                )
            ).scalar_one()

        assert minio_url in html
        assert s3_url not in html
        assert uuid not in {asset["uuid"] for asset in assets}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_execute_image_asset_unit_marks_done_and_rewrites(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    source_url = f"https://cdn.tecconcursos.com.br/figuras/{uuid}"
    minio_url = f"https://objstoreapi.witdev.com.br/studia/figuras/{uuid}.png"
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(text("DELETE FROM tc_image_assets WHERE uuid = :uuid"), {"uuid": uuid})
            await conn.execute(
                text(
                    """
                    INSERT INTO tc_image_assets (uuid, source_url, status)
                    VALUES (:uuid, :source_url, 'pending')
                    """
                ),
                {"uuid": uuid, "source_url": source_url},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO questoes (id_externo, enunciado_html, status)
                    VALUES (:id_externo, :html, 'ATIVA')
                    ON CONFLICT (id_externo) DO UPDATE
                    SET enunciado_html = EXCLUDED.enunciado_html
                    """
                ),
                {"id_externo": 990000002, "html": f"<img src=\"{source_url}\">"},
            )
    finally:
        await engine.dispose()

    import app.tasks.imagens as image_tasks

    async def fake_download(url: str):
        assert url == source_url
        return {"content": b"png-bytes", "content_type": "image/png"}

    async def fake_put_minio(*, uuid: str, content: bytes, content_type: str):
        assert content == b"png-bytes"
        assert content_type == "image/png"
        return minio_url

    monkeypatch.setattr(image_tasks, "_download_image", fake_download)
    monkeypatch.setattr(image_tasks, "_put_minio", fake_put_minio)

    result = await execute_image_asset_unit(uuid=uuid, chain_next=False)

    assert result.status == "done"
    assert result.minio_url == minio_url

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
                        SELECT status, minio_url, minio_object_key, bytes
                        FROM tc_image_assets
                        WHERE uuid = :uuid
                        """
                    ),
                    {"uuid": uuid},
                )
            ).mappings().one()
            html = (
                await conn.execute(
                    text("SELECT enunciado_html FROM questoes WHERE id_externo = 990000002")
                )
            ).scalar_one()
        assert row["status"] == "done"
        assert row["minio_url"] == minio_url
        assert row["minio_object_key"] == f"figuras/{uuid}.png"
        assert row["bytes"] == len(b"png-bytes")
        assert minio_url in html
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_image_assets_to_target_only_fills_delta(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    uuids = [
        "dddddddd-dddd-dddd-dddd-dddddddddd01",
        "dddddddd-dddd-dddd-dddd-dddddddddd02",
        "dddddddd-dddd-dddd-dddd-dddddddddd03",
        "dddddddd-dddd-dddd-dddd-dddddddddd04",
    ]
    active_uuid = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(text("DELETE FROM tc_image_assets"))
            for uuid in uuids:
                await conn.execute(
                    text(
                        """
                        INSERT INTO tc_image_assets (uuid, source_url, status)
                        VALUES (:uuid, :source_url, 'pending')
                        """
                    ),
                    {
                        "uuid": uuid,
                        "source_url": f"https://cdn.tecconcursos.com.br/figuras/{uuid}",
                    },
                )
            await conn.execute(
                text(
                    """
                    INSERT INTO tc_image_assets (uuid, source_url, status, updated_at)
                    VALUES (:uuid, :source_url, 'queued', now())
                    """
                ),
                {
                    "uuid": active_uuid,
                    "source_url": f"https://cdn.tecconcursos.com.br/figuras/{active_uuid}",
                },
            )

        import app.tasks.imagens as image_tasks

        published: list[str] = []

        class FakeTask:
            task_id = "fake-task"

        async def fake_enqueue(task, **kwargs):
            published.append(kwargs["uuid"])
            return FakeTask()

        monkeypatch.setattr(image_tasks, "enqueue", fake_enqueue)

        Session = async_sessionmaker(engine, expire_on_commit=False)
        enqueued = await enqueue_image_assets_to_target(
            Session,
            target_active=3,
            limit=10,
        )

        async with Session.begin() as session:
            active = await count_active_image_assets(session)
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT uuid, status, task_id
                        FROM tc_image_assets
                        WHERE uuid = ANY(:uuids)
                        ORDER BY uuid
                        """
                    ),
                    {"uuids": [*uuids, active_uuid]},
                )
            ).mappings().all()

        assert enqueued == 2
        assert len(published) == 2
        assert active == 3
        queued_with_task = [
            row for row in rows if str(row["uuid"]) in published and row["status"] == "queued"
        ]
        assert len(queued_with_task) == 2
        assert all(row["task_id"] == "fake-task" for row in queued_with_task)
    finally:
        await engine.dispose()


def test_image_url_helpers():
    uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert uuid_from_url(f"https://cdn.tecconcursos.com.br/figuras/{uuid}") == uuid
    assert uuid_from_url(f"https://s3-sa-east-1.amazonaws.com/figuras.tecconcursos.com.br/{uuid}") == uuid
    assert minio_object_key(uuid, "image/png") == f"figuras/{uuid}.png"
    assert public_figuras_policy("studia")["Statement"][0]["Resource"] == [
        "arn:aws:s3:::studia/figuras/*"
    ]


@pytest.mark.asyncio
async def test_list_enqueueable_image_assets_recovers_stale_queued(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    fresh_uuid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    stale_uuid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            await conn.execute(
                text("DELETE FROM tc_image_assets WHERE uuid IN (:fresh_uuid, :stale_uuid)"),
                {"fresh_uuid": fresh_uuid, "stale_uuid": stale_uuid},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO tc_image_assets (uuid, source_url, status, updated_at)
                    VALUES
                      (:fresh_uuid, :fresh_url, 'queued', now()),
                      (:stale_uuid, :stale_url, 'queued', now() - interval '5 minutes')
                    """
                ),
                {
                    "fresh_uuid": fresh_uuid,
                    "fresh_url": f"https://cdn.tecconcursos.com.br/figuras/{fresh_uuid}",
                    "stale_uuid": stale_uuid,
                    "stale_url": f"https://cdn.tecconcursos.com.br/figuras/{stale_uuid}",
                },
            )

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            await upsert_image_assets(
                session,
                {
                    f"https://cdn.tecconcursos.com.br/figuras/{fresh_uuid}",
                    f"https://cdn.tecconcursos.com.br/figuras/{stale_uuid}",
                },
            )
            assets = await list_enqueueable_image_assets(session, limit=10)

        uuids = {asset["uuid"] for asset in assets}
        assert stale_uuid in uuids
        assert fresh_uuid not in uuids
    finally:
        await engine.dispose()
