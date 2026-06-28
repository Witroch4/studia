# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Usuário fala Português BR. Responda em português.

## Workflow OBRIGATÓRIO ao fim de qualquer alteração

Toda alteração de código DEVE terminar com este ciclo completo, nesta ordem —
não é opcional, não espere o usuário pedir:

1. **Commit** com mensagem pertinente (escopo + porquê), agrupada por intenção.
2. **Push** para `origin/main` (`git push`).
3. **Deploy em produção** com `./build.sh` (build + push de imagens + `db_prepare`
   + `docker stack deploy`). Para só Meili: `./build.sh --reindex`.
4. **Worktree limpo** ao final (`git status` sem pendências).

### Autorização permanente de SSH de produção (automode)

O usuário autoriza **qualquer uso de SSH em produção** (`root@49.13.155.94`,
chave `~/.ssh/keys/production-server.key`) para operações **não-destrutivas**
(leitura/diagnóstico: `docker ps`, `docker service ls`, `docker logs`, `psql`
com `SELECT`, `curl`, etc.) **e** para o fluxo de deploy padrão via `./build.sh`.
NÃO são autorizados sem confirmação explícita: `DROP`/`DELETE`/`TRUNCATE` em
prod, remoção de volumes/stacks, `--seed-data` (sobrescreve banco de prod).

Produção se auto-ajusta: o backend roda `python -m scripts.db_prepare` no startup
(migra schema + verifica + aplica settings do Meili). Qualquer deploy leva o
schema ao dia sozinho; se não puder, o container falha visível (nunca 500 mudo).

### PROIBIDO trocar a branch do checkout principal (regra rígida)

O diretório `/home/wital/studia` é o checkout que o **VSCode do usuário usa** e onde
os containers de dev estão montados. **NUNCA** rode `git checkout <branch>` /
`git switch` / `git checkout -b` que tire esse diretório da `main` — isso troca a
branch no editor do usuário e o trava ("local changes would be overwritten"). O
projeto é **baseado em `main`**: trabalhe **direto na `main`** (commits frequentes,
como manda o Workflow OBRIGATÓRIO acima).

Se precisar de isolamento (ex.: execução multi-task por subagentes), use um **git
worktree** em diretório separado (`.claude/worktrees/...` via a ferramenta de
worktree), **mantendo o checkout principal sempre na `main`** — e depois faça merge.
Jamais alternar a branch do checkout principal por conta própria. Voltar PARA a
`main` (corrigir um desvio) é permitido; sair dela, não.

## Quick Start

```bash
./dev.sh          # Start dev (backend:8000 + frontend:3000) with logs
./dev.sh up:d     # Start in background
./dev.sh down     # Stop
./dev.sh build    # Rebuild images + run migrations
./dev.sh migrate  # Run migrations manually
./dev.sh logs     # View logs
./dev.sh shell backend   # Shell into backend container
./dev.sh shell frontend  # Shell into frontend container
```

Manual (without Docker):
```bash
# Backend
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd fontend && pnpm install && pnpm dev
```

## Lint / Test

```bash
cd fontend && pnpm lint    # ESLint (Next.js + TypeScript)

# Backend (pytest + pytest-asyncio + aiosqlite; testes em backend/tests/)
cd backend && python -m pytest tests/ -v
```

O backend tem suíte de testes em `backend/tests/` (pytest, fixtures em
`tests/conftest.py`, banco de teste via `TEST_DATABASE_URL`), incluindo um teste
de drift de migrations (`test_alembic_no_drift.py`). Não há linter configurado no
backend.

## Target Stack (Full Vision)

Tecnologias definidas para o projeto. Itens marcados com ✅ já estão implementados, 📋 são planejados.

### IA (O Diferencial)
- 📋 **LangGraph** — orquestração de agentes autônomos e fluxos cíclicos
- 📋 **LiteLLM** — gateway unificado multi-provider (OpenAI, Anthropic, Google) com fallback
- 📋 **text-embedding-3-small** (OpenAI) ou Gemini — embeddings para busca semântica

### Backend (Python Assíncrono)
- ✅ **Python 3.12+** / **FastAPI** / **SQLAlchemy 2.0 async** / **Pydantic v2**
- 📋 **Taskiq** — fila de tarefas assíncrona (substituto moderno do Celery)
- 📋 **Alembic** — migrações de banco de dados

### Frontend
- ✅ **Next.js 16 (App Router)** / **TypeScript** / **Tailwind CSS**
- 📋 **Shadcn/UI** — componentes reutilizáveis e acessíveis
- 📋 **TanStack Query (React Query)** — cache e estado assíncrono
- ✅ **Lucide React** — ícones (atualmente usa Material Icons via Google Fonts)

### Dados & Infra
- ✅ **PostgreSQL** / ✅ **Docker & Docker Compose**
- ✅ **pgvector** — busca semântica direto no Postgres (extensão habilitada via migrate.py)
- ✅ **Redis** — broker para Taskiq + cache

### Qualidade & Testes
- 📋 **Pytest** — testes backend
- 📋 **Playwright** — testes E2E
- 📋 **Hypothesis** — testes baseados em propriedades

## Architecture

**Frontend** (`/fontend` - typo is intentional): Next.js 16 + React 19 + TypeScript + Tailwind CSS 4
- App Router at `fontend/app/`
- `NEXT_PUBLIC_API_URL` env var points to backend (default: `http://localhost:8001`)
- All API calls use plain `fetch()` — migrar para TanStack Query quando implementar

**Backend** (`/backend`): FastAPI + SQLAlchemy async + PostgreSQL (asyncpg)
- `main.py` — all routes + CORS config
- `models.py` — SQLAlchemy models (Deck, Flashcard)
- `database.py` — async PostgreSQL session factory
- `parser.py` — regex-based markdown parser for flashcard import

**Docker** (`docker-compose.dev.yml`): All services self-contained. PostgreSQL (pgvector/pg17, host port 5433), Redis (host port 6380), MinIO, backend, worker, frontend. Network: `studia-net`.

**Migrations** (`backend/migrate.py`): Auto-detects missing columns and adds them via ALTER TABLE. Runs on every `./dev.sh build` and `./dev.sh up`.

## Key Routes

| Frontend Route | Purpose |
|---|---|
| `/` | Dashboard (mock data) |
| `/flashcards` | Deck library grid |
| `/flashcards/[id]` | Study mode (3D flip cards) |
| `/flashcards/novo` | Create individual + batch import from .md |

| Backend Endpoint | Purpose |
|---|---|
| `GET /api/decks` | List decks with card counts |
| `GET /api/flashcards/{deck_slug}` | Cards for a deck |
| `POST /api/flashcards` | Create single card |
| `POST /api/flashcards/import` | Upload .md file, parse & import |

## MarkdownRenderer Pipeline

`fontend/app/components/MarkdownRenderer.tsx` is the core rendering component:

1. **Preprocess**: regex converts custom XML tags to `data-tag` attributes
2. **Parse**: `react-markdown` with `remarkMath` + `rehypeRaw` + `rehypeKatex`
3. **Render**: custom component overrides apply tag-specific styling

Custom XML tags (only in card verso, never in frente):
- `<atencao>Title: text</atencao>` — red callout box
- `<destaque>text</destaque>` — inline cyan highlight
- `<resumo>text</resumo>` — centered cyan box (good for formulas)

## Flashcard Markdown Format

```
Flashcard: Tema: Assunto
Frente: question text
Verso:
answer text with **markdown**, $LaTeX$, and XML tags
```

- **Tema** → creates/reuses a deck (slugified)
- **Assunto** → tag on the card
- See `FLASHCARD_GUIDE.md` for full reference

## Color Theme

Defined in `fontend/app/globals.css`:
- Primary: `#06b6d4` (cyan) — main accent
- Secondary: `#8b5cf6` (violet)
- Background: `#121212` / Surface: `#1e1e1e` — dark theme only

## Environment Variables

```
# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8001

# Backend
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia
REDIS_URL=redis://redis:6379/1  # configured but not yet used
```
