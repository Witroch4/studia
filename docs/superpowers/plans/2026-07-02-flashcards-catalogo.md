# Flashcards multi-usuário + catálogo público — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decks de flashcards com dono + catálogo público read-only com promoção pelo admin, cópia p/ acervo e mini-guia do formato .md.

**Architecture:** Espelha o padrão `Concurso.user_id + is_public` já existente. Rotas de deck passam de slug → id numérico (slug vira display; único por dono). Todos os endpoints ganham `require_user`.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic; Next.js 16 + React Query v5; pytest (fixtures `client`/`auth_state` de `tests/conftest.py`, users ADMIN_USER/USER_A/USER_B).

## Global Constraints

- Rodar testes: `docker run --rm --network minha_rede -v <worktree>/backend:/app -w /app -e SCRAPER_URL=http://scraper:8090 studia-backend python -m pytest tests/... -q`
- UI: React Query obrigatório, `<Skeleton>` reservando espaço, nunca estado-vazio durante pending (CLAUDE.md).
- Falha pré-existente conhecida (ignorar): `test_admin_billing::test_cancelar_sem_assinatura_400`.
- `test_alembic_no_drift.py` precisa passar (models == migrações).
- Copy da UI em pt-BR. Head alembic atual: `d5e6f7a8b9c0`.

---

### Task 1: Migração + models (dono, catálogo, promoção, slug por dono)

**Files:**
- Create: `backend/alembic/versions/e7a8b9c0d1f2_decks_dono_e_catalogo.py`
- Modify: `backend/models.py:45-57` (Deck)
- Test: `tests/test_alembic_no_drift.py` (existente) + `tests/test_decks_catalogo.py` (novo, só modelo)

**Interfaces:**
- Produces: `Deck.user_id: str|None`, `Deck.is_public: bool`, `Deck.permitir_promocao: bool`; constraint `uq_decks_user_slug (user_id, slug)`; slug SEM unique global.

- [ ] Migração (upgrade): add colunas `user_id String(64) NULL` (+index), `is_public Boolean NOT NULL server_default false`, `permitir_promocao Boolean NOT NULL server_default true`; `UPDATE decks SET is_public = true`; `op.drop_index("ix_decks_slug")` + recria não-único; `op.create_unique_constraint("uq_decks_user_slug", "decks", ["user_id", "slug"])`. (Conferir nome real do index/constraint de slug no baseline antes de dropar.)
- [ ] Models: espelhar colunas no `Deck` (`default=False/True` + `server_default`).
- [ ] Rodar `tests/test_alembic_no_drift.py` → PASS. Commit.

### Task 2: Escopo de leitura + auth (GET decks / cards / todos / DELETE)

**Files:**
- Modify: `backend/main.py:211-295` (list_decks, delete_deck, get_all_cards, get_deck_cards)
- Test: `tests/test_decks_catalogo.py`

**Interfaces:**
- Produces:
  - `GET /api/decks` → `{meus: DeckOut[], catalogo: DeckOut[], usuarios?: {dono:{id,nome,email}, decks: DeckOut[]}[]}`; `DeckOut = {id:int, slug, nome, icon, icon_color, total:int, revisar:int, pct:int, publico:bool, permitir_promocao:bool, meu:bool, pode_excluir:bool}`. `catalogo` exclui os meus públicos (aparecem em `meus` com badge). `usuarios` só p/ admin (decks de outros users; `user_id NULL` = dono `{id:"", nome:"Sistema", email:""}`), nomes via `SELECT id, name, email FROM "user" WHERE id IN :ids` (padrão guias_router.py:370).
  - `GET /api/flashcards/deck/{deck_id:int}` → dono|público|admin; shape atual `{deck_id, deck_nome, total, cards[]}` + `{publico, meu, somente_leitura:bool}`. Rota antiga por slug REMOVIDA.
  - `GET /api/flashcards/todos` → só cards do user (decks `user_id == user.id`).
  - `DELETE /api/decks/{deck_id:int}` → dono ou admin (403 senão).
- Testes-chave (todos com `client`, trocando `auth_state["user"]`):

```python
async def test_user_nao_ve_deck_privado_de_outro(client, auth_state): ...
async def test_catalogo_visivel_a_todos(client, auth_state): ...
async def test_admin_ve_secao_usuarios(client, auth_state): ...
async def test_todos_so_do_usuario(client, auth_state): ...
async def test_delete_deck_de_outro_403(client, auth_state): ...
```

- [ ] Testes → FAIL; implementar; PASS; commit.

### Task 3: Escrita escopada (create, import, impedir_promocao)

**Files:**
- Modify: `backend/main.py:304-331` (create) e `:334+` (import)
- Test: `tests/test_flashcards_import.py` (adaptar p/ auth) + novos casos

**Interfaces:**
- Produces:
  - `POST /api/flashcards` body `{tema, assunto, frente, verso, impedir_promocao?: bool=false}` → deck do user por `(user_id, slug)`; deck novo recebe `permitir_promocao = not impedir_promocao`. Retorna também `deck_id` numérico.
  - `POST /api/flashcards/import` Form `file` + `impedir_promocao: bool = Form(False)` → idem; dedup mantém (deck+frente+verso) DENTRO dos decks do user.
- Testes: import de A não vaza p/ B (mesmo slug → decks distintos); `impedir_promocao=true` grava `permitir_promocao=false` só em deck NOVO; dedup continua (2 imports = skipped).

- [ ] Testes → FAIL; implementar; PASS; commit.

### Task 4: Promover / despromover / copiar / PATCH

**Files:**
- Modify: `backend/main.py` (novos endpoints após delete_deck)
- Test: `tests/test_decks_catalogo.py`

**Interfaces:**
- Produces:
  - `POST /api/decks/{id}/promover` (admin; 404; 409 `permitir_promocao=false`) → `{ok, publico:true}`
  - `POST /api/decks/{id}/despromover` (admin) → `{ok, publico:false}`
  - `PATCH /api/decks/{id}` body `{impedir_promocao: bool}` (só dono; 403 admin/others). `impedir_promocao=true` num deck público também seta `is_public=false`.
  - `POST /api/decks/{id}/copiar` (deck público ou meu; 403 privado alheio) → clona deck (user_id=eu, is_public=false, permitir_promocao=true, slug com sufixo `-2`,`-3`… se colidir) + cards (assunto/frente/verso). Retorna `{id, slug, nome, total}`.
- Testes: promover como user comum → 403; promover impedido → 409; PATCH por admin → 403; PATCH impedir num público despromove; copiar deck público por B → B tem clone com N cards; copiar privado de A por B → 403; copiar 2× → slug `-2`.

- [ ] Testes → FAIL; implementar; PASS; commit.

### Task 5: Frontend /flashcards (Meus + Catálogo + admin)

**Files:**
- Modify: `fontend/app/flashcards/page.tsx`
- Create: `fontend/app/components/CatalogoDeckCard.tsx` (card read-only + Copiar) — admin section inline na page.

**Interfaces:**
- Consumes: `GET /api/decks` novo shape; mutations `POST /api/decks/{id}/copiar|promover|despromover`, `DELETE /api/decks/{id}`.
- `DeckData` vira `{id:number; slug:string; nome; total; revisar; pct; publico; permitir_promocao; meu; pode_excluir}`; links usam `deck.id`.

- [ ] Seção "Meus Baralhos" (grid atual; badge 🌐 "No catálogo" quando `publico`); seção "Catálogo público" (`CatalogoDeckCard`: estudar → `/flashcards/{id}`, botão "Copiar pro meu acervo" com estado pending/sucesso → invalidate `qk.decks()`); seção admin "Baralhos dos usuários" (agrupado por dono, botão Promover/Remover do catálogo; desabilitado + title quando `!permitir_promocao`). Skeletons por seção; nenhum contador/estado-vazio antes de `!isPending`.
- [ ] `pnpm lint` → PASS. Commit.

### Task 6: Frontend /flashcards/novo (checkbox + mini-guia)

**Files:**
- Create: `fontend/app/components/FlashcardGuiaMd.tsx` (padrão visual exato de `ConcursoGuiaCsv.tsx`: botão accordion + tabela + exemplo `<pre>`)
- Modify: `fontend/app/flashcards/novo/page.tsx`

- [ ] Guia: formato `Flashcard: Tema: Assunto` / `Frente:` / `Verso:`; tabela de tags (`<atencao>`, `<destaque>`, `<resumo>`) + markdown/LaTeX; exemplo copiável; nota de tolerâncias (labels em negrito, `(Tema:)`, CRLF, reimporte não duplica).
- [ ] Checkbox "Impedir promoção ao catálogo público" (default desmarcado, texto auxiliar "O admin não poderá publicar este conteúdo para outros usuários") no form individual (body JSON) e no import (FormData `impedir_promocao`).
- [ ] `pnpm lint` → PASS. Commit.

### Task 7: Frontend estudo por id + read-only

**Files:**
- Modify: `fontend/app/flashcards/[id]/page.tsx` (+ `page.tsx` prefetch já ajustado na Task 5)

- [ ] Fetch `GET /api/flashcards/deck/{id}` (numérico; manter `todos` na rota especial). Se `somente_leitura`, esconder qualquer ação de escrita/exclusão na tela de estudo.
- [ ] `pnpm lint` + suíte backend completa → PASS (exceto billing pré-existente). Commit.

### Task 8: Integração e deploy

- [ ] Suíte inteira + `pnpm lint`; merge `main` (checkout principal, sem switch), push, `./build.sh`; smoke em prod: `GET /api/decks` sem cookie → 401; catálogo com 25 decks públicos legados visível logado; worktree removido.
