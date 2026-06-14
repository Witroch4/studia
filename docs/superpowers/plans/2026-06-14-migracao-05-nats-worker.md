# Plano 05 — NATS JetStream no worker do backend (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o broker do worker do backend studIA de TaskIQ-Redis (`ListQueueBroker`) para NATS JetStream compartilhado (`platform-nats`), espelhando o padrão já comprovado do scraper, e de quebra corrigir o `studia_worker` 0/1 (crash-loop por healthcheck HTTP herdado).

**Architecture:** O worker do backend tem uma única task no caminho quente (`processar_aula`) e um único produtor (`main.py`). O broker passa a ser um `PullBasedJetStreamBroker` (taskiq-nats) com **stream/subject/durable próprios** (`TASKIQ_STUDIA_BACKEND` / `taskiq.studia.backend` / `studia-backend-workers`) para **não colidir** com o stream do scraper (`TASKIQ_STUDIA`). Result backend continua no Redis (`redis:6379/2`), como o scraper. O produtor (FastAPI/uvicorn) ganha `broker.startup()`/`shutdown()` no lifespan, porque o JetStream — diferente do Redis — exige conexão/criação de stream antes de publicar. A config vem 100% de env, com defaults seguros.

**Tech Stack:** Python 3.12, FastAPI, TaskIQ, `taskiq-nats==0.6.0`, `nats-py==2.15.0`, `taskiq-redis` (result backend), NATS JetStream (`platform-nats`), Docker Swarm / Compose.

---

## Contexto descoberto (não repetir descoberta)

- **NATS DNS:** prod `nats://nats:4222`; dev `nats://platform-nats:4222` (rede `shared` = external `minha_rede`). O backend worker já está nas redes certas (prod `minha_rede`; dev `shared` + `studia-net`).
- **Padrão comprovado:** `services/scraper/app/tasks/brokers/studia.py` usa `PullBasedJetStreamBroker(servers=..., subject=..., stream_name=..., durable=..., pull_consume_batch=..., stream_config=StreamConfig(name, subjects=[...]), consumer_config=ConsumerConfig(durable_name, filter_subject, ack_wait, max_deliver, max_ack_pending)).with_result_backend(RedisAsyncResultBackend(redis_url))`. `ack_wait` é em **segundos** (scraper passa `600`).
- **Stream isolado:** o scraper detém `TASKIQ_STUDIA` com subjects `taskiq.studia.default`/`taskiq.studia.low`. O backend usa um stream NOVO `TASKIQ_STUDIA_BACKEND` com subject `taskiq.studia.backend` (sem overlap — exigência do JetStream).
- **Produtor único:** `backend/main.py:531-532` (`from worker import processar_aula; await processar_aula.kiq(...)`). As tasks `scrape_caderno_tc`/`scrape_questoes_tc` existem em `worker.py` mas **nunca são despachadas** (legado) — ficam registradas, inofensivas; fora de escopo remover.
- **Causa-raiz do worker 0/1:** `backend/Dockerfile:17` tem `HEALTHCHECK` HTTP em `:8000`; o estágio `production` é usado pelo worker em prod, que não serve HTTP → unhealthy → Swarm reinicia em loop (7 containers zumbis vistos). O bloco `worker` em `docker/stack.yml` **não** sobrescreve o healthcheck. O dev usa `target: deps` (sem o `HEALTHCHECK`), então o problema é **só prod**.
- **ack_wait generoso:** `processar_aula` chama `process_pdf_chunks` (Gemini **Batch API**, com polling/backoff que pode durar minutos). Default `ack_wait=3600` (1h) evita redelivery no meio do batch. `max_ack_pending=1` (serial) e guarda de idempotência (pular aula já `CONCLUIDO`) reduzem risco de processamento duplicado.

---

## File Structure

- **Modify** `backend/requirements.txt` — adicionar `taskiq-nats==0.6.0` e `nats-py==2.15.0`.
- **Modify** `backend/worker.py` — substituir a definição do broker (Redis → NATS JetStream) via factory configurável por env (`load_broker_config()` + `build_broker()`); manter as tasks; adicionar guarda de idempotência em `processar_aula`.
- **Modify** `backend/main.py` — `lifespan` faz `broker.startup()`/`broker.shutdown()` (produtor JetStream).
- **Create** `backend/tests/test_worker_nats_broker.py` — testes da config (pura, env-driven), do tipo do broker, do result backend e do registro da task. Não conecta no NATS.
- **Modify** `docker/stack.yml` (bloco `worker`, ~L70-86) — env NATS + `TASKIQ_RESULT_REDIS_URL` + env do stream do backend + **healthcheck desabilitado** (`test: ["NONE"]`).
- **Modify** `docker-compose.dev.yml` (bloco `worker`, ~L31-57) — env NATS (`platform-nats`) + `TASKIQ_RESULT_REDIS_URL` + env do stream do backend.

Contrato de env do worker do backend (todos com default seguro em `load_broker_config()`):

| Env | Default | Significado |
|---|---|---|
| `NATS_SERVERS` | `nats://nats:4222` | servidores NATS (CSV) |
| `TASKIQ_RESULT_REDIS_URL` | `redis://redis:6379/2` | result backend Redis |
| `TASKIQ_STUDIA_BACKEND_STREAM` | `TASKIQ_STUDIA_BACKEND` | nome do stream |
| `TASKIQ_STUDIA_BACKEND_SUBJECT` | `taskiq.studia.backend` | subject |
| `TASKIQ_STUDIA_BACKEND_DURABLE` | `studia-backend-workers` | consumer durável |
| `TASKIQ_STUDIA_BACKEND_PULL_BATCH` | `1` | mensagens por pull |
| `TASKIQ_STUDIA_BACKEND_MAX_ACK_PENDING` | `1` | concorrência (serial) |
| `TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS` | `3600` | janela de ack (batch lento) |
| `TASKIQ_STUDIA_BACKEND_MAX_DELIVER` | `3` | tentativas de entrega |

---

### Task 1: Dependências NATS no backend

**Files:**
- Modify: `backend/requirements.txt:52-53`

- [ ] **Step 1: Adicionar as duas dependências (versões iguais às do scraper)**

Em `backend/requirements.txt`, logo após a linha `taskiq-redis` (linha 53), o trecho fica:

```
taskiq[redis,reload]
taskiq-redis
taskiq-nats==0.6.0
nats-py==2.15.0
```

- [ ] **Step 2: Instalar localmente no container e confirmar import**

Run:
```bash
cd /home/wital/studia && ./dev.sh build
docker compose -f docker-compose.dev.yml run --rm backend python -c "from taskiq_nats import PullBasedJetStreamBroker; from nats.js.api import ConsumerConfig, StreamConfig; print('ok')"
```
Expected: imprime `ok` (sem ImportError).

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps(worker): adiciona taskiq-nats + nats-py p/ broker NATS JetStream"
```

---

### Task 2: Broker NATS JetStream em `worker.py` (config + factory) — TDD

**Files:**
- Test: `backend/tests/test_worker_nats_broker.py`
- Modify: `backend/worker.py:1-24` (imports + definição do broker) e `backend/worker.py:74-89` (guarda de idempotência em `processar_aula`)

- [ ] **Step 1: Escrever o teste falho da config e do broker**

Criar `backend/tests/test_worker_nats_broker.py`:

```python
"""Config do broker NATS do worker do backend — sem conectar no NATS.

build_broker() só constrói o objeto (a conexão acontece em startup()),
então estes testes rodam sem um NATS de verdade.
"""
import importlib

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
    assert worker.processar_aula.task_name in worker.broker.available_tasks
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/wital/studia && ./dev.sh test backend/tests/test_worker_nats_broker.py`
Expected: FAIL no import (`ImportError: cannot import name 'load_broker_config' from 'worker'`).

- [ ] **Step 3: Implementar o broker NATS em `worker.py`**

Substituir o topo de `backend/worker.py` (linhas 1-24, do `import io` até o bloco que define `broker = ListQueueBroker(...)`) por:

```python
import io
import json
import asyncio
import os
import re
import traceback
from dataclasses import dataclass

import httpx
import pymupdf
from nats.js.api import ConsumerConfig, StreamConfig
from taskiq_nats import PullBasedJetStreamBroker
from taskiq_redis import RedisAsyncResultBackend

from database import async_session
from models import Aula, BlocoConteudo, Flashcard, Deck, StatusProcessamento
from minio_client import download_pdf
from gemini_service import process_pdf_chunks

SCRAPER_URL = os.getenv("SCRAPER_URL", "http://scraper:8090")


@dataclass(frozen=True)
class BrokerConfig:
    nats_servers: list[str]
    result_redis_url: str
    stream: str
    subject: str
    durable: str
    pull_batch: int
    max_ack_pending: int
    ack_wait_seconds: int
    max_deliver: int


def load_broker_config() -> BrokerConfig:
    """Config do broker NATS do worker do backend, 100% via env (defaults seguros)."""
    servers = os.getenv("NATS_SERVERS", "nats://nats:4222")
    return BrokerConfig(
        nats_servers=[s.strip() for s in servers.split(",") if s.strip()],
        result_redis_url=os.getenv("TASKIQ_RESULT_REDIS_URL", "redis://redis:6379/2"),
        stream=os.getenv("TASKIQ_STUDIA_BACKEND_STREAM", "TASKIQ_STUDIA_BACKEND"),
        subject=os.getenv("TASKIQ_STUDIA_BACKEND_SUBJECT", "taskiq.studia.backend"),
        durable=os.getenv("TASKIQ_STUDIA_BACKEND_DURABLE", "studia-backend-workers"),
        pull_batch=int(os.getenv("TASKIQ_STUDIA_BACKEND_PULL_BATCH", "1")),
        max_ack_pending=int(os.getenv("TASKIQ_STUDIA_BACKEND_MAX_ACK_PENDING", "1")),
        ack_wait_seconds=int(os.getenv("TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS", "3600")),
        max_deliver=int(os.getenv("TASKIQ_STUDIA_BACKEND_MAX_DELIVER", "3")),
    )


def build_broker(cfg: BrokerConfig | None = None) -> PullBasedJetStreamBroker:
    """Constrói o broker NATS JetStream (não conecta — conexão é no startup())."""
    cfg = cfg or load_broker_config()
    return PullBasedJetStreamBroker(
        servers=cfg.nats_servers,
        subject=cfg.subject,
        stream_name=cfg.stream,
        durable=cfg.durable,
        pull_consume_batch=cfg.pull_batch,
        stream_config=StreamConfig(name=cfg.stream, subjects=[cfg.subject]),
        consumer_config=ConsumerConfig(
            durable_name=cfg.durable,
            filter_subject=cfg.subject,
            ack_wait=cfg.ack_wait_seconds,
            max_deliver=cfg.max_deliver,
            max_ack_pending=cfg.max_ack_pending,
        ),
    ).with_result_backend(RedisAsyncResultBackend(redis_url=cfg.result_redis_url))


broker = build_broker()
```

> Nota: o `import os`/`import re`/`import traceback` que estavam mais abaixo no arquivo original (linhas ~16-17 e o `import traceback` do topo) foram consolidados aqui — **remover as linhas duplicadas** `import os` e `import re` que ficavam após o `broker = ...` original, se ainda existirem.

- [ ] **Step 4: Adicionar guarda de idempotência em `processar_aula`**

Em `backend/worker.py`, dentro de `processar_aula`, logo após obter `aula` e o check `if not aula:` (após a linha `return {"error": f"Aula {aula_id} não encontrada"}`), inserir:

```python
            # Idempotência: se já concluída, não reprocessa (evita duplicar em
            # caso de redelivery do JetStream após ack_wait).
            if aula.status == StatusProcessamento.CONCLUIDO.value:
                return {"status": "skip", "motivo": "aula já concluída", "aula_id": aula_id}
```

- [ ] **Step 5: Rodar os testes do broker e ver passar**

Run: `cd /home/wital/studia && ./dev.sh test backend/tests/test_worker_nats_broker.py`
Expected: PASS (5 testes verdes).

- [ ] **Step 6: Rodar a suíte inteira (não quebrar nada)**

Run: `cd /home/wital/studia && ./dev.sh test`
Expected: todos verdes (suíte anterior + 5 novos).

- [ ] **Step 7: Commit**

```bash
git add backend/worker.py backend/tests/test_worker_nats_broker.py
git commit -m "feat(worker): broker NATS JetStream (stream próprio do backend) + idempotência em processar_aula"
```

---

### Task 3: Produtor — `broker.startup()`/`shutdown()` no lifespan

**Files:**
- Modify: `backend/main.py:111-119` (lifespan)

- [ ] **Step 1: Editar o lifespan para iniciar/encerrar o broker (lado produtor)**

Substituir o corpo do `lifespan` em `backend/main.py` (linhas 111-119) por:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migrações rodam via Alembic: ./dev.sh migrate (ou python -m scripts.db_prepare)
    # Garantir bucket MinIO existe
    try:
        await asyncio.to_thread(ensure_bucket)
    except Exception:
        pass  # MinIO pode não estar pronto ainda

    # Produtor do NATS JetStream: precisa de startup() p/ criar/garantir o
    # stream e poder publicar (.kiq). Diferente do Redis, não conecta lazy.
    from worker import broker
    if not broker.is_worker_process:
        try:
            await broker.startup()
        except Exception:
            # NATS pode não estar pronto no boot; .kiq falharia visivelmente depois.
            pass
    try:
        yield
    finally:
        if not broker.is_worker_process:
            try:
                await broker.shutdown()
            except Exception:
                pass
```

- [ ] **Step 2: Verificar que o app sobe e o health responde (dev)**

Run:
```bash
cd /home/wital/studia && ./dev.sh up:d
sleep 8
curl -fsS http://localhost:8011/api/health && echo " OK"
docker logs studia-backend-dev 2>&1 | tail -20
```
Expected: `{"status":...}` + ` OK`; logs do backend sem traceback de NATS (broker conectou). Se o NATS dev não estiver de pé, ver Step 3.

- [ ] **Step 3: (se necessário) confirmar NATS dev acessível**

Run:
```bash
docker compose -f /home/wital/studia/docker-compose.dev.yml run --rm backend python -c "import asyncio,nats; asyncio.run(nats.connect('nats://platform-nats:4222')); print('nats ok')"
```
Expected: `nats ok`. (Se falhar, o `platform-nats` não está na rede `minha_rede` do dev — alinhar antes de seguir.)

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat(api): startup/shutdown do broker NATS no lifespan (produtor .kiq)"
```

---

### Task 4: Stack de produção — env NATS + healthcheck do worker

**Files:**
- Modify: `docker/stack.yml:70-86` (bloco `worker`)

- [ ] **Step 1: Atualizar o bloco `worker` (env NATS + result Redis + stream backend + desabilitar healthcheck)**

Substituir o bloco `worker:` em `docker/stack.yml` (linhas 70-86) por:

```yaml
  worker:
    image: *backend-image
    env_file:
      - ${STUDIA_ENV_FILE:-/opt/studia/.env}
    environment:
      REDIS_URL: redis://redis:6379/1
      MINIO_ENDPOINT: minio:9000
      MEILI_URL: http://studia-meili:7700
      SCRAPER_URL: http://studia-scraper:8090
      PYTHONDONTWRITEBYTECODE: "1"
      TZ: America/Fortaleza
      NATS_SERVERS: nats://nats:4222
      TASKIQ_RESULT_REDIS_URL: redis://redis:6379/2
      TASKIQ_STUDIA_BACKEND_MAX_ACK_PENDING: "1"
      TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS: "3600"
    command: taskiq worker worker:broker
    # O worker não serve HTTP; desabilita o HEALTHCHECK HTTP herdado da imagem
    # (Dockerfile estágio production) que causava unhealthy → crash-loop (0/1).
    healthcheck:
      test: ["NONE"]
    networks:
      - minha_rede
    deploy:
      <<: *on-manager
```

- [ ] **Step 2: Validar a sintaxe do compose/stack localmente**

Run: `cd /home/wital/studia && docker compose -f docker/stack.yml config >/dev/null && echo "stack OK"`
Expected: `stack OK` (sem erro de YAML; avisos de variável não setada são aceitáveis).

- [ ] **Step 3: Commit**

```bash
git add docker/stack.yml
git commit -m "fix(prod): worker no NATS JetStream + desabilita healthcheck HTTP herdado (corrige 0/1)"
```

---

### Task 5: Dev compose — env NATS do worker

**Files:**
- Modify: `docker-compose.dev.yml:40-54` (environment do bloco `worker`)

- [ ] **Step 1: Acrescentar env NATS ao worker dev**

No bloco `worker:` de `docker-compose.dev.yml`, dentro de `environment:` (após a linha `- STUDIA_COOKIE_SECURE=false`, antes de `networks:`), adicionar:

```yaml
      - NATS_SERVERS=${NATS_SERVERS:-nats://platform-nats:4222}
      - TASKIQ_RESULT_REDIS_URL=redis://redis:6379/2
      - TASKIQ_STUDIA_BACKEND_MAX_ACK_PENDING=1
      - TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS=3600
```

- [ ] **Step 2: Subir dev e confirmar o worker conectando no NATS**

Run:
```bash
cd /home/wital/studia && ./dev.sh up:d
sleep 8
docker logs studia-worker-dev 2>&1 | tail -30
```
Expected: logs do taskiq indicando consumo (sem traceback de conexão NATS); o worker fica de pé (não reinicia em loop).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "chore(dev): worker dev aponta p/ NATS (platform-nats) + result Redis /2"
```

---

### Task 6: Verificação ponta-a-ponta em dev (upload de aula real)

**Files:** nenhum (validação manual).

- [ ] **Step 1: Subir tudo limpo e disparar uma aula**

Run:
```bash
cd /home/wital/studia && ./dev.sh up:d && sleep 10
docker logs studia-worker-dev 2>&1 | tail -5
```
Expected: worker de pé.

- [ ] **Step 2: Upload de PDF via UI/endpoint e observar processamento**

Pela UI dev (`http://localhost:3000/disciplinas/<slug>`) fazer upload de um PDF pequeno, OU via curl no endpoint de criação de aula. Depois:

Run:
```bash
docker logs studia-worker-dev 2>&1 | tail -40
```
Expected: logs do `[Batch]` (Gemini), task `processar_aula` consumida pelo NATS, `aula.status` indo PENDENTE → PROCESSANDO → CONCLUIDO; flashcards/blocos criados. Conferir no banco:
```bash
docker exec studia-backend-dev python -c "import asyncio; from database import async_session; from sqlalchemy import text; \
import asyncio; \
async def go():\n    async with async_session() as db:\n        r=await db.execute(text('select id,status from aulas order by id desc limit 3')); print(r.fetchall())\nasyncio.run(go())"
```
Expected: a aula recém-criada com `status='concluido'`.

- [ ] **Step 3: Confirmar criação do stream no NATS dev**

Run:
```bash
docker exec $(docker ps --format '{{.Names}}' | grep -i platform-nats | head -1) nats stream ls 2>/dev/null || \
docker compose -f /home/wital/studia/docker-compose.dev.yml run --rm backend python -c "import asyncio,nats; \
async def go():\n    nc=await nats.connect('nats://platform-nats:4222'); js=nc.jetstream(); \
    info=await js.stream_info('TASKIQ_STUDIA_BACKEND'); print('stream:', info.config.name, 'subjects:', info.config.subjects); await nc.close()\nasyncio.run(go())"
```
Expected: stream `TASKIQ_STUDIA_BACKEND` com subject `taskiq.studia.backend`.

---

### Task 7: Deploy em produção + smoke

**Files:** nenhum (deploy). Requer confirmação do usuário antes de rodar (CLAUDE.md autoriza o fluxo `./build.sh`).

- [ ] **Step 1: Push e build/deploy**

```bash
cd /home/wital/studia && git push && ./build.sh
```
Expected: build + push das imagens + `db_prepare` + `docker stack deploy` sem erro.

- [ ] **Step 2: Smoke — worker 1/1 e stream criado**

Run:
```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 '
docker service ls | grep -E "studia_worker|studia_backend"
echo "--- worker logs ---"
docker service logs studia_worker --tail 30 2>&1 | tail -30
'
```
Expected: `studia_worker` `1/1` (sem zumbis); logs do taskiq consumindo do NATS, sem traceback.

- [ ] **Step 3: Smoke — backend publica (.kiq) e stream existe**

Run:
```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 '
NATS=$(docker ps --format "{{.Names}}" | grep -i "_nats\." | head -1)
docker exec "$NATS" sh -lc "nats stream info TASKIQ_STUDIA_BACKEND 2>/dev/null | head -20" || echo "(nats cli ausente — checar via logs do worker)"
curl -fsS https://studia.witdev.com.br/api/health && echo " HEALTH OK"
'
```
Expected: stream `TASKIQ_STUDIA_BACKEND` presente; `HEALTH OK`.

- [ ] **Step 4: Smoke ponta-a-ponta (opcional, com login real) — processar uma aula em prod**

Pela UI de prod, subir um PDF pequeno e confirmar status `concluido`. Se algo travar:
```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 'docker service logs studia_worker --tail 60'
```
Rollback de emergência (padrão comprovado):
```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 'docker service rollback studia_worker studia_backend'
```

- [ ] **Step 5: Worktree limpo + memória**

Run: `cd /home/wital/studia && git status`
Expected: limpo. Atualizar a memória `studia-padronizacao.md` (Plano 05 ✅) e, se relevante, criar memória sobre o stream `TASKIQ_STUDIA_BACKEND` e o fix do healthcheck do worker.

---

## Self-Review

**Spec coverage (gaps do §15 / padronização):**
- "NATS compartilhado no worker do backend" → Tasks 1-5 (broker NATS, env prod+dev, produtor).
- "worker 0/1 (healthcheck)" → Task 4 Step 1 (`healthcheck: test: ["NONE"]`).
- "não colidir com o scraper" → stream/subject próprios (`TASKIQ_STUDIA_BACKEND`), coberto por `test_config_subject_nao_colide_com_scraper`.
- "result backend Redis" → mantido (`redis:6379/2`), coberto por `test_build_broker_tipo_e_result_backend`.
- "produtor publica" → Task 3 (startup no lifespan).

**Placeholder scan:** sem TBD/TODO; todo passo de código tem o código real.

**Type consistency:** `BrokerConfig` (campos `nats_servers, result_redis_url, stream, subject, durable, pull_batch, max_ack_pending, ack_wait_seconds, max_deliver`) é usado de forma idêntica em `load_broker_config()`, `build_broker()` e nos testes. `load_broker_config`/`build_broker`/`broker`/`processar_aula` nomeados de forma consistente entre `worker.py`, `main.py` (import de `broker`) e os testes.

**Riscos conhecidos:**
- Batch lento > `ack_wait` (1h) → redelivery. Mitigado por `ack_wait=3600` + `max_ack_pending=1` + guarda de idempotência (skip se `CONCLUIDO`). Se batches passarem de 1h com frequência, subir `TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS`.
- `is_worker_process` (taskiq) usado p/ não startar o broker como produtor dentro do próprio worker — atributo padrão do TaskiqBroker.
