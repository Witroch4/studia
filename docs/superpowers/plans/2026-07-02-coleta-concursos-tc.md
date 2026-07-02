# Coleta de Concursos do TC (edital/provas/gabarito → MinIO) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Buscar concursos no TC por filtros (Banca/Formação), baixar os arquivos (edital, provas, gabarito) para o MinIO e expor tudo numa tela admin `/q/concursos` — de forma idempotente.

**Architecture:** Novo `kind='concursos'` no ledger do scraper (descoberta paginada com sessão TC → units por concurso → download público do CDN → import de metadados no backend via `X-Internal-Token`). Backend ganha `TcConcurso`/`TcConcursoArquivo` + router `concursos_router.py`. Frontend ganha `/q/concursos` (React Query, padrão `/q/coletar`).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic; Taskiq/NATS (scraper); MinIO (bucket privado `studia-pdfs`); Next.js 16 + React Query v5.

**Spec:** `docs/superpowers/specs/2026-07-02-coleta-concursos-tc-design.md`

## Global Constraints

- Trabalhar num worktree `.claude/worktrees/coleta-concursos-tc`; NUNCA trocar a branch do checkout principal.
- Idempotência ponta-a-ponta: reenfileirar os mesmos filtros NÃO duplica jobs/units/linhas/binários.
- Bucket MinIO: `studia-pdfs` (privado), chave `concursos/{uuid}{ext}` (dedup de binário por uuid).
- Contrato TC (validado): `GET /api/concursos/busca-avancada` com `busca.geradorBuscaConcursoFiltros[i].id/.tipo` + `busca.pagina`; headers `X-Requested-With: XMLHttpRequest` e `Logado: true`; combos em `/api/concursos/busca-avancada/bancas|profissoes`; download público `https://cdn.tecconcursos.com.br/arquivos/{uuid}`.
- Proibido "TC"/"tec" visível na UI (usar "Concursos", "fonte externa").
- UI: React Query obrigatório; `Skeleton` p/ carga de banco; `BrandLoader` p/ operação lenta; dados não pulam na tela.
- Backend tests: `cd backend && python -m pytest tests/ -v` (inclui drift Alembic). Frontend: `cd fontend && pnpm lint`.
- Alembic: head atual `d5e6f7a8b9c0`.

---

### Task 1: Scraper — cliente/parser da busca de concursos

**Files:**
- Create: `services/scraper/app/scrapers/tc_concursos.py`
- Test: `services/scraper/tests/test_tc_concursos.py`

**Interfaces:**
- Produces:
  - `parse_busca_page(data: dict) -> list[dict]` — achata a página da busca em 1 dict por concurso: `{"concurso_id": int, "payload": {"concurso": {...}, "arquivos": [{"tipo","arquivo_id","uuid","nome_arquivo"}]}}`
  - `async fetch_busca_avancada(client: TcClient, filtros: list[dict], pagina: int) -> dict` — chama a API TC e devolve o JSON cru
  - `async fetch_filtros_busca(client: TcClient) -> dict` — `{"bancas": [...], "profissoes": [...]}`
  - `filtros_external_id(filtros: list[dict]) -> str` — id canônico do job, ex. `"BANCA:95|PROFISSAO:6"`

- [ ] **Step 1: Failing test com fixture real**

`services/scraper/tests/test_tc_concursos.py`:

```python
from app.scrapers.tc_concursos import filtros_external_id, parse_busca_page

PAGE = {
    "resultCount": 49, "currentPage": 1, "pageSize": 5, "totalPages": 10,
    "list": [
        {
            "edital": {
                "id": 19626, "nome": "Nº 01/2026, DE 21 DE MAIO DE 2026",
                "ano": 2026, "orgaoNome": "Assembleia Legislativa do Ceará",
                "orgaoSigla": "ALECE", "orgaoRegiao": "Estadual",
                "bancaSigla": "IDECAN",
                "bancaNome": "Instituto de Desenvolvimento Educacional...",
            },
            "concursos": [
                {
                    "concursoId": 174930, "editalId": 19626,
                    "dataAplicacao": "16/08/2026 00:00:00",
                    "escolaridade": "Superior", "bancaNome": "IDECAN",
                    "editalNome": "Nº 01/2026, DE 21 DE MAIO DE 2026",
                    "orgaoSigla": "ALECE",
                    "nomeCompleto": "Analista Legislativo (ALECE)/2026 - Engenharia - Civil",
                    "arquivosPorTipo": {
                        "EDITAL": [{"id": 452178, "nomeArquivo": "1.edital.pdf",
                                    "uuid": "af4483d1-650a-4d18-ac99-785cf983d926"}],
                        "PROVA_OBJETIVA": [{"id": 1, "nomeArquivo": "prova.pdf", "uuid": "u-prova"}],
                    },
                    "urlConcurso": "analista-legislativo-alece-engenharia-civil-2026",
                },
                # mesmo edital, segundo cargo SEM arquivos
                {"concursoId": 174931, "editalId": 19626, "nomeCompleto": "Outro cargo",
                 "urlConcurso": "outro-cargo-2026", "arquivosPorTipo": {}},
            ],
        }
    ],
}


def test_parse_busca_page_achata_concursos():
    units = parse_busca_page(PAGE)
    assert [u["concurso_id"] for u in units] == [174930, 174931]
    c = units[0]["payload"]["concurso"]
    assert c["nome_completo"].startswith("Analista Legislativo")
    assert c["url_concurso"] == "analista-legislativo-alece-engenharia-civil-2026"
    assert c["ano"] == 2026 and c["orgao_nome"].startswith("Assembleia")
    arqs = units[0]["payload"]["arquivos"]
    assert {a["tipo"] for a in arqs} == {"EDITAL", "PROVA_OBJETIVA"}
    assert arqs[0]["uuid"] and arqs[0]["arquivo_id"] and arqs[0]["nome_arquivo"]
    assert units[1]["payload"]["arquivos"] == []  # concurso sem arquivo é válido


def test_external_id_canonico_e_estavel():
    a = filtros_external_id([{"id": "6", "tipo": "PROFISSAO"}, {"id": "95", "tipo": "BANCA"}])
    b = filtros_external_id([{"id": 95, "tipo": "BANCA"}, {"id": 6, "tipo": "PROFISSAO"}])
    assert a == b == "BANCA:95|PROFISSAO:6"
```

- [ ] **Step 2: Rodar e ver falhar** — `cd services/scraper && python -m pytest tests/test_tc_concursos.py -v` → FAIL (módulo não existe).

- [ ] **Step 3: Implementar `app/scrapers/tc_concursos.py`**

```python
"""Busca avançada de concursos do TC + arquivos p/ download.

Contrato validado em 2026-07-02 (ver spec 2026-07-02-coleta-concursos-tc-design.md).
A busca exige sessão TC + headers XHR/Logado; o download dos arquivos é público
(cdn.tecconcursos.com.br/arquivos/{uuid}) e NÃO consome sessão.
"""
from __future__ import annotations

from typing import Any

from app.client import TcClient

BUSCA_PATH = "/api/concursos/busca-avancada"
XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "Logado": "true",
    "Referer": "https://www.tecconcursos.com.br/concursos?tipoBusca=buscaavancada",
}
CDN_ARQUIVO_URL = "https://cdn.tecconcursos.com.br/arquivos/{uuid}"


def filtros_external_id(filtros: list[dict]) -> str:
    partes = sorted(f"{f['tipo'].upper()}:{f['id']}" for f in filtros)
    return "|".join(partes)


def _params_busca(filtros: list[dict], pagina: int) -> dict[str, str]:
    params: dict[str, str] = {}
    for i, f in enumerate(filtros):
        params[f"busca.geradorBuscaConcursoFiltros[{i}].id"] = str(f["id"])
        params[f"busca.geradorBuscaConcursoFiltros[{i}].tipo"] = str(f["tipo"]).upper()
    params["busca.pagina"] = str(pagina)
    return params


async def fetch_busca_avancada(client: TcClient, filtros: list[dict], pagina: int) -> dict[str, Any]:
    r = await client.get(BUSCA_PATH, params=_params_busca(filtros, pagina), headers=XHR_HEADERS)
    return r.json()


async def fetch_filtros_busca(client: TcClient) -> dict[str, Any]:
    bancas = (await client.get(f"{BUSCA_PATH}/bancas", headers=XHR_HEADERS)).json()
    profissoes = (await client.get(f"{BUSCA_PATH}/profissoes", headers=XHR_HEADERS)).json()
    return {"bancas": bancas, "profissoes": profissoes}


def parse_busca_page(data: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for item in data.get("list") or []:
        edital = item.get("edital") or {}
        for c in item.get("concursos") or []:
            arquivos = [
                {
                    "tipo": tipo,
                    "arquivo_id": a["id"],
                    "uuid": a["uuid"],
                    "nome_arquivo": a.get("nomeArquivo") or a["uuid"],
                }
                for tipo, lst in (c.get("arquivosPorTipo") or {}).items()
                for a in (lst or [])
            ]
            units.append(
                {
                    "concurso_id": int(c["concursoId"]),
                    "payload": {
                        "concurso": {
                            "concurso_id_externo": int(c["concursoId"]),
                            "edital_id_externo": c.get("editalId") or edital.get("id"),
                            "nome_completo": c.get("nomeCompleto") or "",
                            "url_concurso": c.get("urlConcurso") or "",
                            "banca_nome": c.get("bancaNome") or edital.get("bancaSigla") or "",
                            "orgao_sigla": c.get("orgaoSigla") or edital.get("orgaoSigla") or "",
                            "orgao_nome": edital.get("orgaoNome") or "",
                            "edital_nome": c.get("editalNome") or edital.get("nome") or "",
                            "ano": edital.get("ano"),
                            "data_aplicacao": c.get("dataAplicacao"),
                            "escolaridade": c.get("escolaridade"),
                        },
                        "arquivos": arquivos,
                    },
                }
            )
    return units
```

Nota: conferir a assinatura real de `TcClient.get` em `app/client.py` (se não aceitar
`params=`/`headers=`, montar a URL com `httpx.QueryParams` e usar
`client._client.get(url, headers=XHR_HEADERS)` como fazem `tc_gabarito.py`/`tc_guia.py`).

- [ ] **Step 4: Testes passam** — `python -m pytest tests/test_tc_concursos.py -v` → PASS.
- [ ] **Step 5: Commit** — `git add … && git commit -m "feat(scraper): parser da busca avançada de concursos do TC"`

---

### Task 2: Scraper — ledger `kind='concursos'`

**Files:**
- Modify: `services/scraper/app/tasks/ledger.py` (DDL + funções no fim do arquivo)
- Test: `services/scraper/tests/test_ledger_concursos.py` (apenas o que não precisa de Postgres)

**Interfaces:**
- Produces (mesma família das funções `*_comentario_*`, trocando a âncora `caderno_id` por `job_id`):
  - DDL: tabela `tc_concurso_units` + índice único parcial `uq_tc_jobs_active_concursos`
  - `async upsert_concursos_job(session, *, external_id: str, filtros: list[dict], requested_by=None) -> CadernoJob`
  - `async upsert_concurso_units(session, *, job_id: int, units: list[dict]) -> int` (`units` = saída de `parse_busca_page`; ON CONFLICT DO UPDATE do payload)
  - `async list_enqueueable_concurso_units(session, *, job_id: int, limit=None) -> list[dict]`
  - `async lease_concurso_unit(session, *, job_id: int, concurso_id: int, ack_wait_seconds: int) -> dict | None`
  - `async mark_concurso_unit_done(session, *, unit_id, job_id, arquivos_ok: int)`
  - `async mark_concurso_unit_failed(session, *, unit_id, job_id, error: str)`
  - `async release_concurso_unit_to_pending(session, *, unit_id)`
  - `async is_concursos_paused(session, *, job_id: int) -> bool`
  - `async refresh_concursos_job_status(session, *, job_id)` / `refresh_concursos_job_counts`
  - `async set_concursos_job_discovery(session, *, job_id: int, status: str, error: str | None = None)` — grava `params['discovery']` (`running|done|failed`) p/ UI

- [ ] **Step 1: DDL** — acrescentar ao `LEDGER_DDL` (antes do fechamento da string), espelhando `tc_comentario_units` (ledger.py:78-103):

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_tc_jobs_active_concursos
ON tc_jobs (kind, external_id)
WHERE kind = 'concursos' AND status IN ('pending', 'running', 'blocked');

CREATE TABLE IF NOT EXISTS tc_concurso_units (
  id BIGSERIAL PRIMARY KEY,
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  concurso_id BIGINT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL,
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  arquivos_ok INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER,
  block_reason TEXT,
  blocked_until TIMESTAMPTZ,
  last_error TEXT,
  leased_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  UNIQUE (job_id, concurso_id)
);

CREATE INDEX IF NOT EXISTS idx_tc_concurso_units_job_status
ON tc_concurso_units (job_id, status, concurso_id);
```

- [ ] **Step 2: Funções** — copiar o bloco `upsert_comentario_job` → `_get_comentario_job` → `list_enqueueable_comentario_units` → `lease_comentario_unit` → `mark_*` → `release_*` → `is_comentario_paused` (ledger.py:762 em diante) adaptando: `kind='concursos'`; lock advisory `tc:concursos:{external_id}`; `params` do job = `jsonb` com `{"filtros": filtros, "discovery": "pending"}` (usar `CAST(:params AS jsonb)`); units keyed por `(job_id, concurso_id)`; `upsert_concurso_units` faz `INSERT ... ON CONFLICT (job_id, concurso_id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()` e retorna quantidade; `is_concursos_paused` lê `paused_by_user` de `tc_jobs WHERE id = :job_id`; `set_concursos_job_discovery` faz `UPDATE tc_jobs SET params = params || jsonb_build_object('discovery', :status, 'discovery_error', :error)`.

- [ ] **Step 3: Teste leve (sem Postgres)** — em `tests/test_ledger_concursos.py`, validar só que o DDL novo é splitável (mesma proteção do bug `;` em comentário):

```python
from app.tasks.ledger import LEDGER_DDL


def test_ddl_concursos_presente_e_splitavel():
    assert "tc_concurso_units" in LEDGER_DDL
    assert "uq_tc_jobs_active_concursos" in LEDGER_DDL
    stmts = "\n".join(l.split("--", 1)[0] for l in LEDGER_DDL.splitlines()).split(";")
    assert all("--" not in s for s in stmts)
```

- [ ] **Step 4: Rodar** — `python -m pytest tests/test_ledger_concursos.py -v` → PASS (e `python -m pytest tests/ -v` continua verde).
- [ ] **Step 5: Commit** — `feat(scraper): ledger kind=concursos (units por concurso)`

---

### Task 3: Scraper — tasks de descoberta e download

**Files:**
- Create: `services/scraper/app/tasks/concursos.py`
- Test: `services/scraper/tests/test_tasks_concursos.py`

**Interfaces:**
- Consumes: Task 1 (`fetch_busca_avancada`, `parse_busca_page`, `CDN_ARQUIVO_URL`), Task 2 (funções do ledger).
- Produces:
  - `@broker_studia_default.task async descobrir_concursos(job_id: int, filtros: list[dict])`
  - `@broker_studia_default.task async coletar_arquivos_concurso(job_id: int, concurso_id: int)`
  - `async _processar_unit_concurso(job_id, concurso_id, *, download=None, put_minio=None, stat_minio=None, post=None, sleep=...)` — núcleo testável com hooks monkeypatchável (mesmo desenho de `comentarios._processar_unit_comentarios`)
  - `_object_key(uuid: str, content_type: str | None, filename: str | None) -> str` → `concursos/{uuid}{ext}`

- [ ] **Step 1: Failing tests do núcleo** (hooks fake, sem DB/MinIO/rede):

```python
import asyncio
import app.tasks.concursos as mod


PAYLOAD = {
    "concurso": {"concurso_id_externo": 86869, "nome_completo": "X", "url_concurso": "x"},
    "arquivos": [
        {"tipo": "EDITAL", "arquivo_id": 1, "uuid": "u-1", "nome_arquivo": "edital.pdf"},
        {"tipo": "GABARITO", "arquivo_id": 2, "uuid": "u-2", "nome_arquivo": "gab.zip"},
    ],
}


def test_object_key_por_uuid():
    assert mod._object_key("u-1", "application/pdf", "edital.pdf") == "concursos/u-1.pdf"
    assert mod._object_key("u-2", "application/x-zip-compressed", "g.zip") == "concursos/u-2.zip"
    assert mod._object_key("u-3", None, None) == "concursos/u-3"


def test_unit_baixa_faz_upload_e_posta(monkeypatch):
    calls = {"download": [], "put": [], "post": []}
    monkeypatch.setattr(mod, "_lease", lambda **k: {"unit_id": 1, "job_id": 9, "payload": PAYLOAD})
    monkeypatch.setattr(mod, "_is_paused", lambda **k: False)
    monkeypatch.setattr(mod, "_stat_minio", lambda key: None)  # nada existe ainda
    monkeypatch.setattr(mod, "_download", lambda url: calls["download"].append(url)
                        or (b"%PDF", "application/pdf", "arquivo.pdf"))
    monkeypatch.setattr(mod, "_put_minio", lambda key, data, ct: calls["put"].append(key))
    monkeypatch.setattr(mod, "_post_import", lambda payload: calls["post"].append(payload) or {"ok": True})
    done = {}
    monkeypatch.setattr(mod, "_mark_done", lambda **k: done.update(k))
    monkeypatch.setattr(mod, "_enqueue_next", lambda **k: None)

    r = asyncio.run(mod._processar_unit_concurso(9, 86869, sleep=lambda s: None))
    assert r["status"] == "done"
    assert len(calls["download"]) == 2 and len(calls["put"]) == 2
    assert done["arquivos_ok"] == 2
    arqs = calls["post"][0]["arquivos"]
    assert arqs[0]["minio_object_key"] == "concursos/u-1.pdf"


def test_unit_pula_download_se_objeto_existe(monkeypatch):
    monkeypatch.setattr(mod, "_lease", lambda **k: {"unit_id": 1, "job_id": 9, "payload": PAYLOAD})
    monkeypatch.setattr(mod, "_is_paused", lambda **k: False)
    monkeypatch.setattr(mod, "_stat_minio",
                        lambda key: {"content_type": "application/pdf", "size": 10, "key": key + ".pdf"})
    baixou = []
    monkeypatch.setattr(mod, "_download", lambda url: baixou.append(url))
    monkeypatch.setattr(mod, "_put_minio", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_post_import", lambda payload: {"ok": True})
    monkeypatch.setattr(mod, "_mark_done", lambda **k: None)
    monkeypatch.setattr(mod, "_enqueue_next", lambda **k: None)
    r = asyncio.run(mod._processar_unit_concurso(9, 86869, sleep=lambda s: None))
    assert r["status"] == "done" and baixou == []  # idempotente: não re-baixa
```

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar `app/tasks/concursos.py`** — estrutura espelhada em `comentarios.py` (hooks `_lease/_mark_done/_mark_failed/_is_paused/_release/_enqueue_next` com `_engine_session()`, lookup via `import app.tasks.concursos as _self` p/ monkeypatch). Pontos específicos:

```python
# _stat_minio / _put_minio: cliente minio.Minio como em imagens._put_minio
# (app/tasks/imagens.py:400), MAS bucket privado os.environ["MINIO_PDF_BUCKET"]
# (default "studia-pdfs") e SEM policy pública.

_EXT_BY_CT = {"application/pdf": ".pdf", "application/zip": ".zip",
              "application/x-zip-compressed": ".zip"}

def _object_key(uuid, content_type, filename):
    import os as _os
    ext = _EXT_BY_CT.get((content_type or "").split(";")[0].strip().lower())
    if not ext and filename and "." in filename:
        ext = _os.path.splitext(filename)[1].lower()[:8] or None
    return f"concursos/{uuid}{ext or ''}"

def _download(url: str) -> tuple[bytes, str | None, str | None]:
    """GET público no CDN (sem cookies TC). Retorna (bytes, content_type, filename)."""
    import httpx, re
    with httpx.Client(timeout=httpx.Timeout(connect=10, read=300, write=30, pool=310),
                      follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"}) as c:
        r = c.get(url)
        r.raise_for_status()
        cd = r.headers.get("content-disposition") or ""
        m = re.search(r'filename="?([^\";]+)', cd)
        return r.content, r.headers.get("content-type"), (m.group(1) if m else None)

async def _post_import(payload: dict) -> dict:
    # POST {backend_url}/api/q/concursos/importar com X-Internal-Token,
    # 3 tentativas em 5xx (copiar _post_import de comentarios.py:37-58).
    ...
```

Núcleo `_processar_unit_concurso`: lease → paused? release e sai → para cada arquivo do payload: `key = _object_key(...)`; `_stat_minio` por PREFIXO `concursos/{uuid}` (listar `list_objects(bucket, prefix=...)` e usar o primeiro) — se existir, usa metadados do stat sem baixar; senão `_download(CDN_ARQUIVO_URL.format(uuid=...))` → `_put_minio(key, data, ct)` → `await sleep(random.uniform(1, 3))`. Monta payload de import `{"concurso": payload["concurso"], "arquivos": [... + minio_object_key/content_type/tamanho_bytes]}` → `_post_import` → `_mark_done(arquivos_ok=N)` → `_enqueue_next(job_id=...)`. Exceção → `_mark_failed` + `_enqueue_next` (nunca derruba o chain).

`descobrir_concursos(job_id, filtros)`: usa `select_tc_account_for_task(TC_TASK_GUIA)` + `load_cookies_for_httpx(account_id=...)` + `TcClient`; `set_concursos_job_discovery(status='running')`; loop `pagina=1..totalPages` (ler `totalPages` da 1ª resposta; teto rígido 100): `fetch_busca_avancada` → `parse_busca_page` → `upsert_concurso_units`; relogin 1x em `SessionExpired` (padrão `_with_tc_client` de main.py:282); ao final `set_concursos_job_discovery('done')`, `refresh_concursos_job_status`, atualizar `total_units` do job (`UPDATE tc_jobs SET total_units = (SELECT count(*) FROM tc_concurso_units WHERE job_id=:id)`) e enfileirar a 1ª unit (`list_enqueueable_concurso_units(limit=1)` → `enqueue(coletar_arquivos_concurso, isolated_broker=True, ...)`). Falha → `set_concursos_job_discovery('failed', error=...)` + `mark tc_jobs.status='failed'`.

- [ ] **Step 4: Testes passam** — `python -m pytest tests/test_tasks_concursos.py tests/ -v`.
- [ ] **Step 5: Commit** — `feat(scraper): tasks de descoberta e download de arquivos de concursos`

---

### Task 4: Scraper — endpoints `/enqueue/concursos` e `/tc/concursos/filtros` + supervisor

**Files:**
- Modify: `services/scraper/app/main.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `POST /enqueue/concursos` body `{"filtros": [{"id": 95, "tipo": "BANCA"}], "requested_by": null}` → `{"job_id", "status", "total_units", "enqueued_units"}` (202-like, síncrono e rápido: só upsert do job + enqueue da task de descoberta)
  - `GET /tc/concursos/filtros` → `{"bancas": [{"key","name"}...], "profissoes": [...]}`

- [ ] **Step 1: Implementar endpoints** (padrão `enqueue_comentarios` main.py:512-551):

```python
class EnqueueConcursosBody(BaseModel):
    filtros: list[dict[str, Any]]
    requested_by: int | None = None


@api.post("/enqueue/concursos", response_model=EnqueueCadernoResponse)
async def enqueue_concursos(body: EnqueueConcursosBody) -> EnqueueCadernoResponse:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.scrapers.tc_concursos import filtros_external_id
    from app.tasks.concursos import descobrir_concursos
    from app.tasks.enqueue import enqueue
    from app.tasks.ledger import ensure_ledger_schema, upsert_concursos_job

    if not body.filtros:
        raise HTTPException(422, "informe ao menos um filtro")
    try:
        select_tc_account_for_task(TC_TASK_GUIA, touch_usage=False)
    except NoEligibleTcAccount as exc:
        raise HTTPException(409, str(exc)) from exc
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            job = await upsert_concursos_job(
                session, external_id=filtros_external_id(body.filtros),
                filtros=body.filtros, requested_by=body.requested_by)
        await enqueue(descobrir_concursos, priority="default",
                      job_id=job.id, filtros=body.filtros)
        return EnqueueCadernoResponse(job_id=job.id, status=job.status,
                                      total_units=job.total_units, enqueued_units=1)
    finally:
        await engine.dispose()


@api.get("/tc/concursos/filtros")
async def tc_concursos_filtros() -> dict[str, Any]:
    from app.scrapers.tc_concursos import fetch_filtros_busca
    return await _with_tc_client(fetch_filtros_busca, task=TC_TASK_GUIA)
```

- [ ] **Step 2: Supervisor** — em `_queue_supervisor_loop` (main.py:697+), adicionar tick análogo ao de comentários: para cada job `kind='concursos'` ativo (`status IN ('pending','running','blocked')`, `paused_by_user = false`, `params->>'discovery' = 'done'`), pegar `list_enqueueable_concurso_units(limit=1)` e enfileirar `coletar_arquivos_concurso`. Copiar a função `_supervisor_tick_comentarios` como `_supervisor_tick_concursos` e registrá-la no loop.

- [ ] **Step 3: Sanidade local** — `python -m pytest tests/ -v` (sem teste novo aqui: endpoints são colagem fina; validação real no smoke de prod).
- [ ] **Step 4: Commit** — `feat(scraper): enqueue/concursos + filtros da busca + supervisor tick`

---

### Task 5: Backend — models `TcConcurso`/`TcConcursoArquivo` + migration

**Files:**
- Modify: `backend/models.py` (após `QuestaoTcImport`, models.py:743-760)
- Create: `backend/alembic/versions/a7c8d9e0f1b2_tc_concursos.py`
- Test: suíte existente `backend/tests/test_alembic_no_drift.py` (cobre o drift)

**Interfaces:**
- Produces (usados pela Task 6/7):

```python
class TcConcurso(Base):
    """Concurso coletado da fonte externa (busca avançada) — metadados + arquivos."""
    __tablename__ = "tc_concursos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    concurso_id_externo: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    edital_id_externo: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    nome_completo: Mapped[str] = mapped_column(Text)
    url_concurso: Mapped[str] = mapped_column(String(512))
    banca_nome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    orgao_sigla: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    orgao_nome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edital_nome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ano: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    data_aplicacao: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    escolaridade: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())
    arquivos: Mapped[list["TcConcursoArquivo"]] = relationship(
        back_populates="concurso", cascade="all, delete-orphan", lazy="selectin")


class TcConcursoArquivo(Base):
    """Arquivo (edital/prova/gabarito) de um concurso, já hospedado no MinIO."""
    __tablename__ = "tc_concurso_arquivos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    concurso_id: Mapped[int] = mapped_column(
        ForeignKey("tc_concursos.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(64))  # EDITAL | PROVA_OBJETIVA | ... (string da fonte)
    arquivo_id_externo: Mapped[int] = mapped_column(BigInteger)
    uuid: Mapped[str] = mapped_column(String(64), index=True)
    nome_arquivo: Mapped[str] = mapped_column(Text)
    minio_object_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tamanho_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    baixado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    concurso: Mapped["TcConcurso"] = relationship(back_populates="arquivos")
    __table_args__ = (
        UniqueConstraint("concurso_id", "arquivo_id_externo", name="uq_tc_concurso_arquivo"),
    )
```

- [ ] **Step 1: Adicionar models** (código acima; imports já existem no arquivo — conferir `JSON`, `Text`, `relationship`).
- [ ] **Step 2: Migration manual** `a7c8d9e0f1b2_tc_concursos.py` com `down_revision = "d5e6f7a8b9c0"` — copiar o formato de `d9f0a1b2c3e4_questao_tc_import.py`; `upgrade()` cria as duas tabelas (tipos idênticos aos models: `sa.BigInteger`, `sa.Text`, `sa.JSON`, FKs com `ondelete="CASCADE"`, unique constraints e índices `concurso_id_externo`, `uuid`, `concurso_id`); `downgrade()` dropa na ordem inversa.
- [ ] **Step 3: Rodar drift test** — `cd backend && python -m pytest tests/test_alembic_no_drift.py -v` → PASS.
- [ ] **Step 4: Commit** — `feat(backend): tabelas tc_concursos + tc_concurso_arquivos`

---

### Task 6: Backend — router `/api/q/concursos` (importar + listar + stream + coletar + jobs + filtros)

**Files:**
- Create: `backend/concursos_router.py`
- Modify: `backend/main.py` (registrar router — copiar como `guias_router` é incluído)
- Test: `backend/tests/test_concursos_router.py`

**Interfaces:**
- Consumes: models Task 5; `require_admin`, `require_user_or_service`, `get_db` (importar de `q_router`/`deps` conforme o padrão de `guias_router.py`); `minio_client.upload_bytes/download_bytes`; env `SCRAPER_URL`.
- Produces:
  - `POST /api/q/concursos/importar` (service ou sessão) body `{"concurso": {...}, "arquivos": [...]}` → `{"ok": true, "concurso_id": int, "arquivos": int}` — upsert idempotente
  - `GET /api/q/concursos` (admin) `?busca=&page=1&page_size=50` → `{"items": [{...concurso, "arquivos": [{"id","tipo","nome_arquivo","content_type","tamanho_bytes"}]}], "total": int}` (ordem: `ano DESC, id DESC`)
  - `GET /api/q/concursos/arquivo/{arquivo_id}` (admin) → `Response(content=..., media_type=..., headers={"Content-Disposition": f'attachment; filename="{nome}"'})` via `minio_client.download_bytes`
  - `POST /api/q/concursos/coletar` (admin) body `{"filtros": [{"id","tipo"}]}` → proxy `POST {SCRAPER_URL}/enqueue/concursos` (timeouts curtos, padrão q_router.py:440-462)
  - `GET /api/q/concursos/jobs` (admin) → progresso: SQL cru em `tc_jobs` (kind='concursos') + `tc_concurso_units` (padrão `GET /api/q/coletar/comentario-jobs`, q_router.py:772+): `{"jobs": [{"job_id","status","paused","filtros","discovery","total_units","done_units","failed_units","blocked_units","atualizado_em"}]}`
  - `GET /api/q/concursos/filtros` (admin) → proxy `GET {SCRAPER_URL}/tc/concursos/filtros`

- [ ] **Step 1: Failing tests** (fixtures/`conftest.py` existentes; DB de teste aiosqlite):

```python
import pytest

PAYLOAD = {
    "concurso": {
        "concurso_id_externo": 86869, "edital_id_externo": 19626,
        "nome_completo": "Analista (IPLANFOR)/2024", "url_concurso": "analista-iplanfor-2024",
        "banca_nome": "IDECAN", "orgao_sigla": "IPPLAN", "orgao_nome": "Instituto",
        "edital_nome": "01/2024", "ano": 2024,
        "data_aplicacao": "14/04/2024 00:00:00", "escolaridade": "Superior",
    },
    "arquivos": [
        {"tipo": "EDITAL", "arquivo_id_externo": 452178, "uuid": "u-ed",
         "nome_arquivo": "edital.pdf", "minio_object_key": "concursos/u-ed.pdf",
         "content_type": "application/pdf", "tamanho_bytes": 100},
    ],
}


@pytest.mark.asyncio
async def test_importar_idempotente(client_service):  # client com X-Internal-Token
    r1 = await client_service.post("/api/q/concursos/importar", json=PAYLOAD)
    assert r1.status_code == 200 and r1.json()["arquivos"] == 1
    r2 = await client_service.post("/api/q/concursos/importar", json=PAYLOAD)
    assert r2.status_code == 200  # repetir NÃO duplica
    lista = await client_admin_get("/api/q/concursos")  # helper conforme conftest
    assert lista["total"] == 1
    assert len(lista["items"][0]["arquivos"]) == 1


@pytest.mark.asyncio
async def test_importar_sem_token_401(client_anon):
    r = await client_anon.post("/api/q/concursos/importar", json=PAYLOAD)
    assert r.status_code == 401
```

(Adaptar nomes de fixtures aos que existem em `backend/tests/conftest.py` — ler o conftest antes; se não houver fixture de token de serviço, criar uma setando `STUDIA_INTERNAL_TOKEN` via `monkeypatch.setenv` e header correspondente.)

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar router** — upsert: `SELECT ... WHERE concurso_id_externo=` → update campos ou insert; arquivos por `(concurso_id, arquivo_id_externo)`; `data_aplicacao` parseada com `datetime.strptime(v, "%d/%m/%Y %H:%M:%S")` em try/except (None se inválida). Registrar em `backend/main.py`: `app.include_router(concursos_router.router)`.
- [ ] **Step 4: Testes passam** — `python -m pytest tests/ -v`.
- [ ] **Step 5: Commit** — `feat(backend): router /api/q/concursos (import idempotente, stream, coleta, progresso)`

---

### Task 7: Frontend — página `/q/concursos`

**Files:**
- Create: `fontend/app/q/concursos/page.tsx`
- Modify: `fontend/lib/queryKeys.ts` (adicionar chaves) e o ponto de navegação admin que linka `/q/coletar` (localizar com `grep -rn '"/q/coletar"' fontend/app --include='*.tsx'` e adicionar link "Concursos" ao lado)

**Interfaces:**
- Consumes: endpoints da Task 6; `apiFetch` de `@/lib/api`; `Skeleton`/`BrandLoader` de `app/components/ds`; guarda admin + polling condicional copiados de `fontend/app/q/coletar/page.tsx:415-423,525-531`.
- Produces (em `queryKeys.ts` — `concursos()` JÁ EXISTE para o legado de boletim; usar nomes novos):

```ts
tcConcursos: (busca: string, page: number) => ["q", "concursos", "lista", busca, page] as const,
tcConcursoJobs: () => ["q", "concursos", "jobs"] as const,
tcConcursoFiltros: () => ["q", "concursos", "filtros"] as const,
```

- [ ] **Step 1: Página** com 3 blocos (client component, guarda admin igual `/q/coletar`):
  1. **Nova coleta**: `useQuery(qk.tcConcursoFiltros(), …)` — enquanto `isPending`, `<BrandLoader label="Consultando filtros na fonte externa…" />` (operação lenta, vai ao TC); erro → aviso com botão tentar de novo. Dois `<select>` pesquisáveis simples (input filtra client-side; os arrays têm ~600 bancas / ~200 formações — renderizar `<datalist>` ou lista filtrada máx. 50): Banca e Formação (itens `{key,name}` — mapear id=key). Botão "Coletar" (disabled sem ao menos 1 filtro) → `useMutation` POST `/api/q/concursos/coletar` com `{filtros: [{id, tipo: "BANCA"}, {id, tipo: "PROFISSAO"}]}` → invalidate `tcConcursoJobs`.
  2. **Jobs**: `useQuery(qk.tcConcursoJobs(), …, { refetchInterval: (q) => temJobAtivo(q) ? 15000 : false })`; card por job: filtros legíveis, fase ("Descobrindo concursos…" quando `discovery==='running'`, senão barra `done/total`), badges failed/blocked; enquanto houver job ativo NÃO mostrar estado-vazio na listagem (regra dados-não-pulam).
  3. **Listagem**: `useQuery(qk.tcConcursos(busca, page), …)`; `<Skeleton>` de tabela (mesmas alturas) no `isPending`; colunas: Concurso (nome_completo + orgao_nome), Banca, Ano, Aplicação, Arquivos = chips por `arquivo` (label humanizada: `EDITAL→Edital`, `PROVA_OBJETIVA→Prova objetiva`, `PROVA_DISCURSIVA→Prova discursiva`, `GABARITO→Gabarito`, fallback title-case) com `<a href={api}/api/q/concursos/arquivo/${a.id}` download>`; ícone ↗ linkando `https://www.tecconcursos.com.br/concursos/${url_concurso}` (target _blank).
- [ ] **Step 2: Lint** — `cd fontend && pnpm lint` → sem erros novos.
- [ ] **Step 3: Commit** — `feat(q): página /q/concursos (coleta por filtros + arquivos)`

---

### Task 8: Deploy + smoke test IDECAN + Engenharia Civil (prod)

**Files:** nenhum (operacional)

- [ ] **Step 1:** Do checkout principal (que segue na `main`): `git merge <branch-do-worktree>` → `git push`.
- [ ] **Step 2:** `./build.sh` (stack inteira reinicia; jobs de coleta em andamento resumem sozinhos).
- [ ] **Step 3 (smoke):** logado como admin na UI de prod, abrir `/q/concursos`, escolher Banca=IDECAN e Formação=Engenharia Civil e clicar Coletar. Acompanhar o job (descoberta → ~49 units). Alternativa via API: `POST /api/q/concursos/coletar {"filtros":[{"id":95,"tipo":"BANCA"},{"id":6,"tipo":"PROFISSAO"}]}`.
- [ ] **Step 4 (verificação):** `SELECT count(*) FROM tc_concursos;` (esperado 49) e `SELECT count(*) FROM tc_concurso_arquivos;` (>0); baixar 1 edital pela UI; rodar a MESMA coleta de novo e conferir que units re-rodam sem duplicar linhas nem re-baixar binários (log `skip` + counts estáveis).
- [ ] **Step 5:** `git worktree remove` + `git status` limpo.

## Self-review

- Spec coverage: contrato TC (T1), ledger/jobs (T2-T4), models+migração (T5), endpoints (T6), UI (T7), smoke idempotente (T8). Fallback de scraping da página individual do concurso ficou de fora conscientemente (YAGNI — a busca já traz `arquivosPorTipo`; se o smoke mostrar lacuna, vira follow-up).
- Tipos consistentes: `payload.concurso.*` snake_case definido em T1 é o mesmo consumido em T3 (`_post_import`) e T6 (importar). `arquivos_ok` (T2/T3). `EnqueueCadernoResponse` reutilizado (T4).
- Sem placeholders: passos de colagem em arquivos gigantes apontam o bloco-fonte exato (arquivo:linha) a copiar.
