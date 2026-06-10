from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine

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
