# Migração studIA → padrão · Plano 02: Estrutura de `domains/` + `platform_core/`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar o backend de **flat** (tudo em `main.py` + routers soltos) para `platform_core/` (app factory + registry + cross-cutting) e `domains/<x>/` (um router por domínio), **sem nenhuma mudança de comportamento** — a suíte (58 testes no Postgres) guarda cada passo.

**Architecture:** Os módulos compartilhados (`models.py`, `database.py`, `auth.py`, `entitlements.py`, `gemini_service.py`, `worker.py`, `minio_client.py`, `parser.py`, `meili_index.py`, `sync_meili.py`, `concurso_engine.py`) **permanecem na raiz** de `backend/` e continuam importados por path absoluto (`from models import ...`) — isso evita reescrever imports em todo lugar. O que muda: cada router vira `domains/<x>/router.py` (expondo `router: APIRouter`), e `platform_core/app.py` é a **fábrica do app** que monta o FastAPI (CORS + lifespan) e inclui os routers de uma **lista de registry**. `main.py` vira um reexport fino (`from platform_core.app import app`) para o `uvicorn main:app` seguir funcionando.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, pytest (Postgres `studia_test`).

**Pré-requisito:** Plano 01 mergeado (Alembic + testes em Postgres). Postgres compartilhado de pé. Rodar a suíte com `./dev.sh test -q` após cada task — **deve permanecer 58 verde** (ou o nº corrente). Qualquer queda = a movimentação quebrou um import/rota; conserte antes de commitar.

**Princípio de cada task:** mover código **verbatim** (corpo dos endpoints inalterado), trocando apenas `@app.<verb>` por `@router.<verb>` e levando junto os imports que aquele router usa. Nenhuma lógica nova.

---

### Task 1: `platform_core/app.py` (app factory + registry) + `main.py` fino

Cria o núcleo: a fábrica do app com CORS + lifespan + uma lista de routers de domínio. Nesta task, o ÚNICO domínio registrado é `system` (rotas `/api/health` e `/api/modelos`, hoje inline no `main.py`). Os demais routers continuam incluídos no `main.py` temporariamente e migram nas tasks seguintes.

**Files:**
- Create: `backend/platform_core/__init__.py` (vazio)
- Create: `backend/platform_core/app.py`
- Create: `backend/domains/__init__.py` (vazio)
- Create: `backend/domains/system/__init__.py` (vazio)
- Create: `backend/domains/system/router.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Ler o `main.py` atual** para extrair, sem alterar: o bloco `app = FastAPI(...)`, o `lifespan`, a configuração de CORS (`app.add_middleware(CORSMiddleware, ...)`), e os corpos das rotas `/api/health` (linha ~163) e `/api/modelos` (linha ~171).

- [ ] **Step 2: Criar `backend/domains/system/router.py`** — mover VERBATIM as rotas `/api/health` e `/api/modelos`, trocando `@app.get` por `@router.get`, e levando os imports que elas usam:

```python
from fastapi import APIRouter

router = APIRouter(tags=["system"])

# COLE AQUI, verbatim, os corpos de /api/health e /api/modelos do main.py,
# trocando @app.get(...) por @router.get(...). Leve os imports que esses
# handlers usarem (ex.: a lista de modelos Gemini, se vier de um módulo).
```

- [ ] **Step 3: Criar `backend/platform_core/app.py`** — a fábrica + registry. Copie o `lifespan` e o `add_middleware(CORSMiddleware, ...)` VERBATIM do `main.py` (mesmos parâmetros: origins, allow_credentials, methods, headers):

```python
from contextlib import asynccontextmanager
from importlib import import_module

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from minio_client import ensure_bucket

# Ordem de inclusão dos routers de domínio. Conforme cada task migra um
# domínio, adicione-o aqui (e remova o include correspondente do main.py).
DOMAIN_ROUTERS: list[str] = [
    "domains.system.router",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # (verbatim do main.py) garantir bucket MinIO
    try:
        await asyncio.to_thread(ensure_bucket)
    except Exception:
        pass  # MinIO pode não estar pronto ainda
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="studIA API", version="0.3.0", lifespan=lifespan)
    # COLE AQUI o app.add_middleware(CORSMiddleware, ...) verbatim do main.py
    for module_path in DOMAIN_ROUTERS:
        module = import_module(module_path)
        app.include_router(module.router)
    return app


app = create_app()
```

- [ ] **Step 4: Editar `backend/main.py`** — remover as rotas `/api/health` e `/api/modelos` (agora em `domains/system`), remover o `app = FastAPI(...)`/`lifespan`/CORS (agora em `platform_core/app.py`), e no LUGAR onde `app` era criado, reexportar:

```python
from platform_core.app import app  # noqa: F401  (uvicorn main:app)
```
Mantenha, por enquanto, os `app.include_router(...)` dos outros 3 routers (q, guias, billing) logo após o import — eles migram nas próximas tasks. (Para isso, `from platform_core.app import app` precisa vir antes desses includes.)

- [ ] **Step 5: Validar** — `./dev.sh test -q` deve seguir verde (58). Além disso, confirme que `/api/health` responde:
```bash
docker exec studia-backend-dev sh -lc 'cd /app && python -c "
from fastapi.testclient import TestClient
from main import app
print([r.path for r in app.routes if getattr(r,\"path\",\"\").startswith(\"/api\")][:8])
"'
```
Expected: lista de rotas inclui `/api/health` e `/api/modelos` (servidas pelo router de system).

- [ ] **Step 6: Commit**
```bash
git add backend/platform_core backend/domains backend/main.py
git commit -m "refactor(domains): platform_core app factory + registry; system vira domínio"
```

---

### Task 2: `domains/billing/` (mover billing_router)

O menor router standalone — prova o padrão de mover um router já separado.

**Files:**
- Create: `backend/domains/billing/__init__.py` (vazio)
- Create: `backend/domains/billing/router.py` (= conteúdo de `backend/billing_router.py`)
- Delete: `backend/billing_router.py`
- Modify: `backend/platform_core/app.py` (registrar) e `backend/main.py` (remover o include antigo)

- [ ] **Step 1: Mover o arquivo** preservando o conteúdo:
```bash
git mv backend/billing_router.py backend/domains/billing/router.py
```
O `router.py` já expõe `router = APIRouter(prefix="/api/billing", ...)`. Seus imports são absolutos (`from models import ...`, `from auth import ...`) e continuam válidos.

- [ ] **Step 2: Registrar no `platform_core/app.py`** — adicione `"domains.billing.router"` à lista `DOMAIN_ROUTERS`.

- [ ] **Step 3: Remover o include antigo do `main.py`** — apague as linhas `from billing_router import router as billing_router` e `app.include_router(billing_router)`.

- [ ] **Step 4: Validar** — `grep -rn "billing_router" backend/ | grep -v domains/billing` deve estar vazio. `./dev.sh test -q` verde.

- [ ] **Step 5: Commit**
```bash
git add -A backend/domains/billing backend/platform_core/app.py backend/main.py
git commit -m "refactor(domains): billing → domains/billing"
```

---

### Task 3: `domains/questoes/` (mover q_router)

**Files:**
- Create: `backend/domains/questoes/__init__.py` (vazio)
- Create: `backend/domains/questoes/router.py` (= `backend/q_router.py`)
- Delete: `backend/q_router.py`
- Modify: `platform_core/app.py`, `main.py`
- Check: `backend/tests/` (algum teste importa de `q_router`?)

- [ ] **Step 1:** `git mv backend/q_router.py backend/domains/questoes/router.py`

- [ ] **Step 2:** Atualizar referências. `grep -rn "q_router\|from q_router\|import q_router" backend/` — para CADA hit (em `main.py` e em testes como `tests/test_q_*`), trocar o import para `from domains.questoes.router import ...`. (Os testes importam `q_router` para monkeypatch — ex.: `q_router.SCRAPER_URL`; atualizar o caminho do módulo.)

- [ ] **Step 3:** Registrar `"domains.questoes.router"` em `DOMAIN_ROUTERS`; remover `from q_router import router as q_router` / `app.include_router(q_router)` do `main.py`.

- [ ] **Step 4: Validar** — `grep -rn "q_router" backend/ | grep -v "domains/questoes"` só pode mostrar referências já reapontadas para `domains.questoes.router`. `./dev.sh test -q` verde (os testes de questões são a maior parte da suíte — bom guarda).

- [ ] **Step 5: Commit**
```bash
git add -A backend/domains/questoes backend/platform_core/app.py backend/main.py backend/tests
git commit -m "refactor(domains): questoes → domains/questoes"
```

---

### Task 4: `domains/guias/` (mover guias_router)

**Files:**
- Create: `backend/domains/guias/__init__.py` (vazio)
- Create: `backend/domains/guias/router.py` (= `backend/guias_router.py`)
- Delete: `backend/guias_router.py`
- Modify: `platform_core/app.py`, `main.py`, testes que importam `guias_router`

- [ ] **Step 1:** `git mv backend/guias_router.py backend/domains/guias/router.py`

- [ ] **Step 2:** `grep -rn "guias_router" backend/` — reapontar imports (em `main.py` e `tests/test_guias_router.py`) para `from domains.guias.router import ...`.

- [ ] **Step 3:** Registrar `"domains.guias.router"`; remover o include antigo do `main.py`.

- [ ] **Step 4: Validar** — grep limpo; `./dev.sh test -q` verde.

- [ ] **Step 5: Commit**
```bash
git add -A backend/domains/guias backend/platform_core/app.py backend/main.py backend/tests
git commit -m "refactor(domains): guias → domains/guias"
```

---

### Task 5: `domains/flashcards/` (extrair decks + flashcards do main.py)

Extrai as rotas inline do `main.py`: `/api/decks` (GET, DELETE), `/api/flashcards/todos`, `/api/flashcards/{deck_slug}`, `/api/flashcards` (POST), `/api/flashcards/import`.

**Files:**
- Create: `backend/domains/flashcards/__init__.py` (vazio)
- Create: `backend/domains/flashcards/router.py`
- Modify: `backend/main.py` (remover essas rotas), `platform_core/app.py` (registrar)

- [ ] **Step 1: Criar `domains/flashcards/router.py`** com um `router = APIRouter(tags=["flashcards"])` e MOVER verbatim os 5 endpoints de decks/flashcards do `main.py`, trocando `@app.<verb>("/api/...")` por `@router.<verb>("/api/...")` (mantendo o path completo). Leve para o topo do arquivo os imports que esses handlers usam — tipicamente: `from models import Deck, Flashcard` (e o que mais aparecer nos corpos), `from parser import parse_markdown`, `from database import get_db`, deps do FastAPI (`Depends`, `UploadFile`, etc.), `from auth import ...` se usado.

- [ ] **Step 2:** Remover do `main.py` os 5 endpoints movidos. Registrar `"domains.flashcards.router"` em `DOMAIN_ROUTERS`.

- [ ] **Step 3: Validar** — confirme que as rotas existem no app:
```bash
docker exec studia-backend-dev sh -lc 'cd /app && python -c "
from main import app
paths=sorted(r.path for r in app.routes if getattr(r,\"path\",\"\").startswith((\"/api/decks\",\"/api/flashcards\")))
print(paths)
"'
```
Expected: as 5 rotas presentes. `./dev.sh test -q` verde.

- [ ] **Step 4: Commit**
```bash
git add -A backend/domains/flashcards backend/main.py backend/platform_core/app.py
git commit -m "refactor(domains): flashcards/decks → domains/flashcards"
```

---

### Task 6: `domains/disciplinas/` (extrair disciplinas, aulas, chat e jobs do main.py)

Extrai: `/api/disciplinas` (GET/POST), `/api/disciplinas/{slug}` (GET), `/api/disciplinas/{slug}/aulas` (POST), `/api/aulas/{aula_id}` (GET), `/api/aulas/{aula_id}/status`, `/api/aulas/{aula_id}/pdf`, `/api/aulas/{aula_id}/chat` (POST), `/api/jobs`, `/api/batch-jobs`, `/api/batch-jobs/{job_name}/cancel`, `/api/batch-jobs/{job_name}` (DELETE).

**Files:**
- Create: `backend/domains/disciplinas/__init__.py` (vazio)
- Create: `backend/domains/disciplinas/router.py`
- Modify: `backend/main.py`, `platform_core/app.py`

- [ ] **Step 1: Criar `domains/disciplinas/router.py`** com `router = APIRouter(tags=["disciplinas"])`. Mover verbatim os 11 endpoints acima (`@app` → `@router`). Levar os imports usados: `from models import Disciplina, Aula, BlocoConteudo, ...`, `from minio_client import upload_pdf, get_presigned_url`, `from gemini_service import ...`, `from worker import processar_aula` (e o que os jobs/chat usarem), `from database import get_db`, deps FastAPI + `from auth import require_admin` se usado. Verifique cada corpo e leve exatamente o que ele referencia.

- [ ] **Step 2:** Remover os 11 endpoints do `main.py`. Registrar `"domains.disciplinas.router"`.

- [ ] **Step 3: Validar** — checagem de rotas (`/api/disciplinas`, `/api/aulas`, `/api/jobs`, `/api/batch-jobs` presentes) como na Task 5. `./dev.sh test -q` verde. Se houver teste de dashboard/streak que cobre jobs, confirme verde.

- [ ] **Step 4: Commit**
```bash
git add -A backend/domains/disciplinas backend/main.py backend/platform_core/app.py
git commit -m "refactor(domains): disciplinas/aulas/jobs → domains/disciplinas"
```

---

### Task 7: `domains/concursos/` (extrair concursos do main.py)

Extrai: `/api/concursos/import` (POST), `/api/concursos` (GET), `/api/concursos/{id}` (GET, DELETE), `/api/concursos/{id}/simular` (POST).

**Files:**
- Create: `backend/domains/concursos/__init__.py` (vazio)
- Create: `backend/domains/concursos/router.py`
- Modify: `backend/main.py`, `platform_core/app.py`

- [ ] **Step 1: Criar `domains/concursos/router.py`** com `router = APIRouter(tags=["concursos"])`. Mover verbatim os 5 endpoints; levar imports usados: `from models import Concurso, Candidato, ...`, `from concurso_engine import ...`, `from database import get_db`, deps FastAPI, auth se usado.

- [ ] **Step 2:** Remover os 5 endpoints do `main.py`. Registrar `"domains.concursos.router"`.

- [ ] **Step 3: Validar** — rotas `/api/concursos*` presentes; `./dev.sh test -q` verde.

- [ ] **Step 4: Commit**
```bash
git add -A backend/domains/concursos backend/main.py backend/platform_core/app.py
git commit -m "refactor(domains): concursos → domains/concursos"
```

---

### Task 8: `main.py` fino + verificação de paridade de rotas

Após as migrações, `main.py` deve conter apenas o reexport do app (e nada de rota/lógica). Garantir que NENHUMA rota sumiu no caminho.

**Files:**
- Modify: `backend/main.py` (limpeza final)

- [ ] **Step 1: Capturar a lista de rotas ANTES** (use o `main` da `main` mergeada como referência). Em um checkout limpo da branch `main` (sem este plano), gere a baseline de rotas — OU, mais simples, confie na suíte (58 testes cobrem as rotas principais) + a checagem abaixo.

- [ ] **Step 2: Reduzir `main.py`** ao mínimo: o reexport `from platform_core.app import app` e quaisquer imports realmente necessários para efeitos colaterais (se houver). Remover includes antigos remanescentes. `grep -nE "@app\.|include_router" backend/main.py` deve estar vazio.

- [ ] **Step 3: Verificação de paridade** — confirme o conjunto de rotas:
```bash
docker exec studia-backend-dev sh -lc 'cd /app && python -c "
from main import app
paths=sorted({r.path for r in app.routes if getattr(r,\"path\",\"\").startswith(\"/api\")})
print(len(paths)); [print(p) for p in paths]
"'
```
Compare com a lista esperada (todas as rotas `/api/health`, `/api/modelos`, `/api/decks*`, `/api/flashcards*`, `/api/disciplinas*`, `/api/aulas*`, `/api/jobs`, `/api/batch-jobs*`, `/api/concursos*`, `/api/q*`, `/api/q/guias*`, `/api/billing*`). Nenhuma pode faltar.

- [ ] **Step 4:** `./dev.sh test -q` verde (58).

- [ ] **Step 5: Commit + deploy** (deploy só após aprovação do dono — o controller decide):
```bash
git add backend/main.py
git commit -m "refactor(domains): main.py vira entrypoint fino (app via platform_core)"
```

---

## Self-Review

- **Cobertura do spec (§10 domain system):** `platform_core/app.py` (factory + registry) ✓ (Task 1); `domains/<x>/router.py` para system, billing, questoes, guias, flashcards, disciplinas, concursos ✓ (Tasks 1-7); `main.py` fino ✓ (Task 8). Módulos compartilhados ficam na raiz (decisão consciente de baixo-churn; mover para `platform_core/db,auth,ai` é refinamento futuro, não-bloqueante).
- **Sem mudança de comportamento:** cada task move código verbatim e roda a suíte de 58 testes (Postgres) como guarda; a Task 8 faz verificação explícita de paridade de rotas.
- **Placeholders:** os corpos dos endpoints NÃO são repetidos aqui de propósito — eles são **relocados verbatim** do `main.py`/routers existentes; cada task diz exatamente quais rotas mover e quais imports levar.
- **Risco conhecido:** um endpoint movido pode referenciar um helper definido inline no `main.py` (não importável). Se isso ocorrer, mover o helper junto para o `router.py` do domínio (ou para um `domains/<x>/services.py`) — a suíte/checagem de rotas acusa na hora.

## Notas

- Ordem segura: system → billing (menor) → questoes → guias → flashcards → disciplinas → concursos → limpeza. Os 3 primeiros movem arquivos já isolados; os demais extraem do `main.py`.
- `worker.py` (tasks TaskIQ) permanece na raiz neste plano; sua reorganização para `domains/<x>/tasks.py` + `platform_core/tasks/` entra no Plano 05 (broker NATS), junto com a troca de broker.
- Após o Plano 02, `models.py` segue como arquivo único; split por domínio é refinamento opcional posterior (alto churn, baixo retorno imediato).
