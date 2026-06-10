from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.tasks.dummy import taskiq_dummy_ping
from app.tasks.enqueue import enqueue
from app.tasks.idempotency import build_idempotency_key
from app.tasks.ledger import (
    ensure_ledger_schema,
    get_next_caderno_unit,
    upsert_caderno_job,
)


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
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
            print(
                {
                    "job_id": job.id,
                    "total_units": job.total_units,
                    "next_inicio": unit["inicio"] if unit else None,
                }
            )

        marker = str(uuid.uuid4())
        task = await enqueue(
            taskiq_dummy_ping,
            priority="default",
            labels={"idempotency_key": build_idempotency_key("dummy", marker)},
            marker=marker,
        )
        print({"task_id": task.task_id, "marker": marker})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
