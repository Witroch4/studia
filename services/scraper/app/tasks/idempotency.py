from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from redis.asyncio import Redis

from app.config import get_settings

IDEMPOTENCY_KEY_LABEL = "idempotency_key"
IDEMPOTENCY_NAMESPACE = "studia:taskiq:idempotency"


def build_idempotency_key(prefix: str, *parts: object) -> str:
    payload = json.dumps(
        [prefix, *parts],
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
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

    async def claim(
        self, *, idempotency_key: str, task_id: str
    ) -> IdempotencyClaim:
        redis_key = f"{IDEMPOTENCY_NAMESPACE}:{idempotency_key}"
        claimed = await self.redis.set(
            redis_key,
            task_id,
            ex=max(1, self.ttl_seconds),
            nx=True,
        )
        if claimed:
            return IdempotencyClaim(
                task_id=task_id, claimed=True, redis_key=redis_key
            )

        existing = await self.redis.get(redis_key)
        return IdempotencyClaim(
            task_id=str(existing or task_id),
            claimed=False,
            redis_key=redis_key,
        )


_store: IdempotencyStore | None = None


def get_idempotency_store() -> IdempotencyStore:
    global _store
    if _store is None:
        settings = get_settings()
        redis = Redis.from_url(
            settings.taskiq_idempotency_redis_url,
            decode_responses=True,
        )
        _store = IdempotencyStore(
            redis,
            ttl_seconds=settings.taskiq_idempotency_ttl_seconds,
        )
    return _store
