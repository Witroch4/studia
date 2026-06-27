# Coleta em massa — UX (pausa real + observabilidade + toast + retry) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar a coleta em massa de comentários controlável e legível: pausar para de verdade (e retoma de onde parou), o painel mostra um feed de eventos + ritmo/ETA, o disparo usa toast (sem alert/prompt nativo), e 5xx transitório não vira "Falha".

**Architecture:** Scraper (worker + ledger) ganha checagem de pausa por questão + retry de 5xx; backend expõe eventos por job; frontend mostra feed/ETA e troca alert/prompt por toast/dialog. Reusa os padrões do worker/ledger de caderno e os componentes de UI existentes.

**Tech Stack:** SQLAlchemy async (ledger Postgres), TaskIQ (worker), FastAPI (backend), React 19 + TanStack Query + sonner (frontend).

## Global Constraints

- **Copy:** nenhuma string de UI cita "TC"/"TecConcursos"/"tec". Toast/dialog com texto neutro.
- **Pausa:** ao pausar, o worker solta a unit em voo para `pending` e NÃO enfileira a próxima; retomar continua da primeira `pending` (questões `done` nunca refeitas). O setter de pausa precisa funcionar para `kind='comentarios'` (hoje é restrito a `'caderno'`).
- **Retry 5xx:** no worker, POST ao backend que retorna 5xx tenta de novo (2 retries, backoff ~3s) ANTES de marcar `failed`; 4xx falha na hora.
- **Testes:** backend e ledger no container (`docker exec studia-backend-dev …` / `docker exec studia-scraper-dev …` — precisam de Postgres); worker puro no venv (`cd services/scraper && .venv/bin/python -m pytest …`); frontend `cd fontend && pnpm lint`. Bare `python` não existe no host.
- O hotfix `isolated_broker=True` (commit `4e8dca5`) JÁ está em prod — fora do escopo deste plano.
- TDD, commits frequentes, DRY, YAGNI.

---

### Task 1: Ledger — pausa/release de comentários + setter kind-agnóstico

**Files:**
- Modify: `services/scraper/app/tasks/ledger.py`
- Test: `services/scraper/tests/test_comentario_pause_ledger.py`

**Interfaces:**
- Produces:
  - `async def is_comentario_paused(session, *, caderno_id: int) -> bool` (job ativo `kind='comentarios'`, `paused_by_user`).
  - `async def release_comentario_unit_to_pending(session, *, unit_id: int) -> None` (UPDATE `tc_comentario_units` → `pending`, limpa lease).
  - `set_caderno_job_paused` passa a operar em QUALQUER job por id (remove o filtro `AND kind = 'caderno'`), para pausar/retomar também jobs de comentários.

- [ ] **Step 1: Teste**

```python
# services/scraper/tests/test_comentario_pause_ledger.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.tasks.ledger import (
    ensure_ledger_schema, upsert_comentario_job, lease_comentario_unit,
    is_comentario_paused, release_comentario_unit_to_pending, set_caderno_job_paused,
)

@pytest.mark.asyncio
async def test_pause_release_comentarios():
    eng = create_async_engine(get_settings().database_url)
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
            await c.execute(text("DELETE FROM tc_jobs WHERE kind='comentarios' AND external_id='999500'"))
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S.begin() as s:
            job = await upsert_comentario_job(s, caderno_id=999500, questao_ids=[1, 2], requested_by=None)
        # set_caderno_job_paused funciona p/ job de comentários (era kind=caderno só)
        async with S.begin() as s:
            ok = await set_caderno_job_paused(s, job_id=job.id, paused=True)
        assert ok is True
        async with S.begin() as s:
            assert await is_comentario_paused(s, caderno_id=999500) is True
        # lease + release volta pra pending
        async with S.begin() as s:
            leased = await lease_comentario_unit(s, caderno_id=999500, questao_id=1, ack_wait_seconds=300)
        async with S.begin() as s:
            await release_comentario_unit_to_pending(s, unit_id=leased["unit_id"])
        async with S.begin() as s:
            st = (await s.execute(text("SELECT status FROM tc_comentario_units WHERE id=:i"),
                                  {"i": leased["unit_id"]})).scalar_one()
        assert st == "pending"
    finally:
        await eng.dispose()
```

- [ ] **Step 2: Rodar e ver falhar** — `docker exec studia-scraper-dev python -m pytest tests/test_comentario_pause_ledger.py -v` → FAIL (ImportError / setter retorna False p/ comentarios).

- [ ] **Step 3: Implementar** em `ledger.py`:

Remover o filtro de kind no setter (perto da L552):
```python
            UPDATE tc_jobs
            SET paused_by_user = :paused, updated_at = now()
            WHERE id = :job_id
```
(antes era `WHERE id = :job_id AND kind = 'caderno'`).

Adicionar (perto de `is_caderno_paused`/`release_unit_to_pending`):
```python
async def is_comentario_paused(session: AsyncSession, *, caderno_id: int) -> bool:
    """True se o job ativo de comentários deste caderno está pausado."""
    row = (
        await session.execute(
            text(
                """
                SELECT paused_by_user FROM tc_jobs
                WHERE kind = 'comentarios' AND external_id = :cid
                  AND status IN ('pending', 'running', 'blocked')
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"cid": str(caderno_id)},
        )
    ).scalar_one_or_none()
    return bool(row)


async def release_comentario_unit_to_pending(session: AsyncSession, *, unit_id: int) -> None:
    """Devolve uma unit de comentários em voo pra 'pending' (sem perder progresso)."""
    await session.execute(
        text(
            """
            UPDATE tc_comentario_units
            SET status = 'pending', leased_until = NULL, task_id = NULL, updated_at = now()
            WHERE id = :unit_id
            """
        ),
        {"unit_id": unit_id},
    )
```

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/tasks/ledger.py services/scraper/tests/test_comentario_pause_ledger.py
git commit -m "feat(scraper): pausa de comentários no ledger (is_comentario_paused + release + setter kind-agnóstico)"
```

---

### Task 2: Worker — checa pausa por questão + retry de 5xx transitório

**Files:**
- Modify: `services/scraper/app/tasks/comentarios.py`
- Test: `services/scraper/tests/test_comentarios_worker_pause_retry.py`

**Interfaces:**
- Consumes: `is_comentario_paused`, `release_comentario_unit_to_pending` (Task 1).
- Produces: hooks `_is_paused`/`_release` (substituíveis em teste); `_processar_unit_comentarios` retorna `{"status":"paused"}` quando pausado (sem POST, sem `_enqueue_next`); `_post_import` faz retry em 5xx.

- [ ] **Step 1: Teste (pausa não posta/não encadeia; retry de 5xx)**

```python
# services/scraper/tests/test_comentarios_worker_pause_retry.py
import pytest, httpx
from app.tasks import comentarios as m

@pytest.mark.asyncio
async def test_pausa_solta_unit_e_para(monkeypatch):
    posts, released, enq = [], [], []
    monkeypatch.setattr(m, "_lease", lambda **k: {"unit_id": 9, "job_id": 1})
    monkeypatch.setattr(m, "_is_paused", lambda **k: True)
    monkeypatch.setattr(m, "_release", lambda **k: released.append(k["unit_id"]))
    monkeypatch.setattr(m, "_mark_done", lambda **k: None)
    monkeypatch.setattr(m, "_enqueue_next", lambda **k: enq.append(1))
    async def fake_post(q, quadro): posts.append(quadro); return {"importados": 0}
    res = await m._processar_unit_comentarios(50, 1, sleep=lambda *_: None, post=fake_post)
    assert res["status"] == "paused"
    assert posts == [] and released == [9] and enq == []  # não bateu no TC, soltou, não encadeou

@pytest.mark.asyncio
async def test_post_retry_5xx(monkeypatch):
    monkeypatch.setattr(m, "get_settings", lambda: type("S", (), {
        "backend_url": "http://b", "studia_internal_token": "t",
        "comentario_pause_min": 0.0, "comentario_pause_max": 0.0})())
    chamadas = {"n": 0}
    def handler(req):
        chamadas["n"] += 1
        return httpx.Response(502) if chamadas["n"] == 1 else httpx.Response(200, json={"importados": 2, "ja_importado": False})
    monkeypatch.setattr(m.httpx, "AsyncClient",
                        lambda *a, **k: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    out = await m._post_import(50, "alunos", _sleep=lambda *_: None)
    assert out["importados"] == 2 and chamadas["n"] == 2  # 1 retry após o 502
```

- [ ] **Step 2: Rodar e ver falhar** — `cd services/scraper && .venv/bin/python -m pytest tests/test_comentarios_worker_pause_retry.py -v` → FAIL.

- [ ] **Step 3: Implementar** em `comentarios.py`:

Hooks novos (perto de `_lease`/`_mark_done`):
```python
async def _is_paused(*, caderno_id: int) -> bool:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            return await is_comentario_paused(s, caderno_id=caderno_id)
    finally:
        await eng.dispose()


async def _release(*, unit_id: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await release_comentario_unit_to_pending(s, unit_id=unit_id)
    finally:
        await eng.dispose()
```
(adicione os imports `is_comentario_paused, release_comentario_unit_to_pending` no bloco `from app.tasks.ledger import (...)`.)

Checagem de pausa em `_processar_unit_comentarios`, logo após o `if leased is None:`:
```python
    if await _call(_self._is_paused, caderno_id=caderno_id):
        await _call(_self._release, unit_id=leased["unit_id"])
        return {"status": "paused"}  # solta a unit e NÃO encadeia
```

Retry de 5xx em `_post_import` (assinatura ganha `_sleep` injetável p/ teste):
```python
async def _post_import(questao_id: int, quadro: str, *, _sleep: Any = asyncio.sleep) -> dict[str, Any]:
    s = get_settings()
    url = f"{s.backend_url}/api/q/questoes/{questao_id}/importar-comentarios-tc?quadro={quadro}"
    headers = {"X-Internal-Token": s.studia_internal_token}
    ultimo: Exception | None = None
    for tentativa in range(3):  # 1 + 2 retries
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=180, write=10, pool=185)) as c:
            r = await c.post(url, headers=headers)
            if r.status_code < 500:
                r.raise_for_status()  # 4xx → falha imediata
                return r.json()
            ultimo = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
        if tentativa < 2:
            await _sleep(3.0)
    raise ultimo  # 5xx persistente após retries
```

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS (2 testes). Rode também o teste antigo do worker (`tests/test_comentarios_worker.py`) p/ garantir retrocompat.

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/tasks/comentarios.py services/scraper/tests/test_comentarios_worker_pause_retry.py
git commit -m "feat(scraper): worker de comentários checa pausa (solta unit, para cadeia) + retry de 5xx transitório"
```

---

### Task 3: Backend — eventos por job + enriquecer jobs (created/updated/atual)

**Files:**
- Modify: `backend/q_router.py` (`listar_comentario_jobs` ~L631 + novo endpoint)
- Test: `backend/tests/test_comentario_eventos.py`

**Interfaces:**
- Produces:
  - `listar_comentario_jobs` passa a incluir, por job: `created_at` (ISO), `updated_at` (ISO), `questao_atual` (`questao_id` de uma unit `running`/`queued`, ou null).
  - `GET /api/q/coletar/comentario-jobs/{job_id}/eventos?limit=20` (admin) → `{eventos: [{questao_id, id_externo, status, coments_alunos, coments_professores, block_reason, last_error, updated_at}]}` por `updated_at desc`.

- [ ] **Step 1: Teste**

```python
# backend/tests/test_comentario_eventos.py
import pytest
from sqlalchemy import text

async def _ledger(db):
    await db.execute(text("CREATE TABLE IF NOT EXISTS tc_jobs (id BIGINT PRIMARY KEY, kind TEXT, status TEXT, source TEXT, external_id TEXT, total_units INT DEFAULT 0, done_units INT DEFAULT 0, failed_units INT DEFAULT 0, blocked_units INT DEFAULT 0, paused_by_user BOOLEAN DEFAULT false, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())"))
    await db.execute(text("CREATE TABLE IF NOT EXISTS tc_comentario_units (id BIGSERIAL PRIMARY KEY, job_id BIGINT, caderno_id BIGINT, questao_id BIGINT, status TEXT, coments_alunos INT DEFAULT 0, coments_professores INT DEFAULT 0, block_reason TEXT, last_error TEXT, updated_at TIMESTAMPTZ DEFAULT now())"))

@pytest.mark.asyncio
async def test_eventos_e_questao_atual(db_session, client):
    await _ledger(db_session)
    await db_session.execute(text("INSERT INTO tc_jobs (id,kind,status,source,external_id,total_units,done_units) VALUES (7001,'comentarios','running','tc','74',2,1)"))
    await db_session.execute(text("INSERT INTO tc_comentario_units (job_id,caderno_id,questao_id,status,coments_alunos) VALUES (7001,74,1934,'done',5),(7001,74,1935,'running',0)"))
    await db_session.commit()
    j = next(x for x in (await client.get("/api/q/coletar/comentario-jobs")).json()["jobs"] if x["job_id"] == 7001)
    assert j["questao_atual"] == 1935 and j["updated_at"] is not None
    ev = (await client.get("/api/q/coletar/comentario-jobs/7001/eventos?limit=10")).json()["eventos"]
    assert any(e["questao_id"] == 1934 and e["coments_alunos"] == 5 for e in ev)
```

- [ ] **Step 2: Rodar e ver falhar** — `docker exec studia-backend-dev python -m pytest tests/test_comentario_eventos.py -v` → FAIL (KeyError `questao_atual` / 404 eventos).

- [ ] **Step 3: Implementar** em `q_router.py`:

No SELECT de `listar_comentario_jobs`, adicionar ao SELECT e ao GROUP BY `j.created_at, j.updated_at`, e uma coluna:
```sql
               (SELECT u2.questao_id FROM tc_comentario_units u2
                 WHERE u2.job_id = j.id AND u2.status IN ('running','queued')
                 ORDER BY u2.updated_at DESC LIMIT 1) AS questao_atual,
```
E no dict de saída (no `jobs.append`), incluir:
```python
            "questao_atual": r["questao_atual"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
```

Novo endpoint após `listar_comentario_jobs`:
```python
@router.get("/coletar/comentario-jobs/{job_id}/eventos")
async def comentario_job_eventos(
    job_id: int, limit: int = 20,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Últimas units (eventos) de um job de comentários, p/ o feed da UI. (admin)"""
    limit = max(1, min(limit, 50))
    rows = (await db.execute(text(
        """
        SELECT u.questao_id, q.id_externo, u.status, u.coments_alunos,
               u.coments_professores, u.block_reason, u.last_error, u.updated_at
        FROM tc_comentario_units u
        LEFT JOIN questoes q ON q.id = u.questao_id
        WHERE u.job_id = :job_id
        ORDER BY u.updated_at DESC
        LIMIT :lim
        """
    ), {"job_id": job_id, "lim": limit})).mappings().all()
    eventos = [{
        "questao_id": r["questao_id"], "id_externo": r["id_externo"],
        "status": r["status"], "coments_alunos": r["coments_alunos"],
        "coments_professores": r["coments_professores"],
        "block_reason": r["block_reason"], "last_error": r["last_error"],
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    } for r in rows]
    return {"eventos": eventos}
```

- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS. Rode `tests/test_comentario_jobs_listagem.py` p/ retrocompat.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_comentario_eventos.py
git commit -m "feat(forum): eventos por job de comentários + questao_atual/created_at/updated_at no resumo"
```

---

### Task 4: Frontend — feed de detalhes + ritmo/ETA + última atualização

**Files:**
- Modify: `fontend/app/q/coletar/page.tsx`
- Modify: `fontend/lib/queryKeys.ts` (ou onde fica `qk`) — `comentarioEventos(jobId)`

**Interfaces:**
- Consumes: `GET /api/q/coletar/comentario-jobs/{id}/eventos` + os campos novos do resumo (Task 3).

- [ ] **Step 1: Tipos + hook de eventos** — em `coletar/page.tsx`:
  - `interface ComentarioJob` ganha: `created_at: string | null; updated_at: string | null; questao_atual: number | null;`
  - `interface ComentarioEvento { questao_id: number; id_externo: number | null; status: string; coments_alunos: number; coments_professores: number; block_reason: string | null; last_error: string | null; updated_at: string | null; }`
  - Hook:
```tsx
function useComentarioEventos(jobId: number | null, ativo: boolean) {
  return useQuery({
    queryKey: ["q", "comentario-eventos", jobId],
    enabled: jobId != null,
    refetchInterval: ativo ? 15000 : false,
    queryFn: async () => {
      const r = await apiFetch(`/api/q/coletar/comentario-jobs/${jobId}/eventos?limit=15`, { cache: "no-store" });
      if (!r.ok) throw new Error("falha");
      return (await r.json()).eventos as ComentarioEvento[];
    },
  });
}
```

- [ ] **Step 2: Render do feed + ETA + última atualização** — no card de cada job de comentários:
  - Botão "ver detalhes" (toggle por `job_id` em `useState<Record<number,boolean>>`).
  - Quando aberto: `useComentarioEventos(job.job_id, job ativo)` e renderiza:
    - **Questão atual**: `job.questao_atual ? \`Processando Q#${job.questao_atual}\` : "—"`.
    - **Ritmo + ETA** (helper puro):
```tsx
function ritmoEta(job: ComentarioJob): string {
  if (!job.created_at || job.done_units <= 0) return "—";
  const min = (Date.now() - new Date(job.created_at).getTime()) / 60000;
  if (min <= 0) return "—";
  const qpm = job.done_units / min;
  if (qpm <= 0) return "—";
  const restantes = Math.max(0, job.total_units - job.done_units);
  const etaMin = restantes / qpm;
  const h = Math.floor(etaMin / 60), mm = Math.round(etaMin % 60);
  return `${qpm.toFixed(1)} q/min · ~${h > 0 ? `${h}h ` : ""}${mm}m restantes`;
}
```
    - **Feed** (lista das units): cada evento como
      `Q#{id_externo ?? questao_id} · +{coments_alunos}/{coments_professores} · {ícone} · {hora}`
      com ícone por status (`done→✓`, `pending/queued→…`, `running→▶`, `blocked→⛔`, `failed→✗`) e `block_reason`/`last_error` em vermelho quando houver.
    - **Última atualização**: `job.updated_at ? new Date(job.updated_at).toLocaleString("pt-BR") : "—"` (substitui o "-" atual no rodapé do card).
  - Texto neutro, sem "TC"/"tec".

- [ ] **Step 3: Lint** — `cd fontend && pnpm lint` → 0 errors. Grep confirmando zero "TC"/"tec" em texto novo visível.

- [ ] **Step 4: Verificação manual (dev/prod)** — abrir `/q/coletar` com job de comentários ativo; "ver detalhes" mostra feed + ritmo/ETA + última atualização preenchida.

- [ ] **Step 5: Commit**

```bash
git add fontend/app/q/coletar/page.tsx fontend/lib/queryKeys.ts
git commit -m "feat(forum): feed de eventos + ritmo/ETA + última atualização no painel de coleta de comentários"
```

---

### Task 5: Toast (sonner) no lugar do alert nativo

**Files:**
- Modify: `fontend/package.json` (dep `sonner`)
- Modify: `fontend/app/layout.tsx` (`<Toaster />`)
- Modify: `fontend/app/q/cadernos/page.tsx` (trocar `window.alert`)

**Interfaces:**
- Produces: `toast` disponível no app (sonner); `cadernos/page.tsx` sem `window.alert`.

- [ ] **Step 1: Instalar sonner + Toaster no layout**

```bash
cd fontend && pnpm add sonner
```
Em `app/layout.tsx`, importar e renderizar dentro do `<body>` (após `<AppShell>`):
```tsx
import { Toaster } from "sonner";
// ... dentro do <body>, após {children}/AppShell:
        <Toaster position="top-right" richColors closeButton />
```

- [ ] **Step 2: Trocar os `window.alert` de `cadernos/page.tsx`** por toast:
```tsx
import { toast } from "sonner";
// importarComentarios:
toast.success("Coleta iniciada em background — acompanhe em Coletar.");
// catch:
toast.error(`Não foi possível iniciar a coleta: ${e instanceof Error ? e.message : e}`);
// importarDoTec (sucesso): toast.success(<resumo do desempenho importado>)
// importarDoTec (catch): toast.error(`Não foi possível importar: ${...}`)
```
(O resumo do desempenho que hoje vai no `window.alert(...)` vira o texto do `toast.success`. Texto neutro, sem "TC"/"tec".)

- [ ] **Step 3: Lint** — `cd fontend && pnpm lint` → 0 errors. Confirmar que `cadernos/page.tsx` não tem mais `window.alert`.

- [ ] **Step 4: Commit**

```bash
git add fontend/package.json fontend/pnpm-lock.yaml fontend/app/layout.tsx fontend/app/q/cadernos/page.tsx
git commit -m "feat(ui): toast (sonner) no lugar do alert nativo na lista de cadernos"
```

---

### Task 6: Prompt do gabarito → input dialog bonito

**Files:**
- Create: `fontend/app/components/PromptDialog.tsx`
- Modify: `fontend/app/q/cadernos/page.tsx` (usar o dialog no lugar de `window.prompt`)

**Interfaces:**
- Produces: `<PromptDialog open, titulo, descricao, placeholder, onConfirm(valor), onCancel />` (controlado), reutilizando os primitivos de `components/ui/alert-dialog.tsx`.

- [ ] **Step 1: Componente `PromptDialog`** (reusa o alert-dialog existente + um `<input>`):
```tsx
// fontend/app/components/PromptDialog.tsx
"use client";
import { useState, useEffect } from "react";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";

interface Props {
  open: boolean; titulo: string; descricao?: string; placeholder?: string;
  onConfirm: (valor: string) => void; onCancel: () => void;
}
export function PromptDialog({ open, titulo, descricao, placeholder, onConfirm, onCancel }: Props) {
  const [valor, setValor] = useState("");
  useEffect(() => { if (open) setValor(""); }, [open]);
  return (
    <AlertDialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{titulo}</AlertDialogTitle>
          {descricao ? <AlertDialogDescription>{descricao}</AlertDialogDescription> : null}
        </AlertDialogHeader>
        <input autoFocus value={valor} placeholder={placeholder}
          onChange={(e) => setValor(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && valor.trim()) onConfirm(valor.trim()); }}
          className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-primary" />
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>Cancelar</AlertDialogCancel>
          <AlertDialogAction disabled={!valor.trim()} onClick={() => onConfirm(valor.trim())}>Confirmar</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```
(Confirme os nomes exportados em `components/ui/alert-dialog.tsx`; ajuste imports se diferirem. Se `AlertDialogAction` não aceitar `disabled`, troque por um `<button>` estilizado dentro do footer.)

- [ ] **Step 2: Usar no `cadernos/page.tsx`** — estado `{ aberto, cadernoId }` para o prompt do gabarito; o botão "↓ Desempenho" abre o dialog; `onConfirm(valor)` extrai o número (`valor.match(/(\d{4,})/)`) e segue o fluxo que hoje vem depois do `window.prompt`. Remover o `window.prompt`. Texto neutro: titulo "Importar desempenho", descricao "Cole a URL ou o ID do caderno de origem", placeholder "https://… ou 12345".

- [ ] **Step 3: Lint** — `cd fontend && pnpm lint` → 0 errors. Confirmar zero `window.prompt`/`window.alert` em `cadernos/page.tsx` e zero "TC"/"tec" em texto visível.

- [ ] **Step 4: Commit**

```bash
git add fontend/app/components/PromptDialog.tsx fontend/app/q/cadernos/page.tsx
git commit -m "feat(ui): prompt do gabarito vira input dialog (sem dialog nativo do navegador)"
```

---

## Deploy (após todas as tasks verdes)

```bash
cd /home/wital/studia && git push && ./build.sh
```
Sem migração nova (ledger é runtime). Smoke: pausar o job ativo em `/q/coletar` → confirmar que `Running`/`Queued` zeram e o job para (units `done` intactas); retomar → continua da próxima `pending`; abrir "ver detalhes" → feed + ETA + última atualização; disparar coleta no card → toast (sem alert nativo); botão "↓ Desempenho" → input dialog.

## Self-Review (preenchido)

**Spec coverage:** A pausa real (T1 ledger + setter kind-agnóstico, T2 worker checa+solta) ✅ · resume de onde parou (units `pending`, T1/T2) ✅ · B feed/ETA/última-atualização (T3 backend eventos+campos, T4 frontend) ✅ · C toast (T5) + prompt→dialog (T6) ✅ · D retry 5xx (T2 `_post_import`) ✅; isolated_broker fora de escopo (já em prod) ✅. Copy sem "TC" reforçada em T4/T5/T6.

**Placeholder scan:** sem TBD/TODO; todo passo tem código/cmd. Pontos a confirmar no ambiente (nomes exportados do `alert-dialog`, caminho de `qk`/queryKeys) sinalizados explicitamente.

**Type consistency:** `is_comentario_paused`/`release_comentario_unit_to_pending` (T1) usados em T2 com os mesmos nomes; campos `created_at/updated_at/questao_atual` (T3) consumidos em T4; `ComentarioEvento` shape idêntico entre endpoint (T3) e hook (T4); `_post_import(questao_id, quadro, *, _sleep)` consistente com a chamada em `_processar_unit_comentarios`.
