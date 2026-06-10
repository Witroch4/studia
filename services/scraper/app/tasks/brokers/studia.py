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


def _build_broker(
    *,
    subject: str,
    durable: str,
    pull_batch: int,
    max_ack_pending: int,
) -> PullBasedJetStreamBroker:
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


def build_default_broker() -> PullBasedJetStreamBroker:
    settings = get_settings()
    return _build_broker(
        subject=settings.taskiq_studia_default_subject,
        durable=settings.taskiq_studia_default_durable,
        pull_batch=settings.taskiq_studia_default_pull_batch,
        max_ack_pending=settings.taskiq_studia_default_max_ack_pending,
    )


def build_low_broker() -> PullBasedJetStreamBroker:
    settings = get_settings()
    return _build_broker(
        subject=settings.taskiq_studia_low_subject,
        durable=settings.taskiq_studia_low_durable,
        pull_batch=settings.taskiq_studia_low_pull_batch,
        max_ack_pending=settings.taskiq_studia_low_max_ack_pending,
    )


settings = get_settings()

broker_studia_default = build_default_broker()

broker_studia_low = build_low_broker()
