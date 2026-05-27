# tec-scraper

Scraper especializado para `witdev-tec-master` — coleta de questões TecConcursos via API JSON autenticada. **Caminho 2 (Apêndice C) da spec**: zero custo de IA, ~3h pra 22k questões.

Estrutura alinhada ao padrão **`witdev-platform-core/services/scraper/`**:

```
services/scraper/
├── pyproject.toml          # Poetry (Python 3.12)
├── Dockerfile              # Base Playwright oficial
├── .env.example
└── app/
    ├── main.py             # CLI typer + FastAPI control-plane
    ├── config.py           # pydantic-settings
    ├── observability.py    # structlog (JSON em prod, console em dev)
    ├── auth.py             # Playwright login → storage_state.json
    ├── client.py           # httpx async + rate limit + classificação de erros
    ├── schemas.py          # Pydantic v2 flexível (extra="allow")
    ├── state.py            # SQLite ScrapeState (retomada idempotente)
    ├── discovery.py        # dump raw JSON pra inspeção
    ├── persistir.py        # upsert Postgres via SQLAlchemy
    └── scrapers/
        └── tecconcursos.py # orquestração: ids → fetch → upsert
```

## Arquitetura (alinhada à Platform Core)

```
┌──────────────────────────────────┐      ┌─────────────────────────┐
│ studia backend worker (Taskiq)   │      │ studia FastAPI          │
│  └─ scrape_caderno_tc(caderno_id)├─HTTP►│  POST /admin/scrape/... │
└──────────────┬───────────────────┘      └─────────────────────────┘
               │ POST /run/caderno
               ▼
┌──────────────────────────────────┐
│ scraper (FastAPI :8090)          │
│  ├─ Playwright cookies (login)   │
│  ├─ httpx → TecConcursos API     │
│  ├─ Pydantic schemas             │
│  ├─ SQLAlchemy upsert            │
│  └─ ScrapeState (SQLite)         │
└──────────────┬───────────────────┘
               │
               ▼
        Postgres studia
        (models de backend/models.py)
```

- **FastAPI** é a fonte de verdade operacional do scraper
- **Pydantic v2** governa os contratos (schemas.py)
- **SQLAlchemy 2.x async** persiste (persistir.py)
- **structlog** loga em JSON
- O worker do studia (que já roda **Taskiq + Redis**) é quem dispara o scraper via HTTP

## Setup local (sem Docker)

```bash
cd services/scraper
poetry install
poetry run playwright install chromium
cp .env.example .env
# preencher TC_EMAIL / TC_PASSWORD
```

## Setup Docker (recomendado)

Já está integrado ao `docker-compose.dev.yml` do studia:

```bash
# Na raiz do studia
export TC_EMAIL=seu@email.com
export TC_PASSWORD=suasenha
./dev.sh up
# o serviço scraper sobe em http://localhost:8090
```

## Uso

### 1. Login (uma vez por sessão — ~7 dias)

```bash
# Local
poetry run python -m app.main login --no-headless   # 1ª vez visual (debug)
poetry run python -m app.main login                 # subsequente headless

# Docker
docker exec -it studia-scraper-dev python -m app.main login
```

Salva `storage_state.json` (cookies AWSALB + prism_*).

### 2. Discovery — confirme os schemas antes de scrapear em massa

A spec marca vários campos com `# CONFIRMAR` porque foram inferidos sem
captura DevTools real. O modo discovery bate o endpoint e salva o JSON
cru em `./discovery/`:

```bash
# Inspecionar 1 questão real
python -m app.main discover questao 2040057 --caderno-id 95116581

# Tentar descobrir endpoint de IDs do caderno
python -m app.main discover caderno 95116581

# Bater contagem/filtros (a "mágica" sub-segundo do TC)
python -m app.main discover contagem
python -m app.main discover lista
```

Inspecione os arquivos em `./discovery/*.json`, e aperte `schemas.py`
quando o formato real estiver claro.

### 3. Scrape

```bash
# Pipeline completo: listar IDs do caderno → scrape → persist Postgres
python -m app.main scrape caderno 95116581

# Subset de IDs (útil pra retries)
python -m app.main scrape questoes 2040057 2040058 --caderno-id 95116581

# Status (quantas já coletadas)
python -m app.main status
```

### 4. Via Taskiq (worker do studia)

```python
from worker import scrape_caderno_tc

# Em qualquer endpoint do backend studia:
await scrape_caderno_tc.kiq(95116581)
```

Worker enfileira → scraper executa → progresso persistido em Postgres.

## Retomada e resiliência

- `ScrapeState` (SQLite) pula IDs já coletadas — pode interromper a qualquer momento e relançar
- Rate limit: `TC_RATE_PER_SEC=2.0` (default) + jitter aleatório
- HTTP 429 → backoff exponencial via `tenacity` (até 5 tentativas, max 300s)
- HTTP 302→/login → exceção `SessionExpired`: rode `login` de novo
- 403/451 → `AccessBlocked`: reduzir taxa, esperar janela
- Captcha → `CaptchaChallenge`: resolver manualmente, refazer login

## Operação contínua e limites observados

| Limite TC | Valor | Como o scraper trata |
|---|---|---|
| Caderno máx. | 30.000 questões | Aceita; quebra em runs paralelos se quiser |
| Rate limit | Não documentado | Default 2 req/s, jitter 0.3–1.5s |
| TTL sessão (AWSALB) | ~7 dias | Re-login automático manual via CLI |

## Mapa de extração para `witdev-platform-core/services/scraper/`

Quando este código for promovido ao monorepo Platform Core, apenas dois pontos mudam:

1. **`persistir.py`** — em vez de gravar direto via SQLAlchemy, faz `POST /api/q/upsert` no `platform-api`. O resto do código (`client.py`, `state.py`, `auth.py`, `scrapers/`) migra inalterado.
2. **`pyproject.toml`** — alinhar com versões fixadas no `services/scraper/pyproject.toml` da Platform Core (Playwright 1.58.0 já está).

Demais convergências (já implementadas aqui):

- Estrutura `app/main.py + app/config.py + app/observability.py + app/scrapers/` ✓
- structlog ✓
- pydantic-settings ✓
- FastAPI como control-plane ✓
- Docker base `mcr.microsoft.com/playwright/python` ✓
- Worker externo chama via HTTP (não broker próprio) ✓

## Anti-patterns proibidos (Platform Architecture §27)

Este serviço **não**:

- Mantém dupla fonte de verdade (a verdade é Postgres, via models de `backend/models.py`)
- Cria backend separado por produto (é runtime interno conforme §20)
- Substitui Pydantic v2 por outro validador
- Usa Prisma ou ORM alternativo
- Mantém compat layer estrutural permanente

## Dependências chave

| Pacote | Versão | Função |
|---|---|---|
| fastapi | ^0.115.0 | control-plane |
| playwright | 1.58.0 | login + captura cookies |
| playwright-stealth | ^2.0.0 | anti-fingerprint |
| httpx[http2] | ^0.28.1 | cliente API |
| tenacity | ^9.0.0 | retry com backoff |
| pydantic | ^2.5.3 | schemas |
| pydantic-settings | ^2.1.0 | config |
| sqlalchemy[asyncio] | ^2.0.41 | persistência |
| asyncpg | ^0.30.0 | driver Postgres |
| structlog | ^25.1.0 | logs |
| typer | ^0.15.0 | CLI |
| markdownify | ^0.13.1 | HTML → MD do enunciado |
| python-slugify | ^8.0.0 | slugs de banca/órgão |

## Próximos passos

- [ ] Capturar payloads reais (DevTools) e apertar `schemas.py`
- [ ] Smoke test: scrape de 10 questões e validar Postgres
- [ ] Indexar em Meilisearch (Fase 2 da spec — quando subir o serviço `meili`)
- [ ] Adicionar `pgvector` embedding (Fase 5)
- [ ] Endpoint `POST /api/q/upsert` no `platform-api` (extração futura)
