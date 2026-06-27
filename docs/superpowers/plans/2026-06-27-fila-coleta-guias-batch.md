# Fila serial de coleta de guias (batch + cooldown) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar vários guias do TecConcursos de uma vez e coletá-los **1 por vez**, com **pausa ≥15 min entre guias**, valendo igual para "colar todas as URLs juntas" e "uma a uma".

**Architecture:** Uma tabela FIFO `guia_fila` + um **supervisor** (loop em processo separado, na imagem do backend) que só libera os cadernos do próximo guia depois que os do anterior terminam e o cooldown expira. A coleta de unidades (faixas de 200q) já é serial no NATS (`max_ack_pending=1`); o supervisor adiciona a serialização e o cooldown **no nível de guia**. Resolução/salvamento no TC é **preguiçoso** (só na vez do guia). O scraper permanece genérico.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL (asyncpg); pytest + pytest-asyncio (banco `studia_test`); Next.js 16 + React 19 + TanStack Query + Tailwind; Docker Swarm (`docker/stack.yml`).

## Global Constraints

- **Idioma:** comentários, mensagens de UI e docstrings em **Português BR**.
- **Migrações:** Alembic é a autoridade de schema. `down_revision` da nova migração = `'d9f0a1b2c3e4'` (head atual). `scripts/db_prepare.py` roda `alembic upgrade head` no startup. **Sem drift** (`test_alembic_no_drift` roda `alembic check`): a migração deve bater 1:1 com o model.
- **Testes backend:** rodam contra Postgres `studia_test` via `./dev.sh test` (faz `alembic upgrade head` antes do pytest). Fixtures em `backend/tests/conftest.py`: `client`, `db_session`, `auth_state` (admin por padrão), `make_user`. Stub de scraper: helper `_fake_scraper` em `test_guias_router.py` (patcha `guias_router.httpx.AsyncClient`).
- **Datas:** usar `datetime.utcnow()` (naive) para `iniciado_em`/`finalizado_em`, consistente com as colunas `DateTime` naive do projeto.
- **Serialização do scraper:** NÃO mexer — `studia-scraper-worker-default` com `max_ack_pending=1` já garante 1 faixa por vez.
- **Envs novos (defaults):** `GUIA_COOLDOWN_SECONDS=900`, `GUIA_SUPERVISOR_INTERVAL=30`, `GUIA_MAX_COLETA_SECONDS=21600`, `GUIA_RESOLVE_MAX_TENTATIVAS=3`.
- **Endpoints admin-only:** usar `Depends(require_admin)` como os demais de `guias_router.py`.

---

## File Structure

- `backend/models.py` — **modificar**: novo model `GuiaFila` (após `GuiaCaderno`, ~linha 533).
- `backend/alembic/versions/e1f2a3b4c5d6_guia_fila.py` — **criar**: migração da tabela `guia_fila`.
- `backend/guia_service.py` — **criar**: domínio da fila (CRUD + cooldown), ops de guia extraídas (`resolver_e_salvar`, `enqueue_cadernos_do_guia`, `guia_coleta_completa`) e o **tick** do supervisor (`guia_supervisor_tick`).
- `backend/guias_router.py` — **modificar**: `importar` (campo `apenas_catalogar`), `importar-lote`, `{id}/coletar` (→ fila), `GET /fila`, `DELETE /fila/{id}`, `POST /fila/{id}/pular`. Extrair corpo de resolve+save para `guia_service`.
- `backend/scripts/guia_supervisor.py` — **criar**: runner (loop) que chama o tick com deps reais + config por env.
- `backend/tests/test_guia_fila.py` — **criar**: testes da fila + endpoints.
- `backend/tests/test_guia_supervisor.py` — **criar**: testes do tick (invariantes).
- `backend/tests/test_guias_router.py` — **modificar**: `iniciar_coleta:False`→`apenas_catalogar:True`; reescrever o teste de enqueue.
- `docker/stack.yml` + `docker-compose.dev.yml` — **modificar**: serviço `studia-guia-supervisor`.
- `fontend/lib/queryKeys.ts` — **modificar**: `qk.guiaFila()`.
- `fontend/app/q/coletar/GuiasPanel.tsx` — **modificar**: textarea + `importar-lote` + seção "Fila de coleta".

---

### Task 1: Model `GuiaFila` + migração Alembic

**Files:**
- Modify: `backend/models.py` (após `GuiaCaderno`, ~linha 533)
- Create: `backend/alembic/versions/e1f2a3b4c5d6_guia_fila.py`
- Test: coberto por `test_alembic_no_drift.py` (já existe) + check manual

**Interfaces:**
- Produces: model `GuiaFila` com campos `id, url, status, guia_id, iniciado_em, finalizado_em, tentativas, erro, requested_by, created_at, updated_at` e tabela `guia_fila`.

- [ ] **Step 1: Adicionar o model `GuiaFila` em `models.py`**

Inserir logo após a classe `GuiaCaderno` (após a linha `guia: Mapped["Guia"] = relationship(back_populates="cadernos")`):

```python
class GuiaFila(Base):
    """Fila FIFO de coleta de guias. Garante 1 guia coletando por vez + cooldown
    entre guias (o supervisor `scripts/guia_supervisor.py` consome esta tabela).

    Ciclo de status: queued → resolving → collecting → done/skipped/error.
    `finalizado_em` do último terminado é a referência do cooldown.
    """

    __tablename__ = "guia_fila"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # URL colada do guia. NULL em re-coleta (já tem guia_id).
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    guia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guias.id", ondelete="SET NULL"), nullable=True
    )
    iniciado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finalizado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Criar a migração**

Criar `backend/alembic/versions/e1f2a3b4c5d6_guia_fila.py`:

```python
"""guia_fila (fila serial de coleta de guias)"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d9f0a1b2c3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guia_fila",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("guia_id", sa.Integer(), nullable=True),
        sa.Column("iniciado_em", sa.DateTime(), nullable=True),
        sa.Column("finalizado_em", sa.DateTime(), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["guia_id"], ["guias.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_guia_fila_status", "guia_fila", ["status"])


def downgrade() -> None:
    op.drop_index("ix_guia_fila_status", table_name="guia_fila")
    op.drop_table("guia_fila")
```

> **Nota de drift:** o model usa `default=` (Python) para `status`/`tentativas`, mas a migração usa `server_default`. `alembic check` compara o schema do banco com o `autogenerate` dos models — `server_default` no banco sem `server_default` no model **gera drift**. Para evitar: ou (a) adicionar `server_default="queued"`/`server_default="0"` no model, ou (b) remover os `server_default` da migração. **Escolha (a)** para que colunas tenham default no banco.

- [ ] **Step 2b: Alinhar defaults no model (anti-drift)**

Editar no model recém-criado:

```python
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="queued", default="queued", index=True
    )
    tentativas: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
```

- [ ] **Step 3: Aplicar migração no banco de teste e checar drift**

Run: `./dev.sh test test_alembic_no_drift.py -v`
Expected: PASS (`alembic upgrade head` cria `guia_fila`; `alembic check` sem drift).

- [ ] **Step 4: Commit**

```bash
git add backend/models.py backend/alembic/versions/e1f2a3b4c5d6_guia_fila.py
git commit -m "feat(coleta): model GuiaFila + migração da fila serial de guias"
```

---

### Task 2: `guia_service` — CRUD da fila + cooldown

**Files:**
- Create: `backend/guia_service.py`
- Test: `backend/tests/test_guia_fila.py`

**Interfaces:**
- Consumes: model `GuiaFila` (Task 1).
- Produces:
  - `async def enfileirar_urls(db, urls: list[str], *, requested_by: str | None) -> list[GuiaFila]`
  - `async def enfileirar_guia(db, guia_id: int, *, requested_by: str | None) -> GuiaFila | None`
  - `async def proximo_cooldown_segundos(db, *, agora: datetime, cooldown_s: int) -> int`
  - `async def listar_fila(db, *, agora: datetime, cooldown_s: int) -> dict`
  - `async def remover_da_fila(db, fila_id: int) -> bool`
  - `async def pular_fila(db, fila_id: int, *, agora: datetime) -> bool`
  - Constantes de status: `ATIVOS = ("resolving", "collecting")`, `TERMINAIS = ("done", "skipped", "error")`.

- [ ] **Step 1: Escrever os testes da fila (falhando)**

Criar `backend/tests/test_guia_fila.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import guia_service
from models import GuiaFila


@pytest.mark.asyncio
async def test_enfileirar_urls_cria_entradas_queued_e_dedup(db_session):
    entries = await guia_service.enfileirar_urls(
        db_session, ["a", "a", "  ", "b"], requested_by="admin-1"
    )
    await db_session.commit()
    assert [e.url for e in entries] == ["a", "b"]  # trim + dedup intra-lote
    assert all(e.status == "queued" for e in entries)
    rows = (await db_session.execute(select(GuiaFila))).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_enfileirar_urls_ignora_url_ja_ativa(db_session):
    await guia_service.enfileirar_urls(db_session, ["a"], requested_by=None)
    await db_session.commit()
    again = await guia_service.enfileirar_urls(db_session, ["a", "c"], requested_by=None)
    await db_session.commit()
    assert [e.url for e in again] == ["c"]  # "a" já estava na fila


@pytest.mark.asyncio
async def test_cooldown_zero_sem_finalizados(db_session):
    seg = await guia_service.proximo_cooldown_segundos(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), cooldown_s=900
    )
    assert seg == 0


@pytest.mark.asyncio
async def test_cooldown_conta_do_ultimo_finalizado(db_session):
    fim = datetime(2026, 1, 1, 12, 0, 0)
    db_session.add(GuiaFila(url="a", status="done", finalizado_em=fim))
    await db_session.flush()
    # 300s depois → faltam 600s do cooldown de 900s
    seg = await guia_service.proximo_cooldown_segundos(
        db_session, agora=fim + timedelta(seconds=300), cooldown_s=900
    )
    assert seg == 600


@pytest.mark.asyncio
async def test_remover_e_pular(db_session):
    [e] = await guia_service.enfileirar_urls(db_session, ["a"], requested_by=None)
    await db_session.flush()
    assert await guia_service.remover_da_fila(db_session, e.id) is True
    [e2] = await guia_service.enfileirar_urls(db_session, ["b"], requested_by=None)
    e2.status = "collecting"
    await db_session.flush()
    agora = datetime(2026, 1, 1, 12, 0, 0)
    assert await guia_service.pular_fila(db_session, e2.id, agora=agora) is True
    await db_session.refresh(e2)
    assert e2.status == "skipped" and e2.finalizado_em == agora
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `./dev.sh test test_guia_fila.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'guia_service'`).

- [ ] **Step 3: Implementar `guia_service.py` (parte da fila)**

Criar `backend/guia_service.py`:

```python
"""Domínio da fila serial de coleta de guias.

Concentra: CRUD da `guia_fila`, cálculo de cooldown, as operações de guia
reusadas pelo supervisor (resolver+salvar, enfileirar cadernos, checar
conclusão) e o tick do supervisor. Mantém o scraper genérico — a noção de
"guia" e a serialização entre guias vivem aqui.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import GuiaFila

ATIVOS = ("resolving", "collecting")
TERMINAIS = ("done", "skipped", "error")


# ─── Fila: CRUD + cooldown ───────────────────────────────


async def enfileirar_urls(
    db: AsyncSession, urls: list[str], *, requested_by: str | None
) -> list[GuiaFila]:
    """Cria entradas `queued` para URLs novas (trim + dedup intra-lote; ignora
    URLs que já têm entrada não-terminal). NÃO commita (o chamador commita)."""
    vistos: set[str] = set()
    limpos: list[str] = []
    for u in urls:
        u = (u or "").strip()
        if u and u not in vistos:
            vistos.add(u)
            limpos.append(u)
    if not limpos:
        return []
    ja = set(
        (
            await db.execute(
                select(GuiaFila.url).where(
                    GuiaFila.url.in_(limpos),
                    GuiaFila.status.in_(("queued", *ATIVOS)),
                )
            )
        )
        .scalars()
        .all()
    )
    novos = [GuiaFila(url=u, status="queued", requested_by=requested_by) for u in limpos if u not in ja]
    for e in novos:
        db.add(e)
    await db.flush()
    return novos


async def enfileirar_guia(
    db: AsyncSession, guia_id: int, *, requested_by: str | None
) -> GuiaFila | None:
    """Enfileira a re-coleta de um guia já existente (sem resolver de novo).
    Idempotente: retorna None se já houver entrada não-terminal p/ esse guia."""
    existe = (
        await db.execute(
            select(GuiaFila.id).where(
                GuiaFila.guia_id == guia_id,
                GuiaFila.status.in_(("queued", *ATIVOS)),
            )
        )
    ).first()
    if existe:
        return None
    e = GuiaFila(guia_id=guia_id, status="queued", requested_by=requested_by)
    db.add(e)
    await db.flush()
    return e


async def proximo_cooldown_segundos(
    db: AsyncSession, *, agora: datetime, cooldown_s: int
) -> int:
    """Segundos restantes do cooldown desde o último guia finalizado. 0 se nunca
    finalizou nada ou já passou o cooldown."""
    ultimo = (
        await db.execute(
            select(GuiaFila.finalizado_em)
            .where(GuiaFila.finalizado_em.isnot(None))
            .order_by(GuiaFila.finalizado_em.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ultimo is None:
        return 0
    restante = cooldown_s - (agora - ultimo).total_seconds()
    return max(0, int(restante))


async def listar_fila(db: AsyncSession, *, agora: datetime, cooldown_s: int) -> dict:
    """Fila ordenada (FIFO por id) + countdown do cooldown."""
    rows = (await db.execute(select(GuiaFila).order_by(GuiaFila.id))).scalars().all()
    pos = 0
    itens: list[dict[str, Any]] = []
    for e in rows:
        if e.status == "queued":
            pos += 1
        itens.append(
            {
                "id": e.id,
                "url": e.url,
                "status": e.status,
                "guia_id": e.guia_id,
                "posicao": pos if e.status == "queued" else None,
                "erro": e.erro,
                "iniciado_em": e.iniciado_em.isoformat() if e.iniciado_em else None,
                "finalizado_em": e.finalizado_em.isoformat() if e.finalizado_em else None,
            }
        )
    ativo = any(e.status in ATIVOS for e in rows)
    proximo = 0 if ativo else await proximo_cooldown_segundos(db, agora=agora, cooldown_s=cooldown_s)
    return {"fila": itens, "ativo": ativo, "proximo_em_segundos": proximo}


async def remover_da_fila(db: AsyncSession, fila_id: int) -> bool:
    """Remove uma entrada `queued` (não mexe em ativa/terminal)."""
    e = (
        await db.execute(select(GuiaFila).where(GuiaFila.id == fila_id))
    ).scalar_one_or_none()
    if e is None or e.status != "queued":
        return False
    await db.delete(e)
    await db.flush()
    return True


async def pular_fila(db: AsyncSession, fila_id: int, *, agora: datetime) -> bool:
    """Pula a entrada (marca skipped + finalizado_em → dispara cooldown)."""
    e = (
        await db.execute(select(GuiaFila).where(GuiaFila.id == fila_id))
    ).scalar_one_or_none()
    if e is None or e.status in TERMINAIS:
        return False
    e.status = "skipped"
    e.finalizado_em = agora
    await db.flush()
    return True
```

- [ ] **Step 4: Rodar — deve passar**

Run: `./dev.sh test test_guia_fila.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/guia_service.py backend/tests/test_guia_fila.py
git commit -m "feat(coleta): guia_service — CRUD da fila + cooldown serial de guias"
```

---

### Task 3: `guia_service` — ops de guia (resolver/salvar, enqueue, conclusão)

**Files:**
- Modify: `backend/guia_service.py`
- Modify: `backend/guias_router.py` (extrair corpo de resolve+save de `importar_guia`)
- Test: `backend/tests/test_guia_fila.py` (acrescentar)

**Interfaces:**
- Consumes (lazy import de `guias_router`): `_scraper_post`, `_merge_cadernos`, `_enqueue_caderno`, `_jobs_por_caderno`, `_coletado_por_caderno`, `_RESOLVE_TIMEOUT`, `_SAVE_TIMEOUT`, `Guia`, `GuiaCaderno`.
- Produces:
  - `async def resolver_e_salvar(db, *, url: str, relogin: bool, page_size: int) -> tuple[Guia, list[dict]]`
  - `async def enqueue_cadernos_do_guia(db, guia_id: int, *, page_size: int) -> tuple[int, list[int]]`
  - `async def guia_coleta_completa(db, guia_id: int) -> bool`

- [ ] **Step 1: Escrever testes (falhando) em `test_guia_fila.py`**

Acrescentar ao fim de `backend/tests/test_guia_fila.py`:

```python
from sqlalchemy import func as safunc
from models import Guia, GuiaCaderno

_RESOLVE = {
    "tc_guia_id": 7777,
    "slug": "x/y",
    "url": "https://www.tecconcursos.com.br/guias/x/y/-",
    "nome": "Guia X",
    "banca": "FGV",
    "cadernos": [
        {"tc_caderno_id": 111, "nome": "Mat A", "total_questoes": 10, "total_capitulos": 0, "ordem": 1},
    ],
}
_SAVE = {"pasta_id": 9001, "itens": [{"id": 111, "nome": "Mat A", "quantidadeItens": 10}]}


def _patch_scraper(monkeypatch):
    """Patcha guias_router.httpx (resolver_e_salvar usa _scraper_post de lá)."""
    from test_guias_router import _fake_scraper

    return _fake_scraper(
        monkeypatch, resolve=_RESOLVE, save=_SAVE,
        enqueue={"job_id": 1, "status": "pending", "total_units": 1, "enqueued_units": 1},
    )


@pytest.mark.asyncio
async def test_resolver_e_salvar_cria_guia_e_cadernos(db_session, monkeypatch):
    _patch_scraper(monkeypatch)
    guia, cadernos = await guia_service.resolver_e_salvar(
        db_session, url="x", relogin=False, page_size=200
    )
    await db_session.commit()
    assert guia.tc_guia_id == 7777
    assert len(cadernos) == 1
    n = (await db_session.execute(select(safunc.count()).select_from(GuiaCaderno))).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_guia_coleta_completa_sem_jobs_e_false(db_session, monkeypatch):
    _patch_scraper(monkeypatch)
    guia, _ = await guia_service.resolver_e_salvar(db_session, url="x", relogin=False, page_size=200)
    await db_session.commit()
    assert await guia_service.guia_coleta_completa(db_session, guia.id) is False


@pytest.mark.asyncio
async def test_enqueue_cadernos_do_guia(db_session, monkeypatch):
    calls = _patch_scraper(monkeypatch)
    guia, _ = await guia_service.resolver_e_salvar(db_session, url="x", relogin=False, page_size=200)
    await db_session.commit()
    enq, falhas = await guia_service.enqueue_cadernos_do_guia(db_session, guia.id, page_size=200)
    assert enq == 1 and falhas == []
    assert sum(1 for c in calls if c["url"].endswith("/enqueue/caderno")) == 1
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `./dev.sh test test_guia_fila.py -v -k "resolver_e_salvar or coleta_completa or enqueue_cadernos"`
Expected: FAIL (`AttributeError: module 'guia_service' has no attribute 'resolver_e_salvar'`).

- [ ] **Step 3: Extrair a lógica de resolve+save de `guias_router.importar_guia` para `guia_service.resolver_e_salvar`**

Adicionar a `backend/guia_service.py` (após os helpers de fila):

```python
# ─── Ops de guia (reuso do pipeline existente) ───────────


async def resolver_e_salvar(
    db: AsyncSession, *, url: str, relogin: bool, page_size: int
) -> tuple[Any, list[dict]]:
    """Resolve a URL do guia, faz upsert de Guia + GuiaCaderno e salva os
    cadernos no TC. NÃO enfileira coleta e NÃO commita (chamador commita).
    Retorna (guia, cadernos). Reusa os helpers de `guias_router`."""
    from sqlalchemy import select as _select

    import guias_router as gr
    from models import Guia, GuiaCaderno

    resolved = await gr._scraper_post(
        "/guia/resolver", {"url": url, "relogin": relogin}, gr._RESOLVE_TIMEOUT
    )
    tc_guia_id = int(resolved["tc_guia_id"])
    cadernos_in = resolved.get("cadernos", [])

    guia = (
        await db.execute(_select(Guia).where(Guia.tc_guia_id == tc_guia_id))
    ).scalar_one_or_none()
    if guia is None:
        guia = Guia(tc_guia_id=tc_guia_id)
        db.add(guia)
    guia.slug = resolved.get("slug")
    guia.url = resolved.get("url") or url
    guia.nome = resolved.get("nome") or f"Guia {tc_guia_id}"
    guia.banca = resolved.get("banca")
    guia.status = "saving"
    await db.flush()

    saved = await gr._scraper_post(
        "/guia/salvar-cadernos", {"tc_guia_id": tc_guia_id}, gr._SAVE_TIMEOUT
    )
    pasta_id = saved.get("pasta_id")
    if pasta_id:
        guia.tc_pasta_id = int(pasta_id)

    cadernos = gr._merge_cadernos(saved.get("itens") or [], cadernos_in)
    if not cadernos:
        from fastapi import HTTPException

        raise HTTPException(502, "Não foi possível obter os cadernos do guia (pasta vazia).")
    guia.total_cadernos = len(cadernos)

    existing = {
        gc.tc_caderno_id: gc
        for gc in (
            await db.execute(_select(GuiaCaderno).where(GuiaCaderno.guia_id == guia.id))
        )
        .scalars()
        .all()
    }
    for c in cadernos:
        tc_caderno_id = int(c["tc_caderno_id"])
        gc = existing.get(tc_caderno_id)
        if gc is None:
            gc = GuiaCaderno(guia_id=guia.id, tc_caderno_id=tc_caderno_id)
            db.add(gc)
        gc.tc_caderno_base = c.get("caderno_base_id")
        gc.nome = c["nome"]
        gc.disciplina = c["nome"]
        gc.total_questoes = int(c.get("total_questoes") or 0)
        gc.total_capitulos = int(c.get("total_capitulos") or 0)
        gc.ordem = c.get("ordem")
        if gc.status not in {"materialized"}:
            gc.status = "pending"
    await db.flush()
    return guia, cadernos


async def enqueue_cadernos_do_guia(
    db: AsyncSession, guia_id: int, *, page_size: int
) -> tuple[int, list[int]]:
    """Enfileira a coleta de cada caderno do guia. Retorna (enfileirados, falhas)."""
    from sqlalchemy import select as _select

    import guias_router as gr
    from models import GuiaCaderno

    cads = (
        await db.execute(_select(GuiaCaderno).where(GuiaCaderno.guia_id == guia_id))
    ).scalars().all()
    enq = 0
    falhas: list[int] = []
    for c in cads:
        if c.tc_caderno_id is None:
            continue
        res = await gr._enqueue_caderno(c.tc_caderno_id, c.total_questoes, page_size)
        if res.get("enqueued_units", 0) > 0 or res.get("job_id"):
            enq += 1
        else:
            falhas.append(c.tc_caderno_id)
    return enq, falhas


async def guia_coleta_completa(db: AsyncSession, guia_id: int) -> bool:
    """True quando todo caderno do guia está materializado, com job 'done', ou
    com coletado ≥ esperado (mesma regra de `listar_guias`)."""
    from sqlalchemy import select as _select

    import guias_router as gr
    from models import GuiaCaderno

    cads = (
        await db.execute(_select(GuiaCaderno).where(GuiaCaderno.guia_id == guia_id))
    ).scalars().all()
    if not cads:
        return False
    tc_ids = [c.tc_caderno_id for c in cads if c.tc_caderno_id]
    coletado = await gr._coletado_por_caderno(db, tc_ids)
    jobs = await gr._jobs_por_caderno(db, tc_ids)
    return all(
        c.caderno_id
        or jobs.get(c.tc_caderno_id, {}).get("status") == "done"
        or (c.total_questoes > 0 and coletado.get(c.tc_caderno_id, 0) >= c.total_questoes)
        for c in cads
    )
```

- [ ] **Step 4: Rodar — deve passar**

Run: `./dev.sh test test_guia_fila.py -v`
Expected: PASS (todos, inclusive os 3 novos).

- [ ] **Step 5: Garantir que os testes existentes de guias seguem verdes**

Run: `./dev.sh test test_guias_router.py -v`
Expected: PASS (nenhuma regressão — `importar` ainda inalterado nesta task).

- [ ] **Step 6: Commit**

```bash
git add backend/guia_service.py backend/tests/test_guia_fila.py
git commit -m "feat(coleta): guia_service — resolver/salvar, enqueue e checagem de conclusão"
```

---

### Task 4: Endpoints da fila em `guias_router.py`

**Files:**
- Modify: `backend/guias_router.py`
- Test: `backend/tests/test_guia_fila.py` (endpoints) + `backend/tests/test_guias_router.py` (ajustes)

**Interfaces:**
- Consumes: `guia_service.*` (Tasks 2-3).
- Produces (HTTP): `POST /api/q/guias/importar` (campo `apenas_catalogar`), `POST /api/q/guias/importar-lote`, `POST /api/q/guias/{id}/coletar` (→ fila), `GET /api/q/guias/fila`, `DELETE /api/q/guias/fila/{id}`, `POST /api/q/guias/fila/{id}/pular`.

- [ ] **Step 1: Escrever testes de endpoint (falhando)**

Acrescentar a `backend/tests/test_guia_fila.py`:

```python
@pytest.mark.asyncio
async def test_importar_lote_cria_fila(client, db_session):
    r = await client.post(
        "/api/q/guias/importar-lote",
        json={"urls": ["https://tc/guias/a", "https://tc/guias/a", "https://tc/guias/b"]},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["enfileirados"] == 2  # dedup
    rows = (await db_session.execute(select(GuiaFila))).scalars().all()
    assert {e.url for e in rows} == {"https://tc/guias/a", "https://tc/guias/b"}


@pytest.mark.asyncio
async def test_importar_default_vai_pra_fila_sem_resolver(client, db_session, monkeypatch):
    calls = _patch_scraper(monkeypatch)
    r = await client.post("/api/q/guias/importar", json={"url": "https://tc/guias/z"})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    assert calls == []  # NÃO resolve agora (preguiçoso)


@pytest.mark.asyncio
async def test_importar_apenas_catalogar_resolve_agora(client, db_session, monkeypatch):
    calls = _patch_scraper(monkeypatch)
    r = await client.post(
        "/api/q/guias/importar", json={"url": "x", "apenas_catalogar": True}
    )
    assert r.status_code == 202, r.text
    assert r.json()["cadernos"] == 1
    assert any(c["url"].endswith("/guia/resolver") for c in calls)
    # não enfileira coleta
    assert sum(1 for c in calls if c["url"].endswith("/enqueue/caderno")) == 0


@pytest.mark.asyncio
async def test_get_fila_e_pular(client, db_session):
    await client.post("/api/q/guias/importar-lote", json={"urls": ["a", "b"]})
    r = await client.get("/api/q/guias/fila")
    assert r.status_code == 200
    fila = r.json()["fila"]
    assert [e["posicao"] for e in fila] == [1, 2]
    fid = fila[0]["id"]
    rp = await client.post(f"/api/q/guias/fila/{fid}/pular")
    assert rp.status_code == 200 and rp.json()["ok"] is True
    rd = await client.delete(f"/api/q/guias/fila/{fila[1]['id']}")
    assert rd.status_code == 200 and rd.json()["ok"] is True
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `./dev.sh test test_guia_fila.py -v -k "importar or get_fila"`
Expected: FAIL (404/422 — endpoints e campo ainda não existem).

- [ ] **Step 3: Atualizar o schema e o endpoint `importar` em `guias_router.py`**

Substituir a classe `ImportarGuiaReq` (linhas 44-50):

```python
class ImportarGuiaReq(BaseModel):
    url: str = Field(..., description="URL base do guia TC (ex.: /guias/oab-2026)")
    relogin: bool = Field(False, description="Refazer login Playwright antes")
    page_size: int = Field(200, ge=1, le=200)
    apenas_catalogar: bool = Field(
        False,
        description="Só resolver+salvar metadados agora (sem coletar). Padrão: "
        "False = adiciona à fila de coleta serial.",
    )


class ImportarLoteReq(BaseModel):
    urls: list[str] = Field(..., min_length=1, description="URLs de guias do TC")
```

Substituir TODO o corpo de `importar_guia` (linhas 146-245) por:

```python
@router.post("/importar", status_code=status.HTTP_202_ACCEPTED)
async def importar_guia(
    req: ImportarGuiaReq,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Padrão: adiciona o guia à fila de coleta serial (resolve preguiçoso, na
    vez do guia). Com `apenas_catalogar=true`: resolve+salva metadados agora,
    sem coletar."""
    import guia_service

    if req.apenas_catalogar:
        guia, cadernos = await guia_service.resolver_e_salvar(
            db, url=req.url, relogin=req.relogin, page_size=req.page_size
        )
        guia.status = "pending"
        await db.commit()
        await db.refresh(guia)
        return {
            **_guia_dict(guia),
            "cadernos": len(cadernos),
            "enqueued": 0,
            "message": "Guia catalogado (sem coleta).",
        }

    novos = await guia_service.enfileirar_urls(db, [req.url], requested_by=_admin.id)
    await db.commit()
    if not novos:
        return {"status": "queued", "url": req.url, "message": "Guia já estava na fila."}
    e = novos[0]
    await db.refresh(e)
    return {
        "fila_id": e.id,
        "status": e.status,
        "url": e.url,
        "message": "Guia adicionado à fila de coleta.",
    }
```

- [ ] **Step 4: Adicionar os endpoints de lote e fila**

Inserir logo após `importar_guia` (antes de `_merge_cadernos`):

```python
@router.post("/importar-lote", status_code=status.HTTP_202_ACCEPTED)
async def importar_lote(
    req: ImportarLoteReq,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Enfileira N guias de uma vez (resolve preguiçoso, coleta 1 por vez)."""
    import guia_service

    novos = await guia_service.enfileirar_urls(db, req.urls, requested_by=_admin.id)
    await db.commit()
    return {
        "enfileirados": len(novos),
        "fila": [{"id": e.id, "url": e.url, "status": e.status} for e in novos],
        "message": f"{len(novos)} guia(s) na fila de coleta.",
    }


@router.get("/fila")
async def listar_fila(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fila de coleta + countdown do cooldown. Enriquece com o nome do guia."""
    import os
    from datetime import datetime

    import guia_service
    from models import Guia

    cooldown = int(os.getenv("GUIA_COOLDOWN_SECONDS", "900"))
    data = await guia_service.listar_fila(db, agora=datetime.utcnow(), cooldown_s=cooldown)
    guia_ids = [it["guia_id"] for it in data["fila"] if it["guia_id"]]
    nomes: dict[int, str] = {}
    if guia_ids:
        rows = (
            await db.execute(select(Guia.id, Guia.nome).where(Guia.id.in_(guia_ids)))
        ).all()
        nomes = {gid: nome for gid, nome in rows}
    for it in data["fila"]:
        it["guia_nome"] = nomes.get(it["guia_id"])
    return data


@router.delete("/fila/{fila_id}")
async def remover_fila(
    fila_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove uma entrada que ainda está só 'na fila'."""
    import guia_service

    ok = await guia_service.remover_da_fila(db, fila_id)
    await db.commit()
    return {"ok": ok}


@router.post("/fila/{fila_id}/pular")
async def pular_fila_endpoint(
    fila_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Pula a entrada ativa/queued (libera a fila; dispara o cooldown)."""
    from datetime import datetime

    import guia_service

    ok = await guia_service.pular_fila(db, fila_id, agora=datetime.utcnow())
    await db.commit()
    return {"ok": ok}
```

- [ ] **Step 5: Trocar `{id}/coletar` para enfileirar (em vez de enqueue direto)**

Substituir o corpo de `coletar_guia` (linhas 716-748) por:

```python
@router.post("/{guia_id}/coletar")
async def coletar_guia(
    guia_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adiciona o guia à fila de coleta serial (re-coleta). Idempotente: não
    duplica se já estiver na fila/coletando."""
    import guia_service

    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")
    e = await guia_service.enfileirar_guia(db, guia_id, requested_by=_admin.id)
    await db.commit()
    return {
        "guia_id": guia_id,
        "fila_id": e.id if e else None,
        "enfileirado": e is not None,
        "message": "Guia na fila de coleta." if e else "Guia já estava na fila/coletando.",
    }
```

- [ ] **Step 6: Ajustar os testes existentes em `test_guias_router.py`**

Trocar todas as ocorrências de `"iniciar_coleta": False` por `"apenas_catalogar": True` (testes: `test_importar_guia_idempotente`, `test_listar_e_detalhe_guia`, `test_renomear_guia`, `test_importar_guia_fresco_usa_itens_da_pasta`, `test_materializar_sem_coleta_nao_cria_caderno`).

Run (para localizar): `grep -rn "iniciar_coleta" backend/tests/`

Reescrever `test_importar_guia_persiste_e_enfileira` (linhas 78-103) para o novo comportamento default (vai pra fila, sem resolver):

```python
@pytest.mark.asyncio
async def test_importar_guia_default_vai_pra_fila(client, db_session, monkeypatch):
    from sqlalchemy import func as safunc
    from models import GuiaFila

    calls = _fake_scraper(monkeypatch, resolve=RESOLVE, save=SAVE, enqueue=ENQUEUE)
    r = await client.post("/api/q/guias/importar", json={"url": "https://tc/guias/oab"})
    assert r.status_code == 202
    assert r.json()["status"] == "queued"
    assert calls == []  # preguiçoso: não resolve no import
    n = (await db_session.execute(safunc.count(GuiaFila.id).select())).scalar() or (
        await db_session.execute(select(safunc.count()).select_from(GuiaFila))
    ).scalar()
    assert n == 1
```

> Se a primeira forma de contagem falhar por sintaxe, use só:
> `n = (await db_session.execute(select(safunc.count()).select_from(GuiaFila))).scalar()` (adicione `from sqlalchemy import select`).

- [ ] **Step 7: Rodar a suíte de guias completa**

Run: `./dev.sh test test_guia_fila.py test_guias_router.py -v`
Expected: PASS (todos).

- [ ] **Step 8: Commit**

```bash
git add backend/guias_router.py backend/tests/test_guia_fila.py backend/tests/test_guias_router.py
git commit -m "feat(coleta): endpoints da fila (importar-lote, GET/DELETE/pular) + importar via fila"
```

---

### Task 5: Tick do supervisor (`guia_supervisor_tick`)

**Files:**
- Modify: `backend/guia_service.py`
- Test: `backend/tests/test_guia_supervisor.py`

**Interfaces:**
- Consumes: `GuiaFila`, helpers da fila (Task 2), ops de guia (Task 3).
- Produces:
  - `async def guia_supervisor_tick(db, *, agora, cooldown_s, max_coleta_s, max_tentativas, resolver=..., enqueue=..., completa=...) -> dict` — deps injetáveis (default = funções reais). Retorna `{"acao": str, ...}` descrevendo o que o tick fez.

- [ ] **Step 1: Escrever os testes do tick (falhando)**

Criar `backend/tests/test_guia_supervisor.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import guia_service
from models import Guia, GuiaFila

CFG = dict(cooldown_s=900, max_coleta_s=21600, max_tentativas=3)


async def _guia(db, *, status="collecting"):
    g = Guia(tc_guia_id=None, nome="G", status=status)
    db.add(g)
    await db.flush()
    return g


def _deps(*, resolver=None, enqueue=None, completa=None):
    async def _r(db, url, *, page_size):  # cria um guia fake e devolve
        g = Guia(tc_guia_id=None, nome=f"resolvido:{url}", status="saving")
        db.add(g)
        await db.flush()
        return g

    async def _e(db, guia_id, *, page_size):
        return (1, [])

    async def _c(db, guia_id):
        return False

    return dict(
        resolver=resolver or _r,
        enqueue=enqueue or _e,
        completa=completa or _c,
    )


@pytest.mark.asyncio
async def test_primeiro_guia_inicia_imediatamente(db_session):
    await guia_service.enfileirar_urls(db_session, ["a"], requested_by=None)
    await db_session.flush()
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), **CFG, **_deps()
    )
    assert out["acao"] == "iniciou"
    [e] = (await db_session.execute(select(GuiaFila))).scalars().all()
    assert e.status == "collecting" and e.guia_id is not None


@pytest.mark.asyncio
async def test_nao_inicia_se_ja_coletando(db_session):
    g = await _guia(db_session)
    db_session.add(GuiaFila(guia_id=g.id, status="collecting", iniciado_em=datetime(2026, 1, 1, 11, 0, 0)))
    await guia_service.enfileirar_urls(db_session, ["b"], requested_by=None)
    await db_session.flush()
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), **CFG,
        **_deps(completa=lambda db, gid: _false()),
    )
    assert out["acao"] in ("aguardando", "nada")
    fila_b = (await db_session.execute(select(GuiaFila).where(GuiaFila.url == "b"))).scalar_one()
    assert fila_b.status == "queued"


async def _false():
    return False


@pytest.mark.asyncio
async def test_conclui_guia_e_dispara_cooldown(db_session):
    g = await _guia(db_session)
    e = GuiaFila(guia_id=g.id, status="collecting", iniciado_em=datetime(2026, 1, 1, 11, 0, 0))
    db_session.add(e)
    await db_session.flush()

    async def _completa(db, gid):
        return True

    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 12, 0, 0), **CFG,
        **_deps(completa=_completa),
    )
    assert out["acao"] == "concluiu"
    await db_session.refresh(e)
    assert e.status == "done" and e.finalizado_em == datetime(2026, 1, 1, 12, 0, 0)


@pytest.mark.asyncio
async def test_respeita_cooldown(db_session):
    fim = datetime(2026, 1, 1, 12, 0, 0)
    db_session.add(GuiaFila(url="x", status="done", finalizado_em=fim))
    await guia_service.enfileirar_urls(db_session, ["novo"], requested_by=None)
    await db_session.flush()
    # 100s depois → ainda dentro do cooldown de 900s
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=fim + timedelta(seconds=100), **CFG, **_deps()
    )
    assert out["acao"] == "cooldown"
    novo = (await db_session.execute(select(GuiaFila).where(GuiaFila.url == "novo"))).scalar_one()
    assert novo.status == "queued"


@pytest.mark.asyncio
async def test_inicia_apos_cooldown(db_session):
    fim = datetime(2026, 1, 1, 12, 0, 0)
    db_session.add(GuiaFila(url="x", status="done", finalizado_em=fim))
    await guia_service.enfileirar_urls(db_session, ["novo"], requested_by=None)
    await db_session.flush()
    out = await guia_service.guia_supervisor_tick(
        db_session, agora=fim + timedelta(seconds=901), **CFG, **_deps()
    )
    assert out["acao"] == "iniciou"


@pytest.mark.asyncio
async def test_auto_skip_apos_max_coleta(db_session):
    g = await _guia(db_session)
    e = GuiaFila(guia_id=g.id, status="collecting", iniciado_em=datetime(2026, 1, 1, 0, 0, 0))
    db_session.add(e)
    await db_session.flush()

    async def _completa(db, gid):
        return False

    out = await guia_service.guia_supervisor_tick(
        db_session, agora=datetime(2026, 1, 1, 7, 0, 0), **CFG,  # 7h > 6h
        **_deps(completa=_completa),
    )
    assert out["acao"] == "pulou_timeout"
    await db_session.refresh(e)
    assert e.status == "skipped"


@pytest.mark.asyncio
async def test_resolver_falha_vira_error_apos_tentativas(db_session):
    await guia_service.enfileirar_urls(db_session, ["ruim"], requested_by=None)
    await db_session.flush()

    async def _resolver_falha(db, url, *, page_size):
        raise RuntimeError("scraper 502")

    agora = datetime(2026, 1, 1, 12, 0, 0)
    # 3 tentativas: cada tick incrementa; na 3ª vira error
    for _ in range(3):
        out = await guia_service.guia_supervisor_tick(
            db_session, agora=agora, **CFG, **_deps(resolver=_resolver_falha)
        )
    e = (await db_session.execute(select(GuiaFila).where(GuiaFila.url == "ruim"))).scalar_one()
    assert e.status == "error" and e.tentativas == 3 and out["acao"] == "erro_resolver"
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `./dev.sh test test_guia_supervisor.py -v`
Expected: FAIL (`AttributeError: ... 'guia_supervisor_tick'`).

- [ ] **Step 3: Implementar `guia_supervisor_tick` em `guia_service.py`**

Adicionar ao fim de `backend/guia_service.py`:

```python
# ─── Tick do supervisor ──────────────────────────────────


async def _default_resolver(db: AsyncSession, url: str, *, page_size: int):
    guia, _ = await resolver_e_salvar(db, url=url, relogin=False, page_size=page_size)
    return guia


async def guia_supervisor_tick(
    db: AsyncSession,
    *,
    agora: datetime,
    cooldown_s: int,
    max_coleta_s: int,
    max_tentativas: int,
    resolver=_default_resolver,
    enqueue=enqueue_cadernos_do_guia,
    completa=guia_coleta_completa,
) -> dict[str, Any]:
    """Um passo do supervisor. Invariantes: ≤1 entrada ativa; 1º guia imediato;
    ≥cooldown entre guias. Deps (resolver/enqueue/completa) são injetáveis p/ teste.
    Retorna {"acao": ...}. NÃO commita (o runner commita)."""
    # 1) Há entrada ativa?
    ativo = (
        await db.execute(
            select(GuiaFila).where(GuiaFila.status.in_(ATIVOS)).order_by(GuiaFila.id).limit(1)
        )
    ).scalar_one_or_none()

    if ativo is not None:
        if ativo.status == "collecting" and ativo.guia_id is not None:
            if await completa(db, ativo.guia_id):
                ativo.status = "done"
                ativo.finalizado_em = agora
                await db.flush()
                return {"acao": "concluiu", "fila_id": ativo.id}
            if ativo.iniciado_em and (agora - ativo.iniciado_em).total_seconds() > max_coleta_s:
                ativo.status = "skipped"
                ativo.erro = "timeout (parcial)"
                ativo.finalizado_em = agora
                await db.flush()
                return {"acao": "pulou_timeout", "fila_id": ativo.id}
            return {"acao": "aguardando", "fila_id": ativo.id}
        # 'resolving' preso (crash): trata como tentativa que vai re-tentar
        return {"acao": "nada", "fila_id": ativo.id}

    # 2) Nenhuma ativa → cooldown?
    espera = await proximo_cooldown_segundos(db, agora=agora, cooldown_s=cooldown_s)
    if espera > 0:
        return {"acao": "cooldown", "proximo_em_segundos": espera}

    # 3) Pega o próximo queued
    proximo = (
        await db.execute(
            select(GuiaFila).where(GuiaFila.status == "queued").order_by(GuiaFila.id).limit(1)
        )
    ).scalar_one_or_none()
    if proximo is None:
        return {"acao": "nada"}

    proximo.iniciado_em = agora
    if proximo.guia_id is None:
        try:
            guia = await resolver(db, proximo.url, page_size=200)
            proximo.guia_id = guia.id
        except Exception as exc:  # noqa: BLE001 — qualquer falha de resolve conta tentativa
            proximo.tentativas += 1
            proximo.erro = str(exc)[:500]
            if proximo.tentativas >= max_tentativas:
                proximo.status = "error"
                proximo.finalizado_em = agora
            await db.flush()
            return {"acao": "erro_resolver", "fila_id": proximo.id, "tentativas": proximo.tentativas}

    enq, falhas = await enqueue(db, proximo.guia_id, page_size=200)
    proximo.status = "collecting"
    # marca o Guia como coletando (UI)
    guia_row = (
        await db.execute(select(Guia).where(Guia.id == proximo.guia_id))
    ).scalar_one_or_none()
    if guia_row is not None:
        guia_row.status = "collecting"
    await db.flush()
    return {"acao": "iniciou", "fila_id": proximo.id, "enqueued": enq, "falhas": falhas}
```

> Adicionar no topo de `guia_service.py` o import: `from models import Guia, GuiaFila` (já tem `GuiaFila`; incluir `Guia`).

- [ ] **Step 4: Rodar — deve passar**

Run: `./dev.sh test test_guia_supervisor.py -v`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/guia_service.py backend/tests/test_guia_supervisor.py
git commit -m "feat(coleta): tick do supervisor de guias (serial + cooldown + auto-skip)"
```

---

### Task 6: Runner do supervisor (`scripts/guia_supervisor.py`)

**Files:**
- Create: `backend/scripts/guia_supervisor.py`
- Test: `backend/tests/test_guia_supervisor.py` (config loader)

**Interfaces:**
- Consumes: `guia_supervisor_tick`, `database.async_session`.
- Produces: `def carregar_config() -> dict` + `async def loop() -> None` + `__main__`.

- [ ] **Step 1: Teste do loader de config (falhando)**

Acrescentar a `backend/tests/test_guia_supervisor.py`:

```python
def test_carregar_config_defaults(monkeypatch):
    for k in ("GUIA_COOLDOWN_SECONDS", "GUIA_SUPERVISOR_INTERVAL",
              "GUIA_MAX_COLETA_SECONDS", "GUIA_RESOLVE_MAX_TENTATIVAS"):
        monkeypatch.delenv(k, raising=False)
    from scripts.guia_supervisor import carregar_config

    cfg = carregar_config()
    assert cfg == {
        "cooldown_s": 900,
        "interval": 30,
        "max_coleta_s": 21600,
        "max_tentativas": 3,
    }
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `./dev.sh test test_guia_supervisor.py::test_carregar_config_defaults -v`
Expected: FAIL (`ModuleNotFoundError: scripts.guia_supervisor`).

- [ ] **Step 3: Implementar o runner**

Criar `backend/scripts/guia_supervisor.py`:

```python
"""Supervisor da fila de coleta de guias.

Loop em processo separado (imagem do backend): a cada `GUIA_SUPERVISOR_INTERVAL`
segundos chama `guia_service.guia_supervisor_tick`, que garante 1 guia coletando
por vez com cooldown entre guias. Roda como serviço `studia-guia-supervisor`
(replicas: 1).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime


def carregar_config() -> dict:
    return {
        "cooldown_s": int(os.getenv("GUIA_COOLDOWN_SECONDS", "900")),
        "interval": int(os.getenv("GUIA_SUPERVISOR_INTERVAL", "30")),
        "max_coleta_s": int(os.getenv("GUIA_MAX_COLETA_SECONDS", "21600")),
        "max_tentativas": int(os.getenv("GUIA_RESOLVE_MAX_TENTATIVAS", "3")),
    }


async def loop() -> None:
    import guia_service
    from database import async_session

    cfg = carregar_config()
    print(f"guia_supervisor iniciado: {cfg}", flush=True)
    while True:
        try:
            async with async_session() as db:
                out = await guia_service.guia_supervisor_tick(
                    db,
                    agora=datetime.utcnow(),
                    cooldown_s=cfg["cooldown_s"],
                    max_coleta_s=cfg["max_coleta_s"],
                    max_tentativas=cfg["max_tentativas"],
                )
                await db.commit()
            if out.get("acao") not in (None, "nada", "aguardando"):
                print(f"guia_supervisor.tick {out}", flush=True)
        except Exception as exc:  # noqa: BLE001 — loop nunca morre por 1 falha
            print(f"guia_supervisor.erro {exc!r}", flush=True)
        await asyncio.sleep(max(cfg["interval"], 5))


if __name__ == "__main__":
    asyncio.run(loop())
```

> Confirmar o nome do sessionmaker em `backend/database.py` (`async_session`). Se for outro (ex.: `AsyncSessionLocal`), ajustar o import. Run: `grep -n "sessionmaker\|async_session" backend/database.py`.

- [ ] **Step 4: Rodar — deve passar**

Run: `./dev.sh test test_guia_supervisor.py -v`
Expected: PASS (incluindo o config loader).

- [ ] **Step 5: Smoke do runner (importa sem erro)**

Run: `./dev.sh shell backend` então `python -c "import scripts.guia_supervisor as s; print(s.carregar_config())"`
Expected: imprime o dict de config. (Ou `docker compose -f docker-compose.dev.yml exec backend python -c "import scripts.guia_supervisor"`.)

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/guia_supervisor.py backend/tests/test_guia_supervisor.py
git commit -m "feat(coleta): runner do supervisor de guias (loop + config por env)"
```

---

### Task 7: Serviço `studia-guia-supervisor` no Docker

**Files:**
- Modify: `docker/stack.yml`
- Modify: `docker-compose.dev.yml`

**Interfaces:**
- Consumes: imagem do backend + `scripts/guia_supervisor.py` (Task 6).

- [ ] **Step 1: Adicionar o serviço no stack de produção**

Em `docker/stack.yml`, logo após o serviço `worker` (que usa `*backend-image`), adicionar (copiando o bloco `environment`/`networks`/`deploy` do `worker`, trocando só o `command` e o nome):

```yaml
  studia-guia-supervisor:
    image: *backend-image
    env_file:
      - ${STUDIA_ENV_FILE:-/opt/studia/.env}
    environment:
      MINIO_ENDPOINT: minio:9000
      MEILI_URL: http://studia-meili:7700
      SCRAPER_URL: http://studia-scraper:8090
      PYTHONDONTWRITEBYTECODE: "1"
      TZ: America/Fortaleza
      NATS_SERVERS: nats://nats:4222
      TASKIQ_RESULT_REDIS_URL: redis://redis:6379/2
      GUIA_COOLDOWN_SECONDS: "900"
      GUIA_SUPERVISOR_INTERVAL: "30"
      GUIA_MAX_COLETA_SECONDS: "21600"
      GUIA_RESOLVE_MAX_TENTATIVAS: "3"
    command: python -m scripts.guia_supervisor
    # Não serve HTTP: desabilita o HEALTHCHECK HTTP herdado da imagem (senão
    # vira unhealthy → crash-loop), igual ao serviço `worker`.
    healthcheck:
      test: ["NONE"]
    networks:
      - minha_rede
    deploy:
      <<: *on-manager
      replicas: 1
```

> O bloco acima espelha o serviço `worker` (mesmo `env_file`, `environment`, `healthcheck: ["NONE"]`, `networks: [minha_rede]`, `deploy: <<: *on-manager`), trocando só o `command` e acrescentando as 4 envs `GUIA_*`. O `env_file` traz `DATABASE_URL` e demais segredos. `*on-manager` não define `replicas`, então `replicas: 1` é adicionado no merge.

- [ ] **Step 2: Adicionar o serviço no dev**

Em `docker-compose.dev.yml`, após o serviço `worker` (linha ~33), adicionar (copiando `build`/`volumes`/`environment`/`networks` do `worker`, trocando `command` e `container_name`):

```yaml
  guia-supervisor:
    build:
      context: ./backend
    container_name: studia-guia-supervisor-dev
    command: python -m scripts.guia_supervisor
    volumes:
      - ./backend:/app
    environment:
      # (mesmo bloco environment do serviço `worker` no dev)
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia
      - SCRAPER_URL=http://scraper:8090
      - GUIA_COOLDOWN_SECONDS=900
      - GUIA_SUPERVISOR_INTERVAL=30
      - GUIA_MAX_COLETA_SECONDS=21600
      - GUIA_RESOLVE_MAX_TENTATIVAS=3
    networks:
      - studia-net
```

> Abrir `docker-compose.dev.yml`, ler o serviço `worker` (linhas ~33-65) e replicar `build`/`volumes`/`environment` idênticos, mudando só `container_name`, `command` e acrescentando as envs `GUIA_*`.

- [ ] **Step 3: Subir e verificar o supervisor no dev**

Run: `docker compose -f docker-compose.dev.yml up -d guia-supervisor && docker logs studia-guia-supervisor-dev`
Expected: log `guia_supervisor iniciado: {...}` e, sem fila, nada de erro.

- [ ] **Step 4: Commit**

```bash
git add docker/stack.yml docker-compose.dev.yml
git commit -m "chore(deploy): serviço studia-guia-supervisor (fila serial de guias)"
```

---

### Task 8: Frontend — textarea de lote + seção "Fila de coleta"

**Files:**
- Modify: `fontend/lib/queryKeys.ts`
- Modify: `fontend/app/q/coletar/GuiasPanel.tsx`

**Interfaces:**
- Consumes (HTTP): `POST /api/q/guias/importar-lote`, `GET /api/q/guias/fila`, `DELETE /api/q/guias/fila/{id}`, `POST /api/q/guias/fila/{id}/pular`.
- Produces: `qk.guiaFila()`.

- [ ] **Step 1: Adicionar a query key**

Em `fontend/lib/queryKeys.ts`, na linha após `comentarioJobs:`:

```ts
  guiaFila: () => ["q", "guias", "fila"] as const,
```

- [ ] **Step 2: Trocar o input único por textarea de lote no `GuiasPanel.tsx`**

Substituir o estado `const [url, setUrl] = useState("");` por `const [urls, setUrls] = useState("");` e a função `importar(...)` (linhas 121-149) por uma versão de lote:

```tsx
  async function importarLote() {
    const lista = urls
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean);
    if (lista.length === 0) {
      setMsg("Cole uma ou mais URLs de guias (uma por linha).");
      return;
    }
    setImportando(true);
    setMsg(null);
    try {
      const r = await apiFetch("/api/q/guias/importar-lote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: lista }),
      });
      const data = await r.json();
      if (!r.ok) setMsg(data.detail || data.message || `HTTP ${r.status}`);
      else {
        setMsg(`✓ ${data.enfileirados} guia(s) adicionados à fila de coleta.`);
        setUrls("");
        await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
        await queryClient.invalidateQueries({ queryKey: qk.guias() });
      }
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setImportando(false);
    }
  }

  // Importar 1 guia (resultado da busca) → também entra na fila.
  async function importar(targetUrl: string, slug?: string) {
    if (slug) setImportandoSlug(slug);
    setMsg(null);
    try {
      const r = await apiFetch("/api/q/guias/importar-lote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: [targetUrl.trim()] }),
      });
      const data = await r.json();
      if (!r.ok) setMsg(data.detail || data.message || `HTTP ${r.status}`);
      else {
        setMsg(`✓ ${data.enfileirados} guia(s) na fila de coleta.`);
        await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
        if (termo) void buscar();
      }
    } finally {
      setImportandoSlug(null);
    }
  }
```

Substituir o bloco do input + checkbox (linhas 182-203) por:

```tsx
      {/* Importar em lote por URLs */}
      <div className="flex flex-col gap-2">
        <textarea
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          placeholder={"Cole uma ou mais URLs de guias (uma por linha)\nhttps://www.tecconcursos.com.br/guias/oab-2026\nhttps://www.tecconcursos.com.br/guias/..."}
          rows={4}
          className="px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary font-mono"
          disabled={importando}
        />
        <button
          onClick={() => void importarLote()}
          disabled={importando}
          className="self-start bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 px-4 py-2 rounded text-sm font-semibold"
        >
          {importando ? "Adicionando…" : "Adicionar à fila de coleta"}
        </button>
        <p className="text-xs text-fg-faint">
          Os guias são coletados <strong>1 por vez</strong>, com pausa de ~15 min entre eles
          para não sobrecarregar o TC — vale igual colando todas de uma vez ou uma a uma.
        </p>
      </div>
```

Remover o estado `iniciarColeta`/`setIniciarColeta` (não é mais usado).

- [ ] **Step 3: Adicionar a query + seção "Fila de coleta"**

Adicionar a interface e a query (após a query `guiasData`, ~linha 95):

```tsx
interface FilaItem {
  id: number;
  url: string | null;
  status: string;
  guia_id: number | null;
  guia_nome: string | null;
  posicao: number | null;
  erro: string | null;
}
interface FilaResp {
  fila: FilaItem[];
  ativo: boolean;
  proximo_em_segundos: number;
}

  const { data: filaData } = useQuery<FilaResp>({
    queryKey: qk.guiaFila(),
    queryFn: () => apiJson<FilaResp>("/api/q/guias/fila"),
    refetchInterval: (q) => {
      const f = q.state.data;
      const naoTerminal = (f?.fila ?? []).some(
        (e) => !["done", "skipped", "error"].includes(e.status),
      );
      return naoTerminal ? 15000 : false;
    },
  });
  const fila = filaData?.fila ?? [];

  async function removerFila(id: number) {
    await apiFetch(`/api/q/guias/fila/${id}`, { method: "DELETE" });
    await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
  }
  async function pularFila(id: number) {
    await apiFetch(`/api/q/guias/fila/${id}/pular`, { method: "POST" });
    await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
  }
```

Inserir a seção JSX logo antes do bloco `{/* Guias importados */}` (linha ~256):

```tsx
      {/* Fila de coleta */}
      {fila.length > 0 && (
        <div className="space-y-2 pt-1">
          <div className="flex items-center justify-between">
            <div className="text-xs text-fg-faint uppercase tracking-wide">Fila de coleta</div>
            {!filaData?.ativo && (filaData?.proximo_em_segundos ?? 0) > 0 && (
              <span className="text-[11px] text-amber-400">
                Esfriando — próximo guia em ~{Math.ceil((filaData!.proximo_em_segundos) / 60)} min
              </span>
            )}
          </div>
          {fila.map((e) => {
            const terminal = ["done", "skipped", "error"].includes(e.status);
            const label =
              e.status === "collecting" ? "Coletando"
              : e.status === "resolving" ? "Resolvendo"
              : e.status === "queued" ? `Na fila${e.posicao ? ` #${e.posicao}` : ""}`
              : e.status === "done" ? "Concluído"
              : e.status === "skipped" ? "Pulado"
              : "Erro";
            const cor =
              e.status === "collecting" || e.status === "resolving" ? "text-primary border-primary/40 bg-primary/15"
              : e.status === "done" ? "text-success border-success/40 bg-success/15"
              : e.status === "error" ? "text-error border-error/40 bg-error/15"
              : "text-fg border-border bg-surface-2";
            return (
              <div key={e.id} className="rounded border border-border bg-black/20 p-2 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm text-fg truncate">
                    {e.guia_nome || e.url || `Guia ${e.guia_id ?? e.id}`}
                  </div>
                  {e.erro && <div className="text-[11px] text-error truncate">{e.erro}</div>}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${cor}`}>{label}</span>
                  {e.status === "queued" && (
                    <button onClick={() => void removerFila(e.id)} className="text-xs text-fg-faint hover:text-error px-1" title="Remover da fila">✕</button>
                  )}
                  {(e.status === "collecting" || e.status === "resolving") && (
                    <button onClick={() => void pularFila(e.id)} className="text-xs text-amber-400 hover:text-amber-300 px-1" title="Pular guia">Pular</button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
```

- [ ] **Step 4: Lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros (sem variáveis não usadas — confirmar que `iniciarColeta` foi removido e `apiJson` está importado, já está na linha 5).

- [ ] **Step 5: Commit**

```bash
git add fontend/lib/queryKeys.ts fontend/app/q/coletar/GuiasPanel.tsx
git commit -m "feat(coleta): UI de lote (textarea) + seção Fila de coleta com cooldown e pular"
```

---

### Task 9: Verificação final + workflow do projeto

**Files:** nenhum novo.

- [ ] **Step 1: Suíte backend completa**

Run: `./dev.sh test -v`
Expected: PASS (inclui `test_guia_fila`, `test_guia_supervisor`, `test_guias_router`, `test_alembic_no_drift`).

- [ ] **Step 2: Lint frontend**

Run: `cd fontend && pnpm lint`
Expected: sem erros.

- [ ] **Step 3: Smoke manual no dev (fluxo de ponta a ponta)**

1. `./dev.sh up:d` (sobe tudo, incl. `guia-supervisor`).
2. Abrir `/q/coletar`, colar 2 URLs de guia (uma por linha), "Adicionar à fila".
3. Verificar `GET /api/q/guias/fila`: 1º guia `collecting` (ou `resolving`), 2º `queued #1`.
4. `docker logs studia-guia-supervisor-dev` mostra `acao: iniciou`.
5. Após o 1º concluir, confirmar `proximo_em_segundos > 0` (cooldown) e que o 2º só inicia depois.

- [ ] **Step 4: Workflow obrigatório (CLAUDE.md): push + deploy**

```bash
git push
./build.sh
```
Expected: build + push de imagens + `db_prepare` (aplica a migração `guia_fila`) + `docker stack deploy`. Confirmar o serviço `studia-guia-supervisor` rodando em prod:
`ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 "docker service ls | grep guia-supervisor"`

- [ ] **Step 5: Worktree limpo**

Run: `git status`
Expected: limpo (sem pendências).

---

## Self-Review (preenchido)

**1. Cobertura do spec:**
- Fila FIFO `guia_fila` → Task 1. ✓
- Supervisor (1 por vez, cooldown entre guias, 1º imediato, auto-skip 6h) → Task 5 (tick) + Task 6 (runner) + Task 7 (serviço). ✓
- Resolve preguiçoso → Task 3 (`resolver_e_salvar`) + tick chama na vez do guia. ✓
- Endpoints `importar` (apenas_catalogar), `importar-lote`, `{id}/coletar`→fila, `GET/DELETE/pular /fila` → Task 4. ✓
- Config por env → Task 6/7. ✓
- Frontend (textarea, fila, cooldown, pular) → Task 8. ✓
- Testes (invariantes do tick + endpoints) → Tasks 2-5. ✓
- Deploy + migração no startup → Task 7/9. ✓
- Fora de escopo (`/api/q/coletar` avulso, adoção de coletas legadas) → respeitado. ✓

**2. Placeholders:** os blocos `environment:` do Docker (Tasks 7) pedem para copiar do `worker` — é instrução de leitura explícita, não placeholder de código. Demais steps têm código completo.

**3. Consistência de tipos:** nomes batem entre tasks — `resolver_e_salvar(db, *, url, relogin, page_size) -> (Guia, list)`, `enqueue_cadernos_do_guia(db, guia_id, *, page_size) -> (int, list)`, `guia_coleta_completa(db, guia_id) -> bool`, `guia_supervisor_tick(...) -> dict` com `acao` em {iniciou, aguardando, concluiu, cooldown, pulou_timeout, erro_resolver, nada}; deps do tick (`resolver/enqueue/completa`) batem com os defaults; `qk.guiaFila()` usado no front. ✓
