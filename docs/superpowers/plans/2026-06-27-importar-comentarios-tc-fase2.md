# Importar comentários do TC — Fase 2 (coleta em massa) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um botão admin no card do caderno dispara um job durável (NATS/ledger) que varre todas as questões do caderno e importa os comentários do TC (alunos+professor), reusando 100% o endpoint da Fase 1, com delay 5–15s por questão e progresso/pausa no painel `/q/coletar`.

**Architecture:** Job no scraper espelhando a coleta de questões: novo `kind='comentarios'` em `tc_jobs` + tabela `tc_comentario_units` (1 unit/questão). O worker, por unit, chama o endpoint da Fase 1 no backend (`POST /api/q/questoes/{id}/importar-comentarios-tc?quadro=`) via DNS interno + token de serviço — sem reimplementar upsert/re-host. Cada unit concluída enfileira a próxima (chain); o supervisor recupera units bloqueadas.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), TaskIQ + NATS JetStream + asyncpg + httpx (scraper), Postgres (ledger), React 19 + TanStack Query (frontend).

## Global Constraints

- **Copy do frontend:** nenhuma string visível ao usuário cita "TC"/"TecConcursos"/"tec". Botão = **"💬 Importar"**; o botão de gabarito muda de **"↓ TEC"** para **"↓ Desempenho"**.
- **Delay anti-bot:** `random.uniform(5.0, 15.0)` segundos **por questão**, aplicado **só após uma chamada que realmente bateu no TC** (endpoint devolveu `ja_importado=false`). Se ambos os quadros já estavam importados, sem sleep.
- **Reuso total da Fase 1:** o worker NÃO reimplementa upsert/re-host/marcador — chama o endpoint da Fase 1. Unidade = 1 questão, cobre os 2 quadros (alunos+professores).
- **Admin-only:** disparar a coleta em massa exige admin (`require_admin`); o botão só aparece para admin no front.
- **Auth de serviço:** o worker autentica no backend com header `X-Internal-Token: $STUDIA_INTERNAL_TOKEN` (segredo forte, injetado pelo build.sh). O endpoint da Fase 1 passa a aceitar **sessão de usuário OU** esse token.
- **Idempotência:** marcador `QuestaoTcImport` (Fase 1) + `tc_comentario_id` unique; lazy e massa convergem.
- **Testes:** backend no container (`docker exec studia-backend-dev python -m pytest ...`); scraper no venv (`cd services/scraper && .venv/bin/python -m pytest ...`). Bare `python` não existe no host.
- TDD, commits frequentes, DRY, YAGNI.

---

### Task 1: Ledger — schema `tc_comentario_units` + `kind='comentarios'`

**Files:**
- Modify: `services/scraper/app/tasks/ledger.py` (constante `LEDGER_DDL`, ~L13-114)
- Test: `services/scraper/tests/test_comentario_ledger_schema.py`

**Interfaces:**
- Produces: tabela `tc_comentario_units(id, job_id FK tc_jobs, caderno_id, questao_id, status, task_id, attempts, coments_alunos, coments_professores, http_status, block_reason, blocked_until, last_error, leased_until, created_at, updated_at, finished_at, UNIQUE(job_id, questao_id))` + índices; índice único de job ativo para `kind='comentarios'`.

- [ ] **Step 1: Teste — ensure_ledger_schema cria a tabela**

```python
# services/scraper/tests/test_comentario_ledger_schema.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.tasks.ledger import ensure_ledger_schema

@pytest.mark.asyncio
async def test_cria_tc_comentario_units():
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
            r = await conn.execute(text(
                "SELECT to_regclass('public.tc_comentario_units')"))
            assert r.scalar() is not None
            cols = (await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='tc_comentario_units'"))).scalars().all()
            assert {"job_id","caderno_id","questao_id","status",
                    "coments_alunos","coments_professores","blocked_until"} <= set(cols)
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd services/scraper && .venv/bin/python -m pytest tests/test_comentario_ledger_schema.py -v`
Expected: FAIL (`to_regclass` retorna None — tabela não existe).
(Se o venv não conectar no Postgres dev, rode no container do scraper: `docker exec studia-scraper-dev python -m pytest tests/test_comentario_ledger_schema.py -v`.)

- [ ] **Step 3: Adicionar DDL** — em `LEDGER_DDL`, após o bloco de `tc_caderno_units` (depois da L72), inserir:

```sql

CREATE UNIQUE INDEX IF NOT EXISTS uq_tc_jobs_active_comentarios
ON tc_jobs (kind, external_id)
WHERE kind = 'comentarios' AND status IN ('pending', 'running', 'blocked');

CREATE TABLE IF NOT EXISTS tc_comentario_units (
  id BIGSERIAL PRIMARY KEY,
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  caderno_id BIGINT NOT NULL,
  questao_id BIGINT NOT NULL,
  status TEXT NOT NULL,
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  coments_alunos INTEGER NOT NULL DEFAULT 0,
  coments_professores INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER,
  block_reason TEXT,
  blocked_until TIMESTAMPTZ,
  last_error TEXT,
  leased_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  UNIQUE (job_id, questao_id)
);

CREATE INDEX IF NOT EXISTS idx_tc_comentario_units_job_status
ON tc_comentario_units (job_id, status, questao_id);

CREATE INDEX IF NOT EXISTS idx_tc_comentario_units_blocked_until
ON tc_comentario_units (status, blocked_until);
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd services/scraper && .venv/bin/python -m pytest tests/test_comentario_ledger_schema.py -v` (ou via container)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/tasks/ledger.py services/scraper/tests/test_comentario_ledger_schema.py
git commit -m "feat(scraper): ledger schema tc_comentario_units (kind=comentarios)"
```

---

### Task 2: Ledger — funções de job/unit de comentários

Espelham as funções de caderno do MESMO arquivo. Leia cada função-modelo citada e adapte: troque `tc_caderno_units`→`tc_comentario_units`, a chave de unit `(caderno_id, inicio, page_size)`→`(job_id, questao_id)`, os contadores `questoes_ok/novas/atualizadas`→`coments_alunos/coments_professores`, e `kind='caderno'`→`kind='comentarios'`.

**Files:**
- Modify: `services/scraper/app/tasks/ledger.py`
- Test: `services/scraper/tests/test_comentario_ledger_fns.py`

**Interfaces:**
- Consumes: `CadernoJob` dataclass (reusa; L117), `ensure_ledger_schema` (Task 1).
- Produces:
  - `async def upsert_comentario_job(session, *, caderno_id: int, questao_ids: list[int], requested_by: int | None) -> CadernoJob` — cria/atualiza job `kind='comentarios'`, `external_id=str(caderno_id)`, `total_units=len(questao_ids)`; insere 1 unit/questão (status `'pending'`) via `ON CONFLICT (job_id, questao_id) DO NOTHING`; usa `pg_advisory_xact_lock` como o upsert de caderno (L138).
  - `async def list_enqueueable_comentario_units(session, *, caderno_id: int, limit: int | None = None) -> list[dict]` — units `pending|failed`, ou `blocked` com `blocked_until <= now()`, ou `running` com `leased_until < now()`; ordena por `questao_id`; cada dict tem `unit_id, questao_id, status, block_reason`.
  - `async def lease_comentario_unit(session, *, caderno_id: int, questao_id: int, ack_wait_seconds: int) -> dict | None` — UPDATE CAS → `running` + `leased_until=now()+ack`; retorna `{unit_id, job_id}` ou None.
  - `async def mark_comentario_unit_done(session, *, unit_id: int, job_id: int, coments_alunos: int, coments_professores: int) -> None` — status `done`, grava contadores, chama `refresh_comentario_job_status`.
  - `async def mark_comentario_unit_blocked(session, *, unit_id, job_id, reason, blocked_until, http_status=None) -> None` e `mark_comentario_unit_failed(session, *, unit_id, job_id, error, http_status=None) -> None`.
  - `async def refresh_comentario_job_status(session, *, job_id: int) -> None` — recomputa done/failed/blocked_units e deriva `tc_jobs.status` (mesma lógica CASE de `refresh_caderno_job_status`, L280, mas contando `tc_comentario_units`).
  - `async def list_active_comentario_jobs(session) -> list[CadernoJob]` — `kind='comentarios' AND status IN ('pending','running','blocked') AND paused_by_user IS NOT TRUE`.

- [ ] **Step 1: Teste das funções principais**

```python
# services/scraper/tests/test_comentario_ledger_fns.py
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.tasks.ledger import (
    ensure_ledger_schema, upsert_comentario_job,
    list_enqueueable_comentario_units, lease_comentario_unit,
    mark_comentario_unit_done, refresh_comentario_job_status,
)

@pytest.mark.asyncio
async def test_job_units_lifecycle():
    eng = create_async_engine(get_settings().database_url)
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S.begin() as s:
            job = await upsert_comentario_job(
                s, caderno_id=999001, questao_ids=[11, 12, 13], requested_by=None)
        assert job.total_units == 3
        async with S.begin() as s:
            units = await list_enqueueable_comentario_units(s, caderno_id=999001, limit=10)
        assert len(units) == 3
        async with S.begin() as s:
            leased = await lease_comentario_unit(
                s, caderno_id=999001, questao_id=11, ack_wait_seconds=300)
        assert leased is not None
        async with S.begin() as s:
            await mark_comentario_unit_done(
                s, unit_id=leased["unit_id"], job_id=job.id,
                coments_alunos=2, coments_professores=1)
            await refresh_comentario_job_status(s, job_id=job.id)
        async with S.begin() as s:
            restantes = await list_enqueueable_comentario_units(s, caderno_id=999001, limit=10)
        assert len(restantes) == 2  # uma concluída
    finally:
        await eng.dispose()
```

- [ ] **Step 2: Rodar e ver falhar** — `cd services/scraper && .venv/bin/python -m pytest tests/test_comentario_ledger_fns.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implementar as funções** mirrorando as de caderno (mesmo arquivo): `upsert_caderno_job` (L138), `list_enqueueable_caderno_units` (L383), `lease_caderno_unit` (L419), `mark_caderno_unit_done` (L591), `mark_caderno_unit_blocked` (L620), `mark_caderno_unit_failed` (L653), `refresh_caderno_job_status` (L280), `list_active_caderno_jobs` (L487). Aplique as substituições descritas no cabeçalho da Task. Para `upsert_comentario_job`, em vez de calcular faixas (`_planned_ranges`), itere `questao_ids` inserindo `(job_id, caderno_id, questao_id, 'pending')`.

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/tasks/ledger.py services/scraper/tests/test_comentario_ledger_fns.py
git commit -m "feat(scraper): ledger fns de job/unit de comentários (espelha caderno)"
```

---

### Task 3: Backend — auth de serviço (sessão OU token interno)

**Files:**
- Modify: `backend/q_router.py` (dependência + aplicar no endpoint `importar_comentarios_tc`)
- Test: `backend/tests/test_internal_token_auth.py`

**Interfaces:**
- Produces: `async def require_user_or_service(request, user_opt) -> CurrentUser | None` — retorna o usuário se houver sessão; senão, se `request.headers["X-Internal-Token"] == os.getenv("STUDIA_INTERNAL_TOKEN")` (e o env não for vazio), autoriza como serviço (retorna `None`); senão `HTTPException(401)`.
- O endpoint `POST /api/q/questoes/{id}/importar-comentarios-tc` passa a depender disso em vez de `require_user`.

- [ ] **Step 1: Teste**

```python
# backend/tests/test_internal_token_auth.py
import os, pytest
from models import Questao

@pytest.mark.asyncio
async def test_token_servico_autoriza(db_session, client_sem_auth, monkeypatch):
    monkeypatch.setenv("STUDIA_INTERNAL_TOKEN", "segredo123")
    db_session.add(Questao(id=70, id_externo=None))  # no-op, mas passa do auth
    await db_session.commit()
    # sem sessão + token correto → 200 (no-op por id_externo None)
    r = await client_sem_auth.post(
        "/api/q/questoes/70/importar-comentarios-tc?quadro=alunos",
        headers={"X-Internal-Token": "segredo123"})
    assert r.status_code == 200
    # sem sessão + token errado → 401
    r2 = await client_sem_auth.post(
        "/api/q/questoes/70/importar-comentarios-tc?quadro=alunos",
        headers={"X-Internal-Token": "errado"})
    assert r2.status_code == 401
```

(Use a fixture de client SEM autenticação. Veja `conftest.py`: `client` é autenticado; procure/instancie um `AsyncClient` sem o cookie de sessão — se não existir fixture, crie `client_sem_auth` no teste a partir do mesmo `app`/transport do `conftest`, sem `auth_state`. Ajuste o nome ao que existir.)

- [ ] **Step 2: Rodar e ver falhar** — `docker exec studia-backend-dev python -m pytest tests/test_internal_token_auth.py -v` → FAIL.

- [ ] **Step 3: Implementar a dependência** em `q_router.py` (perto dos outros deps de auth; reusa o `require_user_opt` que já existe na cadeia — confirmar o nome no arquivo de auth):

```python
import os as _os
from fastapi import Request

async def require_user_or_service(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_opt),
) -> CurrentUser | None:
    if user is not None:
        return user
    tok = _os.getenv("STUDIA_INTERNAL_TOKEN") or ""
    if tok and request.headers.get("X-Internal-Token") == tok:
        return None  # chamada de serviço (worker do scraper)
    raise HTTPException(401, "não autenticado")
```

Trocar a assinatura do endpoint `importar_comentarios_tc`:
`user: CurrentUser = Depends(require_user)` → `user: CurrentUser | None = Depends(require_user_or_service)`.
(O corpo do endpoint não usa `user` para nada específico do usuário — comentários TC são globais; confirme e, se usar `user.id` em algum log, trate `user is None`.)

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS. Rode também `tests/test_importar_comentarios_tc.py` para garantir que o caminho com sessão segue funcionando.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_internal_token_auth.py
git commit -m "feat(forum): auth de serviço (X-Internal-Token) no import de comentários"
```

---

### Task 4: Backend — endpoint admin que enfileira a coleta em massa

**Files:**
- Modify: `backend/q_router.py` (novo endpoint perto de `coletar`, ~L285)
- Test: `backend/tests/test_enqueue_comentarios_caderno.py`

**Interfaces:**
- Consumes: `require_admin`, `CadernoQuestoes`, `SCRAPER_URL`, `httpx`.
- Produces: `POST /api/q/cadernos/{caderno_id}/importar-comentarios-tc` → `{job_id, status, total_units, enqueued_units}`.

- [ ] **Step 1: Teste (mock do scraper enqueue)**

```python
# backend/tests/test_enqueue_comentarios_caderno.py
import pytest, httpx
import q_router
from models import CadernoQuestoes

@pytest.mark.asyncio
async def test_admin_enfileira_comentarios(db_session, client_admin, monkeypatch):
    db_session.add(CadernoQuestoes(id=300, owner_uid="u1", tc_caderno_id=42,
                                   question_ids=[11, 12, 13], total=3, nome="X"))
    await db_session.commit()
    captured = {}
    def handler(req):
        captured["url"] = str(req.url); captured["json"] = req.content
        return httpx.Response(200, json={"job_id": 9, "status": "running",
                                         "total_units": 3, "enqueued_units": 1})
    real = httpx.AsyncClient
    monkeypatch.setattr(q_router.httpx, "AsyncClient",
                        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    r = await client_admin.post("/api/q/cadernos/300/importar-comentarios-tc")
    assert r.status_code in (200, 202)
    assert r.json()["job_id"] == 9
    assert "enqueue/comentarios" in captured["url"]
```

(`client_admin` = client autenticado como admin; veja como `test_admin_usuarios.py` obtém um admin e reuse o mesmo helper/fixture. Ajuste os kwargs de `CadernoQuestoes` aos campos reais do model.)

- [ ] **Step 2: Rodar e ver falhar** — `docker exec studia-backend-dev python -m pytest tests/test_enqueue_comentarios_caderno.py -v` → FAIL (404).

- [ ] **Step 3: Implementar** (mirror do `coletar`, L285):

```python
@router.post("/cadernos/{caderno_id}/importar-comentarios-tc", status_code=status.HTTP_202_ACCEPTED)
async def importar_comentarios_caderno(
    caderno_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Enfileira a coleta em massa de comentários do caderno (admin)."""
    cad = (await db.execute(
        select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id)
    )).scalar_one_or_none()
    if cad is None:
        raise HTTPException(404, "caderno não encontrado")
    qids = list(cad.question_ids or [])
    if not qids:
        raise HTTPException(422, "caderno sem questões")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3, read=15, write=5, pool=20)
        ) as c:
            r = await c.post(f"{SCRAPER_URL}/enqueue/comentarios",
                             json={"caderno_id": caderno_id, "questao_ids": qids})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:300]}")
    job = r.json()
    return {"caderno_id": caderno_id, "job_id": job["job_id"], "status": job["status"],
            "total_units": job["total_units"], "enqueued_units": job["enqueued_units"]}
```

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_enqueue_comentarios_caderno.py
git commit -m "feat(forum): endpoint admin importar-comentarios-tc por caderno (enfileira job)"
```

---

### Task 5: Scraper — config de pacing + worker `coletar_comentarios_questao`

**Files:**
- Modify: `services/scraper/app/config.py` (2 settings)
- Create: `services/scraper/app/tasks/comentarios.py`
- Test: `services/scraper/tests/test_comentarios_worker.py`

**Interfaces:**
- Consumes: ledger fns (Task 2), `broker_studia_default`, `enqueue` (`app/tasks/enqueue.py`), settings.
- Produces: `@broker_studia_default.task async def coletar_comentarios_questao(questao_id: int, caderno_id: int) -> dict` e a função testável `async def _processar_unit_comentarios(questao_id: int, caderno_id: int, *, sleep=asyncio.sleep, post=None) -> dict` (injeção pra teste).

- [ ] **Step 1: Config** — em `app/config.py`, perto de `imprimir_pause_*` (L112): adicionar
```python
    comentario_pause_min: float = 5.0     # seg entre questões (mín) — simulação humana
    comentario_pause_max: float = 15.0    # seg entre questões (máx)
    backend_url: str = "http://studia-backend:8000"  # DNS interno do swarm
    studia_internal_token: str = ""       # header X-Internal-Token p/ chamar o backend
```

- [ ] **Step 2: Teste do worker (sem rede; injeta post+sleep)**

```python
# services/scraper/tests/test_comentarios_worker.py
import pytest
from app.tasks import comentarios as m

@pytest.mark.asyncio
async def test_pace_so_quando_bate_no_tc(monkeypatch):
    chamadas, sleeps = [], []
    async def fake_post(url, quadro):
        chamadas.append(quadro)
        # alunos já importado (sem TC), professores fez fetch (bateu no TC)
        return {"importados": 0 if quadro == "alunos" else 1,
                "ja_importado": quadro == "alunos"}
    async def fake_sleep(s): sleeps.append(s)
    # neutraliza o ledger (lease/mark) — testamos só a lógica de pacing/chamadas
    monkeypatch.setattr(m, "_lease", lambda **k: {"unit_id": 1, "job_id": 1})
    monkeypatch.setattr(m, "_mark_done", lambda **k: None)
    monkeypatch.setattr(m, "_enqueue_next", lambda **k: None)
    res = await m._processar_unit_comentarios(
        99, 1, sleep=fake_sleep, post=fake_post)
    assert chamadas == ["alunos", "professores"]
    assert len(sleeps) == 1            # dormiu só 1x (o quadro que bateu no TC)
    assert 5.0 <= sleeps[0] <= 15.0
    assert res["coments_professores"] == 1 and res["coments_alunos"] == 0
```

(Esta forma exige que `_processar_unit_comentarios` use hooks substituíveis `m._lease/_mark_done/_enqueue_next` e os parâmetros `sleep`/`post`. Estruture o módulo assim para ser testável sem DB/broker.)

- [ ] **Step 3: Rodar e ver falhar** — `cd services/scraper && .venv/bin/python -m pytest tests/test_comentarios_worker.py -v` → FAIL.

- [ ] **Step 4: Implementar o worker**

```python
# services/scraper/app/tasks/comentarios.py
"""Worker da coleta em massa de comentários: 1 unit = 1 questão (2 quadros).
Reusa o endpoint da Fase 1 no backend (não reimplementa upsert/re-host)."""
from __future__ import annotations
import asyncio, random
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.observability import get_logger
from app.tasks.brokers.studia import broker_studia_default
from app.tasks.enqueue import enqueue
from app.tasks.ledger import (
    ensure_ledger_schema, lease_comentario_unit, mark_comentario_unit_done,
    mark_comentario_unit_failed, list_enqueueable_comentario_units,
)

log = get_logger(__name__)
QUADROS = ("alunos", "professores")


async def _post_import(questao_id: int, quadro: str) -> dict[str, Any]:
    s = get_settings()
    url = f"{s.backend_url}/api/q/questoes/{questao_id}/importar-comentarios-tc?quadro={quadro}"
    headers = {"X-Internal-Token": s.studia_internal_token}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=180, write=10, pool=185)) as c:
        r = await c.post(url, headers=headers)
        r.raise_for_status()
        return r.json()


def _engine_session():
    eng = create_async_engine(get_settings().database_url)
    return eng, async_sessionmaker(eng, expire_on_commit=False)


async def _lease(*, caderno_id: int, questao_id: int) -> dict | None:
    eng, S = _engine_session()
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
        async with S.begin() as s:
            return await lease_comentario_unit(
                s, caderno_id=caderno_id, questao_id=questao_id, ack_wait_seconds=600)
    finally:
        await eng.dispose()


async def _mark_done(*, unit_id, job_id, coments_alunos, coments_professores) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await mark_comentario_unit_done(
                s, unit_id=unit_id, job_id=job_id,
                coments_alunos=coments_alunos, coments_professores=coments_professores)
    finally:
        await eng.dispose()


async def _mark_failed(*, unit_id, job_id, error) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await mark_comentario_unit_failed(s, unit_id=unit_id, job_id=job_id, error=error)
    finally:
        await eng.dispose()


async def _enqueue_next(*, caderno_id: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            units = await list_enqueueable_comentario_units(s, caderno_id=caderno_id, limit=1)
        for u in units:
            await enqueue(coletar_comentarios_questao, priority="default",
                          questao_id=u["questao_id"], caderno_id=caderno_id)
    finally:
        await eng.dispose()


async def _processar_unit_comentarios(
    questao_id: int, caderno_id: int, *, sleep=asyncio.sleep, post=_post_import,
) -> dict[str, Any]:
    leased = await _lease(caderno_id=caderno_id, questao_id=questao_id)
    if leased is None:
        return {"status": "skipped"}
    s = get_settings()
    counts = {"alunos": 0, "professores": 0}
    try:
        for quadro in QUADROS:
            res = await post(questao_id, quadro)
            counts[quadro] = int(res.get("importados") or 0)
            if not res.get("ja_importado"):  # bateu no TC → humaniza
                await sleep(random.uniform(s.comentario_pause_min, s.comentario_pause_max))
    except Exception as exc:  # noqa: BLE001 — registra e segue o chain
        await _mark_failed(unit_id=leased["unit_id"], job_id=leased["job_id"], error=str(exc)[:300])
        await _enqueue_next(caderno_id=caderno_id)
        log.warning("comentarios.unit.failed", questao_id=questao_id, erro=str(exc)[:120])
        return {"status": "failed"}
    await _mark_done(unit_id=leased["unit_id"], job_id=leased["job_id"],
                     coments_alunos=counts["alunos"], coments_professores=counts["professores"])
    await _enqueue_next(caderno_id=caderno_id)
    return {"status": "done", "coments_alunos": counts["alunos"],
            "coments_professores": counts["professores"]}


@broker_studia_default.task
async def coletar_comentarios_questao(questao_id: int, caderno_id: int) -> dict[str, Any]:
    return await _processar_unit_comentarios(questao_id, caderno_id)
```

- [ ] **Step 5: Rodar e ver passar** — `cd services/scraper && .venv/bin/python -m pytest tests/test_comentarios_worker.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add services/scraper/app/config.py services/scraper/app/tasks/comentarios.py services/scraper/tests/test_comentarios_worker.py
git commit -m "feat(scraper): worker coletar_comentarios_questao (reusa Fase 1, delay 5-15s só em fetch)"
```

---

### Task 6: Scraper — rota `POST /enqueue/comentarios`

**Files:**
- Modify: `services/scraper/app/main.py` (modelo + rota, perto de `enqueue_caderno` ~L297)
- Test: `services/scraper/tests/test_enqueue_comentarios_route.py`

**Interfaces:**
- Consumes: `upsert_comentario_job`, `list_enqueueable_comentario_units` (Task 2), `coletar_comentarios_questao` (Task 5), `enqueue`.
- Produces: `POST /enqueue/comentarios` body `{caderno_id:int, questao_ids:list[int], requested_by:int|null}` → `{job_id, status, total_units, enqueued_units}`.

- [ ] **Step 1: Teste (registro de rota + cria job)**

```python
# services/scraper/tests/test_enqueue_comentarios_route.py
from app.main import api

def test_rota_registrada():
    paths = [r.path for r in api.routes]
    assert "/enqueue/comentarios" in paths
```

- [ ] **Step 2: Rodar e ver falhar** — `cd services/scraper && .venv/bin/python -m pytest tests/test_enqueue_comentarios_route.py -v` → FAIL.

- [ ] **Step 3: Implementar** (mirror de `enqueue_caderno`, main.py L297):

```python
class EnqueueComentariosBody(BaseModel):
    caderno_id: int
    questao_ids: list[int]
    requested_by: int | None = None

@api.post("/enqueue/comentarios", response_model=EnqueueCadernoResponse)
async def enqueue_comentarios(body: EnqueueComentariosBody) -> EnqueueCadernoResponse:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.tasks.comentarios import coletar_comentarios_questao
    from app.tasks.enqueue import enqueue
    from app.tasks.ledger import (
        ensure_ledger_schema, get_caderno_job, list_enqueueable_comentario_units,
        upsert_comentario_job,
    )
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            job = await upsert_comentario_job(
                session, caderno_id=body.caderno_id,
                questao_ids=body.questao_ids, requested_by=body.requested_by)
            units = await list_enqueueable_comentario_units(
                session, caderno_id=body.caderno_id, limit=1)
        enqueued = 0
        for u in units:
            await enqueue(coletar_comentarios_questao, priority="default",
                          questao_id=u["questao_id"], caderno_id=body.caderno_id)
            enqueued += 1
        async with Session.begin() as session:
            job = await get_caderno_job(session, job_id=job.id)
        return EnqueueCadernoResponse(job_id=job.id, status=job.status,
                                      total_units=job.total_units, enqueued_units=enqueued)
    finally:
        await engine.dispose()
```

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/main.py services/scraper/tests/test_enqueue_comentarios_route.py
git commit -m "feat(scraper): rota /enqueue/comentarios (cria job + enfileira 1ª unit)"
```

---

### Task 7: Scraper — supervisor recupera jobs de comentários

**Files:**
- Modify: `services/scraper/app/main.py` (`_queue_supervisor_loop`, ~L511-601)
- Test: `services/scraper/tests/test_supervisor_comentarios.py`

**Interfaces:**
- Consumes: `list_active_comentario_jobs`, `list_enqueueable_comentario_units` (Task 2), `coletar_comentarios_questao` (Task 5).

- [ ] **Step 1: Teste (a função de varredura enfileira units elegíveis)**

Extraia a lógica de comentários do loop para uma função pura testável `async def _supervisor_tick_comentarios(Session, enqueue_fn) -> int` que retorna quantas units enfileirou, e teste-a com um job ativo + units pending (semeadas via `upsert_comentario_job`), conferindo `enqueue_fn` chamado.

```python
# services/scraper/tests/test_supervisor_comentarios.py
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.tasks.ledger import ensure_ledger_schema, upsert_comentario_job
from app.main import _supervisor_tick_comentarios

@pytest.mark.asyncio
async def test_tick_enfileira_units_pendentes():
    eng = create_async_engine(get_settings().database_url)
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S.begin() as s:
            await upsert_comentario_job(s, caderno_id=999777, questao_ids=[1,2], requested_by=None)
        chamadas = []
        async def fake_enqueue(questao_id, caderno_id): chamadas.append((questao_id, caderno_id))
        n = await _supervisor_tick_comentarios(S, fake_enqueue)
        assert n >= 1 and len(chamadas) >= 1
    finally:
        await eng.dispose()
```

- [ ] **Step 2: Rodar e ver falhar** — `cd services/scraper && .venv/bin/python -m pytest tests/test_supervisor_comentarios.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implementar** — em `main.py`, adicionar a função pura e chamá-la dentro do `_queue_supervisor_loop` (junto do bloco que processa jobs de caderno):

```python
async def _supervisor_tick_comentarios(Session, enqueue_fn) -> int:
    from app.tasks.ledger import (
        list_active_comentario_jobs, list_enqueueable_comentario_units,
        refresh_comentario_job_status,
    )
    enfileiradas = 0
    async with Session.begin() as session:
        jobs = await list_active_comentario_jobs(session)
        for job in jobs:
            await refresh_comentario_job_status(session, job_id=job.id)
        jobs = await list_active_comentario_jobs(session)
    for job in jobs:
        async with Session.begin() as session:
            units = await list_enqueueable_comentario_units(
                session, caderno_id=job.caderno_id, limit=1)
        for u in units:
            await enqueue_fn(questao_id=u["questao_id"], caderno_id=job.caderno_id)
            enfileiradas += 1
    return enfileiradas
```

E no loop (`_queue_supervisor_loop`), após o bloco de caderno, antes do `log.info("queue_supervisor.tick", ...)`:

```python
            async def _eq(questao_id, caderno_id):
                from app.tasks.comentarios import coletar_comentarios_questao
                await enqueue(coletar_comentarios_questao, priority="default",
                              questao_id=questao_id, caderno_id=caderno_id)
            comentarios_enqueued = await _supervisor_tick_comentarios(Session, _eq)
```

(Inclua `comentarios_enqueued` no `log.info` do tick.)

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/main.py services/scraper/tests/test_supervisor_comentarios.py
git commit -m "feat(scraper): supervisor recupera units de jobs de comentários"
```

---

### Task 8: Backend — `GET /api/q/coletar/comentario-jobs` (progresso)

**Files:**
- Modify: `backend/q_router.py` (novo endpoint perto de `listar_jobs_coleta` ~L339)
- Test: `backend/tests/test_comentario_jobs_listagem.py`

**Interfaces:**
- Produces: `GET /api/q/coletar/comentario-jobs` → `{jobs: [{job_id, caderno_id, status, paused, total_units, done_units, failed_units, blocked_units, pending_units, running_units, pct_units_done, coments_total}]}` (admin).

- [ ] **Step 1: Teste**

```python
# backend/tests/test_comentario_jobs_listagem.py
import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_lista_jobs_comentarios(db_session, client_admin):
    # semeia um job de comentários + units direto no ledger
    await db_session.execute(text(
        "INSERT INTO tc_jobs (id, kind, status, source, external_id, total_units, done_units) "
        "VALUES (5001,'comentarios','running','tc','42',2,1)"))
    await db_session.execute(text(
        "INSERT INTO tc_comentario_units (job_id, caderno_id, questao_id, status, coments_alunos) "
        "VALUES (5001,42,11,'done',3),(5001,42,12,'pending',0)"))
    await db_session.commit()
    r = await client_admin.get("/api/q/coletar/comentario-jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    j = next(x for x in jobs if x["job_id"] == 5001)
    assert j["total_units"] == 2 and j["done_units"] == 1
    assert j["pending_units"] == 1 and j["pct_units_done"] == 50.0
```

(Garanta que o schema do ledger existe no banco de teste — o conftest pode não criar `tc_jobs`. Se necessário, no teste, rode `ensure_ledger_schema` equivalente via DDL `CREATE TABLE IF NOT EXISTS` ou pule com skip se a tabela não existir. Prefira criar as tabelas no setup do teste.)

- [ ] **Step 2: Rodar e ver falhar** — `docker exec studia-backend-dev python -m pytest tests/test_comentario_jobs_listagem.py -v` → FAIL (404).

- [ ] **Step 3: Implementar** (query mirror de `listar_jobs_coleta`, mas em `tc_comentario_units`):

```python
@router.get("/coletar/comentario-jobs")
async def listar_comentario_jobs(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Jobs de coleta de comentários para a UI acompanhar. (admin)"""
    rows = (await db.execute(text(
        """
        SELECT j.id AS job_id, CAST(j.external_id AS INTEGER) AS caderno_id,
               j.status, COALESCE(j.paused_by_user,false) AS paused,
               j.total_units, j.done_units, j.failed_units, j.blocked_units, j.updated_at,
               COALESCE(SUM(CASE WHEN u.status='pending' THEN 1 ELSE 0 END),0) AS pending_units,
               COALESCE(SUM(CASE WHEN u.status='queued'  THEN 1 ELSE 0 END),0) AS queued_units,
               COALESCE(SUM(CASE WHEN u.status='running' THEN 1 ELSE 0 END),0) AS running_units,
               COALESCE(SUM(u.coments_alunos + u.coments_professores),0) AS coments_total
        FROM tc_jobs j
        LEFT JOIN tc_comentario_units u ON u.job_id = j.id
        WHERE j.kind='comentarios'
          AND j.status IN ('pending','running','blocked','done')
        GROUP BY j.id, j.external_id, j.status, j.paused_by_user,
                 j.total_units, j.done_units, j.failed_units, j.blocked_units, j.updated_at
        ORDER BY j.updated_at DESC, j.id DESC
        """
    ))).mappings().all()
    jobs = []
    for r in rows:
        total = r["total_units"] or 0
        pct = round((r["done_units"] or 0) / total * 100, 2) if total else 0.0
        jobs.append({**{k: r[k] for k in (
            "job_id","caderno_id","status","paused","total_units","done_units",
            "failed_units","blocked_units","pending_units","queued_units",
            "running_units","coments_total")}, "pct_units_done": pct})
    return {"jobs": jobs}
```

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_comentario_jobs_listagem.py
git commit -m "feat(forum): GET coletar/comentario-jobs (progresso da coleta em massa)"
```

---

### Task 9: Frontend — botão admin no card + rename ↓TEC; lista no /q/coletar

**Files:**
- Modify: `fontend/app/q/cadernos/page.tsx` (botão + rename + estado)
- Modify: `fontend/app/q/coletar/page.tsx` (seção de jobs de comentários)
- Modify: `fontend/app/q/hooks/` (hook `useComentarioJobs` — arquivo onde vivem os hooks de coletar; criar se preciso)

**Interfaces:**
- Consumes: `POST /api/q/cadernos/{id}/importar-comentarios-tc` (Task 4), `GET /api/q/coletar/comentario-jobs` (Task 8).

- [ ] **Step 1: Botão no card + rename** — em `cadernos/page.tsx`:
  - Reusar o estado `importando` (já existe, L85) com uma chave separada, p.ex. `coletandoComents`.
  - Renomear o label do botão de gabarito: `{importando[c.id] ? "importando…" : "↓ TEC"}` → `"↓ Desempenho"` (e o `title` sem "TecConcursos": ex. "Importar acertos/erros do desempenho").
  - Adicionar, ao lado, **admin-only**, o botão de comentários:

```tsx
{ehAdmin && (
  <button
    onClick={() => importarComentarios(c.id)}
    disabled={coletandoComents[c.id]}
    title="Importar comentários da comunidade para todas as questões"
    className="text-fg-faint hover:text-primary disabled:opacity-50 opacity-0 group-hover:opacity-100 focus:opacity-100 transition whitespace-nowrap"
  >
    {coletandoComents[c.id] ? "coletando…" : "💬 Importar"}
  </button>
)}
```

  - `importarComentarios(id)`: set loading → `apiFetch('/api/q/cadernos/${id}/importar-comentarios-tc', {method:'POST'})` → on ok, `window.alert('Coleta iniciada em background. Acompanhe em Coletar.')` (ou toast existente) → unset loading. (Espelhe `importarDoTec`, L133.)
  - `ehAdmin`: obtenha o papel pelo MESMO mecanismo que o `Sidebar` usa para `adminOnly` (procure em `app/components/Sidebar.tsx` como ele decide admin — reuse o hook/sessão; o backend já é a barreira dura via `require_admin`).

- [ ] **Step 2: Hook + seção no /q/coletar** — adicionar `useComentarioJobs` (React Query, `GET /api/q/coletar/comentario-jobs`, `refetchInterval` 15s enquanto houver `running/queued/pending`) e renderizar uma seção **"Coleta de comentários"** com a mesma estrutura de card (barra usando `pct_units_done`, `X/total questões`, botão pausar/retomar reusando os endpoints `/api/q/coletar/jobs/{id}/pausar|retomar` que já são kind-agnósticos). Reuse `qk` adicionando `qk.comentarioJobs()`.

- [ ] **Step 3: Lint** — `cd fontend && pnpm lint` → 0 errors. Confirme: zero strings de UI com "TC"/"tec" (o "↓ Desempenho" substituiu o "↓ TEC").

- [ ] **Step 4: Verificação manual (dev)** — abra `/q/cadernos` como admin: o card mostra "↓ Desempenho" e "💬 Importar" no hover; clicar dispara e mostra "coletando…" + alerta; `/q/coletar` lista o job de comentários com progresso.

- [ ] **Step 5: Commit**

```bash
git add fontend/app/q/cadernos/page.tsx fontend/app/q/coletar/page.tsx fontend/app/q/hooks/
git commit -m "feat(forum): botão admin '💬 Importar' no card + rename ↓TEC→↓Desempenho + progresso no /q/coletar"
```

---

### Task 10: Deploy — secret + env do serviço

**Files:**
- Modify: `build.sh` (bloco do `.env` remoto: gerar/propagar `STUDIA_INTERNAL_TOKEN`; garantir `BACKEND_URL` para o scraper)
- Modify (se necessário): o compose/stack do scraper para passar `STUDIA_INTERNAL_TOKEN` e `BACKEND_URL` ao serviço scraper (e `STUDIA_INTERNAL_TOKEN` ao backend).

**Interfaces:**
- Produces: `STUDIA_INTERNAL_TOKEN` disponível no env do **backend** (lido por `require_user_or_service`) e do **scraper** (lido por `settings.studia_internal_token`); `BACKEND_URL` no env do scraper.

- [ ] **Step 1: Gerar/propagar o token** — em `build.sh`, perto de `STUDIA_JWT_SECRET` (L28-33), adicionar a mesma mecânica:

```bash
STUDIA_INTERNAL_TOKEN=""
[ -f "$ENV_FILE" ] && STUDIA_INTERNAL_TOKEN=$(grep -E '^STUDIA_INTERNAL_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)
[ -n "$STUDIA_INTERNAL_TOKEN" ] || STUDIA_INTERNAL_TOKEN=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
```

E no bloco que escreve o `.env` remoto (perto de `printf 'STUDIA_JWT_SECRET=%s\n' ...`):

```bash
  printf 'STUDIA_INTERNAL_TOKEN=%s\n' "$STUDIA_INTERNAL_TOKEN"
  echo "BACKEND_URL=http://studia-backend:8000"
```

- [ ] **Step 2: Conferir consumo no stack** — confirme que o serviço **scraper** e o **backend** recebem o `/opt/studia/.env` (mesmo `env_file`/`--env-file`). Se o scraper usa outro arquivo de env, replique `STUDIA_INTERNAL_TOKEN` e `BACKEND_URL` lá. Confirme o nome interno do serviço backend no compose (`studia-backend`) — ajuste `BACKEND_URL` se for outro.

- [ ] **Step 3: Verificação** (pós-deploy, não destrutiva):
  - `ssh ... 'docker exec <scraper-task> python -c "from app.config import get_settings as g; s=g(); print(bool(s.studia_internal_token), s.backend_url)"'` → `True http://studia-backend:8000`.
  - `curl -s -o /dev/null -w "%{http_code}" -X POST https://studia.witdev.com.br/api/q/questoes/5/importar-comentarios-tc?quadro=alunos -H "X-Internal-Token: <wrong>"` → 401.

- [ ] **Step 4: Commit**

```bash
git add build.sh
git commit -m "chore(deploy): STUDIA_INTERNAL_TOKEN + BACKEND_URL no env (worker→backend)"
```

---

## Deploy (após todas as tasks verdes)

```bash
cd /home/wital/studia && git push && ./build.sh
```

`db_prepare` não cria as tabelas do ledger (são do scraper, via `ensure_ledger_schema` em runtime) — o `enqueue/comentarios` chama `ensure_ledger_schema` antes de usar, então as tabelas nascem no primeiro disparo. Smoke pós-deploy: disparar a coleta num caderno pequeno (ex.: o de 4 questões) e ver no `/q/coletar` o job de comentários progredir; conferir comentários populando nas questões.

## Self-Review (preenchido)

**Spec coverage:** kind=comentarios + tc_comentario_units (T1) ✅ · ledger fns (T2) ✅ · worker reusa Fase 1 + delay 5–15s só em fetch (T5) ✅ · auth de serviço (T3) ✅ · enqueue admin por caderno (T4) ✅ · rota scraper enqueue (T6) ✅ · supervisor (T7) ✅ · progresso /q/coletar (T8+T9) ✅ · botão admin no card + rename ↓Desempenho + copy sem "TC" (T9) ✅ · segredo/env (T10) ✅. Casos de borda do spec (caderno vazio→422/0 units; id_externo None→no-op no endpoint; job ativo duplicado→índice único; pausa; token errado→401) cobertos por T4/T1/T3.

**Placeholder scan:** sem TBD/TODO. As funções longas do ledger (T2) referenciam a função-modelo de caderno por `arquivo:linha` com a lista exata de substituições — é adaptação de código existente que o implementer lê, não placeholder. Pontos a confirmar no ambiente (nome de fixtures `client_admin`/`client_sem_auth`, nome do serviço backend no compose, mecanismo admin do Sidebar) estão sinalizados explicitamente em cada task.

**Type consistency:** `questao_ids: list[int]` (T2/T4/T6) consistente; `coments_alunos/coments_professores` idênticos em DDL (T1), ledger (T2), worker (T5), listagem (T8); `coletar_comentarios_questao(questao_id, caderno_id)` mesma assinatura em T5/T6/T7; `require_user_or_service` (T3) usado em T3; `/enqueue/comentarios` body idêntico em T4 (cliente) e T6 (servidor).
