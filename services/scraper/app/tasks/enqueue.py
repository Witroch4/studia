from __future__ import annotations

from typing import Any, Literal

from taskiq.task import AsyncTaskiqTask

from app.tasks.brokers.studia import (
    broker_studia_default,
    broker_studia_low,
    build_default_broker,
    build_low_broker,
)
from app.tasks.idempotency import IDEMPOTENCY_KEY_LABEL, get_idempotency_store

Priority = Literal["default", "low"]
_STARTED_BROKERS: set[int] = set()


def _resolve_broker(priority: Priority, *, isolated: bool = False):
    if priority == "default":
        return build_default_broker() if isolated else broker_studia_default
    if priority == "low":
        return build_low_broker() if isolated else broker_studia_low
    raise ValueError(f"Unsupported priority: {priority}")


async def enqueue(
    task: Any,
    *,
    priority: Priority = "default",
    labels: dict[str, Any] | None = None,
    isolated_broker: bool = False,
    **kwargs: Any,
) -> Any:
    broker = _resolve_broker(priority, isolated=isolated_broker)
    try:
        if isolated_broker:
            await broker.startup()
        else:
            await _ensure_broker_started(broker)
        kicker = task.kicker().with_broker(broker)

        if labels:
            kicker.labels.update(labels)

        idempotency_key = kicker.labels.get(IDEMPOTENCY_KEY_LABEL)
        if isinstance(idempotency_key, str) and idempotency_key.strip():
            task_id = broker.id_generator()
            claim = await get_idempotency_store().claim(
                idempotency_key=idempotency_key,
                task_id=task_id,
            )
            if not claim.claimed:
                return AsyncTaskiqTask(
                    task_id=claim.task_id,
                    result_backend=broker.result_backend,
                    return_type=task.return_type,
                )
            kicker = kicker.with_task_id(claim.task_id)

        return await kicker.kiq(**kwargs)
    finally:
        if isolated_broker:
            await broker.shutdown()


async def _ensure_broker_started(broker: Any) -> None:
    broker_id = id(broker)
    if broker_id in _STARTED_BROKERS:
        return
    await broker.startup()
    _STARTED_BROKERS.add(broker_id)
