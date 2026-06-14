"""Config do broker NATS do worker do backend — sem conectar no NATS.

build_broker() só constrói o objeto (a conexão acontece em startup()),
então estes testes rodam sem um NATS de verdade.
"""
import pytest
from taskiq_nats import PullBasedJetStreamBroker
from taskiq_redis import RedisAsyncResultBackend

import worker
from worker import load_broker_config, build_broker


_ENV_KEYS = [
    "NATS_SERVERS",
    "TASKIQ_RESULT_REDIS_URL",
    "TASKIQ_STUDIA_BACKEND_STREAM",
    "TASKIQ_STUDIA_BACKEND_SUBJECT",
    "TASKIQ_STUDIA_BACKEND_DURABLE",
    "TASKIQ_STUDIA_BACKEND_PULL_BATCH",
    "TASKIQ_STUDIA_BACKEND_MAX_ACK_PENDING",
    "TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS",
    "TASKIQ_STUDIA_BACKEND_MAX_DELIVER",
]


def test_config_defaults(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    cfg = load_broker_config()
    assert cfg.nats_servers == ["nats://nats:4222"]
    assert cfg.result_redis_url == "redis://redis:6379/2"
    assert cfg.stream == "TASKIQ_STUDIA_BACKEND"
    assert cfg.subject == "taskiq.studia.backend"
    assert cfg.durable == "studia-backend-workers"
    assert cfg.pull_batch == 1
    assert cfg.max_ack_pending == 1
    assert cfg.ack_wait_seconds == 3600
    assert cfg.max_deliver == 3


def test_config_subject_nao_colide_com_scraper():
    # O scraper detém taskiq.studia.default / taskiq.studia.low no stream TASKIQ_STUDIA.
    cfg = load_broker_config()
    assert cfg.subject not in {"taskiq.studia.default", "taskiq.studia.low"}
    assert cfg.stream != "TASKIQ_STUDIA"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("NATS_SERVERS", "nats://a:4222, nats://b:4222")
    monkeypatch.setenv("TASKIQ_RESULT_REDIS_URL", "redis://r:6379/5")
    monkeypatch.setenv("TASKIQ_STUDIA_BACKEND_SUBJECT", "taskiq.studia.backend.x")
    monkeypatch.setenv("TASKIQ_STUDIA_BACKEND_MAX_ACK_PENDING", "4")
    monkeypatch.setenv("TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS", "120")
    cfg = load_broker_config()
    assert cfg.nats_servers == ["nats://a:4222", "nats://b:4222"]
    assert cfg.result_redis_url == "redis://r:6379/5"
    assert cfg.subject == "taskiq.studia.backend.x"
    assert cfg.max_ack_pending == 4
    assert cfg.ack_wait_seconds == 120


def test_build_broker_tipo_e_result_backend():
    b = build_broker()
    assert isinstance(b, PullBasedJetStreamBroker)
    assert isinstance(b.result_backend, RedisAsyncResultBackend)


def test_processar_aula_registrada_no_broker():
    # A task decorada com @broker.task fica disponível no broker do módulo.
    # PullBasedJetStreamBroker usa local_task_registry (dict) em vez de available_tasks.
    assert worker.processar_aula.task_name in worker.broker.local_task_registry
