# Question Card Canvas Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PDF-like annotation mode for the studIA question card, with a switchable canvas overlay, double-click strike-through targets, a scientific calculator, and persisted history.

**Architecture:** Backend stores annotation state as JSON per caderno + questao and calculator history as separate rows. Frontend keeps the existing question flow, wraps the question card in a measured overlay, stores vector strokes with normalized coordinates, and hides the canvas without deleting saved strokes. Calculator focus and active canvas mode prevent normal question hotkeys from firing.

**Tech Stack:** FastAPI, SQLAlchemy async, Postgres, pytest, Next.js 16, React 19, Tailwind CSS v4, Material Symbols.

---

## File Structure

Backend:

- Modify `backend/requirements.txt`: add test-only packages used by backend tests.
- Create `backend/tests/conftest.py`: async SQLite test database and FastAPI client fixtures.
- Create `backend/tests/test_q_annotation_models.py`: model/index smoke tests.
- Create `backend/tests/test_q_annotations_api.py`: annotation API tests.
- Create `backend/tests/test_q_calculator_api.py`: calculator history API tests.
- Modify `backend/models.py`: add `QuestaoAnotacao` and `CalculadoraHistorico`.
- Modify `backend/migrate.py`: create the expression unique index for annotation scope.
- Modify `backend/q_router.py`: add schemas and routes for annotations and calculator history.

Frontend:

- Modify `fontend/app/hooks/useHotkeys.ts`: allow optional `enabled` guard.
- Create `fontend/app/q/caderno/[id]/annotations/types.ts`: shared annotation types and empty factories.
- Create `fontend/app/q/caderno/[id]/annotations/api.ts`: fetch helpers for annotations and calculator history.
- Create `fontend/app/q/caderno/[id]/annotations/useQuestionAnnotations.ts`: load/save state, debounce, local fallback.
- Create `fontend/app/q/caderno/[id]/components/CanvasToolbar.tsx`: switch and tools.
- Create `fontend/app/q/caderno/[id]/components/QuestionCanvasOverlay.tsx`: pointer drawing and rendering.
- Create `fontend/app/q/caderno/[id]/components/ScientificCalculator.tsx`: calculator panel and history.
- Create `fontend/app/q/caderno/[id]/components/math.ts`: safe expression evaluator.
- Create `fontend/app/q/caderno/[id]/components/StrikableAlternative.tsx`: double-click strike target.
- Modify `fontend/app/q/caderno/[id]/page.tsx`: integrate hook, toolbar, overlay, calculator, strike targets, and guarded hotkeys.

Commit rule for each task: this repository is dirty. Before each commit, run `git status --short` and stage only the files listed in that task.

---

### Task 1: Backend Test Scaffold

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Add backend test dependencies**

Append these lines to `backend/requirements.txt`:

```txt
# test support
pytest>=8.3.0
pytest-asyncio>=0.24.0
aiosqlite>=0.20.0
```

- [ ] **Step 2: Create async API test fixtures**

Create `backend/tests/conftest.py`:

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database import get_db
from main import app
from models import Base


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

- [ ] **Step 3: Verify pytest imports**

Run:

```bash
cd backend
python -m pytest --version
```

Expected: prints a pytest version and exits `0`.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/tests/conftest.py
git commit -m "test(backend): add async api test scaffold"
```

---

### Task 2: Annotation and Calculator Models

**Files:**
- Create: `backend/tests/test_q_annotation_models.py`
- Modify: `backend/models.py`
- Modify: `backend/migrate.py`

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/test_q_annotation_models.py`:

```python
from models import CalculadoraHistorico, QuestaoAnotacao


def test_annotation_model_uses_expected_table_and_index():
    assert QuestaoAnotacao.__tablename__ == "questao_anotacoes"
    columns = set(QuestaoAnotacao.__table__.columns.keys())
    assert {
        "id",
        "usuario_id",
        "caderno_id",
        "questao_id",
        "canvas_json",
        "strikes_json",
        "created_at",
        "updated_at",
    }.issubset(columns)
    index_names = {index.name for index in QuestaoAnotacao.__table__.indexes}
    assert "uq_questao_anotacoes_scope" in index_names


def test_calculator_history_model_uses_expected_table():
    assert CalculadoraHistorico.__tablename__ == "calculadora_historico"
    columns = set(CalculadoraHistorico.__table__.columns.keys())
    assert {
        "id",
        "usuario_id",
        "caderno_id",
        "questao_id",
        "expression",
        "result",
        "created_at",
    }.issubset(columns)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
python -m pytest tests/test_q_annotation_models.py -q
```

Expected: FAIL with import errors for `QuestaoAnotacao` and `CalculadoraHistorico`.

- [ ] **Step 3: Add models**

Modify `backend/models.py`:

1. Add `Index` to the SQLAlchemy imports.
2. Add these classes after `Resolucao` and before `CadernoQuestoes`:

```python
class QuestaoAnotacao(Base):
    """Canvas and strike-through state for one question in one caderno scope."""

    __tablename__ = "questao_anotacoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    caderno_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canvas_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    strikes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "uq_questao_anotacoes_scope",
            func.coalesce(usuario_id, 0),
            func.coalesce(caderno_id, 0),
            questao_id,
            unique=True,
        ),
    )


class CalculadoraHistorico(Base):
    """Scientific calculator history, optionally linked to a question."""

    __tablename__ = "calculadora_historico"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    caderno_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    questao_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
```

- [ ] **Step 4: Make migration idempotently create the annotation expression index**

Modify `backend/migrate.py` after `await conn.run_sync(Base.metadata.create_all)`:

```python
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_questao_anotacoes_scope
            ON questao_anotacoes (COALESCE(usuario_id, 0), COALESCE(caderno_id, 0), questao_id)
        """))
```

- [ ] **Step 5: Run model tests**

Run:

```bash
cd backend
python -m pytest tests/test_q_annotation_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/migrate.py backend/tests/test_q_annotation_models.py
git commit -m "feat(backend): add question annotation models"
```

---

### Task 3: Annotation API

**Files:**
- Create: `backend/tests/test_q_annotations_api.py`
- Modify: `backend/q_router.py`

- [ ] **Step 1: Write failing annotation API tests**

Create `backend/tests/test_q_annotations_api.py`:

```python
import pytest

from models import CadernoQuestoes, Questao

pytestmark = pytest.mark.asyncio


async def seed_question(db_session):
    db_session.add(CadernoQuestoes(id=10, nome="Caderno", question_ids=[99], total=1))
    db_session.add(
        Questao(
            id=99,
            id_externo=3966994,
            tipo="MULTIPLA_ESCOLHA",
            enunciado_html="<p>Enunciado</p>",
            gabarito="A",
            status="ATIVA",
        )
    )
    await db_session.commit()


async def test_get_missing_annotation_returns_empty_state(client, db_session):
    await seed_question(db_session)

    response = await client.get("/api/q/cadernos/10/questoes/99/annotations")

    assert response.status_code == 200
    data = response.json()
    assert data["caderno_id"] == 10
    assert data["questao_id"] == 99
    assert data["canvas_json"] == {"version": 1, "cardSize": None, "strokes": []}
    assert data["strikes_json"] == {"version": 1, "targets": []}


async def test_put_annotation_persists_canvas_and_strikes(client, db_session):
    await seed_question(db_session)
    payload = {
        "canvas_json": {
            "version": 1,
            "cardSize": {"width": 900, "height": 600},
            "strokes": [
                {
                    "id": "stroke_1",
                    "tool": "pen",
                    "color": "#22c55e",
                    "width": 4,
                    "points": [{"x": 0.2, "y": 0.3, "p": 0.6}],
                }
            ],
        },
        "strikes_json": {
            "version": 1,
            "targets": [{"type": "alternative", "id": 321}],
        },
    }

    put_response = await client.put(
        "/api/q/cadernos/10/questoes/99/annotations",
        json=payload,
    )
    get_response = await client.get("/api/q/cadernos/10/questoes/99/annotations")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["canvas_json"] == payload["canvas_json"]
    assert get_response.json()["strikes_json"] == payload["strikes_json"]


async def test_put_annotation_updates_existing_row(client, db_session):
    await seed_question(db_session)

    await client.put(
        "/api/q/cadernos/10/questoes/99/annotations",
        json={"canvas_json": {"version": 1, "cardSize": None, "strokes": []}, "strikes_json": {"version": 1, "targets": []}},
    )
    response = await client.put(
        "/api/q/cadernos/10/questoes/99/annotations",
        json={
            "canvas_json": {"version": 1, "cardSize": None, "strokes": [{"id": "stroke_2"}]},
            "strikes_json": {"version": 1, "targets": [{"type": "alternative", "id": 8}]},
        },
    )

    assert response.status_code == 200
    assert response.json()["canvas_json"]["strokes"] == [{"id": "stroke_2"}]
    assert response.json()["strikes_json"]["targets"] == [{"type": "alternative", "id": 8}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
python -m pytest tests/test_q_annotations_api.py -q
```

Expected: FAIL with `404 Not Found` for the annotation routes.

- [ ] **Step 3: Add schemas and helpers**

Modify `backend/q_router.py` imports:

```python
from models import (
    Alternativa,
    Banca,
    CalculadoraHistorico,
    CadernoQuestoes,
    Cargo,
    Materia,
    Orgao,
    Questao,
    QuestaoAnotacao,
    Resolucao,
)
```

Add this after `ResponderReq`:

```python
def _empty_canvas() -> dict[str, Any]:
    return {"version": 1, "cardSize": None, "strokes": []}


def _empty_strikes() -> dict[str, Any]:
    return {"version": 1, "targets": []}


class AnnotationReq(BaseModel):
    canvas_json: dict[str, Any] = Field(default_factory=_empty_canvas)
    strikes_json: dict[str, Any] = Field(default_factory=_empty_strikes)


def _annotation_response(row: QuestaoAnotacao | None, caderno_id: int, questao_id: int) -> dict[str, Any]:
    return {
        "id": row.id if row else None,
        "usuario_id": row.usuario_id if row else None,
        "caderno_id": caderno_id,
        "questao_id": questao_id,
        "canvas_json": row.canvas_json if row else _empty_canvas(),
        "strikes_json": row.strikes_json if row else _empty_strikes(),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }
```

- [ ] **Step 4: Add annotation routes before `@router.get("/{questao_id}")`**

Insert these routes before the current detail route:

```python
@router.get("/cadernos/{caderno_id}/questoes/{questao_id}/annotations")
async def get_annotations(caderno_id: int, questao_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    q = (await db.execute(select(Questao.id).where(Questao.id == questao_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "questao não encontrada")

    row = (await db.execute(
        select(QuestaoAnotacao).where(
            QuestaoAnotacao.usuario_id.is_(None),
            QuestaoAnotacao.caderno_id == caderno_id,
            QuestaoAnotacao.questao_id == questao_id,
        )
    )).scalar_one_or_none()
    return _annotation_response(row, caderno_id, questao_id)


@router.put("/cadernos/{caderno_id}/questoes/{questao_id}/annotations")
async def put_annotations(
    caderno_id: int,
    questao_id: int,
    req: AnnotationReq,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    q = (await db.execute(select(Questao.id).where(Questao.id == questao_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "questao não encontrada")

    row = (await db.execute(
        select(QuestaoAnotacao).where(
            QuestaoAnotacao.usuario_id.is_(None),
            QuestaoAnotacao.caderno_id == caderno_id,
            QuestaoAnotacao.questao_id == questao_id,
        )
    )).scalar_one_or_none()
    if row:
        row.canvas_json = req.canvas_json
        row.strikes_json = req.strikes_json
    else:
        row = QuestaoAnotacao(
            usuario_id=None,
            caderno_id=caderno_id,
            questao_id=questao_id,
            canvas_json=req.canvas_json,
            strikes_json=req.strikes_json,
        )
        db.add(row)

    await db.commit()
    await db.refresh(row)
    return _annotation_response(row, caderno_id, questao_id)
```

- [ ] **Step 5: Run annotation API tests**

Run:

```bash
cd backend
python -m pytest tests/test_q_annotations_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/q_router.py backend/tests/test_q_annotations_api.py
git commit -m "feat(backend): add question annotation api"
```

---

### Task 4: Calculator History API

**Files:**
- Create: `backend/tests/test_q_calculator_api.py`
- Modify: `backend/q_router.py`

- [ ] **Step 1: Write failing calculator API tests**

Create `backend/tests/test_q_calculator_api.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_calculator_history_post_and_list(client):
    payload = {
        "expression": "sin(30)",
        "result": "0.5",
        "caderno_id": 10,
        "questao_id": 99,
    }

    post_response = await client.post("/api/q/calculator/history", json=payload)
    list_response = await client.get("/api/q/calculator/history?caderno_id=10&questao_id=99")

    assert post_response.status_code == 200
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["expression"] == "sin(30)"
    assert items[0]["result"] == "0.5"


async def test_calculator_history_delete(client):
    response = await client.post(
        "/api/q/calculator/history",
        json={"expression": "2+2", "result": "4", "caderno_id": None, "questao_id": None},
    )
    item_id = response.json()["id"]

    delete_response = await client.delete(f"/api/q/calculator/history/{item_id}")
    list_response = await client.get("/api/q/calculator/history")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}
    assert list_response.json()["items"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
python -m pytest tests/test_q_calculator_api.py -q
```

Expected: FAIL with `404 Not Found` for calculator routes.

- [ ] **Step 3: Add schemas**

Add this near `AnnotationReq` in `backend/q_router.py`:

```python
class CalculatorHistoryReq(BaseModel):
    expression: str = Field(..., min_length=1, max_length=512)
    result: str = Field(..., min_length=1, max_length=512)
    caderno_id: int | None = None
    questao_id: int | None = None
```

- [ ] **Step 4: Add calculator routes before `@router.get("/{questao_id}")`**

Insert before the dynamic detail route:

```python
@router.get("/calculator/history")
async def list_calculator_history(
    caderno_id: int | None = None,
    questao_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from sqlalchemy import desc

    stmt = select(CalculadoraHistorico).where(CalculadoraHistorico.usuario_id.is_(None))
    if caderno_id is not None:
        stmt = stmt.where(CalculadoraHistorico.caderno_id == caderno_id)
    if questao_id is not None:
        stmt = stmt.where(CalculadoraHistorico.questao_id == questao_id)
    rows = (await db.execute(stmt.order_by(desc(CalculadoraHistorico.created_at)).limit(50))).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "usuario_id": row.usuario_id,
                "caderno_id": row.caderno_id,
                "questao_id": row.questao_id,
                "expression": row.expression,
                "result": row.result,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.post("/calculator/history")
async def create_calculator_history(req: CalculatorHistoryReq, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = CalculadoraHistorico(
        usuario_id=None,
        caderno_id=req.caderno_id,
        questao_id=req.questao_id,
        expression=req.expression.strip(),
        result=req.result.strip(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "usuario_id": row.usuario_id,
        "caderno_id": row.caderno_id,
        "questao_id": row.questao_id,
        "expression": row.expression,
        "result": row.result,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/calculator/history/{item_id}")
async def delete_calculator_history(item_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    row = (await db.execute(
        select(CalculadoraHistorico).where(
            CalculadoraHistorico.id == item_id,
            CalculadoraHistorico.usuario_id.is_(None),
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "historico não encontrado")
    await db.delete(row)
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 5: Run calculator API tests**

Run:

```bash
cd backend
python -m pytest tests/test_q_calculator_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/q_router.py backend/tests/test_q_calculator_api.py
git commit -m "feat(backend): add calculator history api"
```

---

### Task 5: Frontend Annotation Data Layer

**Files:**
- Modify: `fontend/app/hooks/useHotkeys.ts`
- Create: `fontend/app/q/caderno/[id]/annotations/types.ts`
- Create: `fontend/app/q/caderno/[id]/annotations/api.ts`
- Create: `fontend/app/q/caderno/[id]/annotations/useQuestionAnnotations.ts`

- [ ] **Step 1: Add optional hotkey enable guard**

Modify `fontend/app/hooks/useHotkeys.ts` signature and effect:

```ts
export function useHotkeys(
  map: Record<string, (e: KeyboardEvent) => void>,
  options: { enabled?: boolean } = {},
) {
  const enabled = options.enabled ?? true;

  useEffect(() => {
    if (!enabled) return;

    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if ((e.target as HTMLElement | null)?.isContentEditable) return;

      const ctrl = e.ctrlKey || e.metaKey;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const combo = ctrl ? `Ctrl+${key}` : key;

      const cb = map[combo] ?? map[key];
      if (cb) {
        e.preventDefault();
        cb(e);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [map, enabled]);
}
```

- [ ] **Step 2: Create annotation types**

Create `fontend/app/q/caderno/[id]/annotations/types.ts`:

```ts
export type CanvasTool = "pen" | "highlight" | "eraser";

export interface CanvasPoint {
  x: number;
  y: number;
  p?: number;
}

export interface CanvasStroke {
  id: string;
  tool: Exclude<CanvasTool, "eraser">;
  color: string;
  width: number;
  points: CanvasPoint[];
}

export interface CanvasState {
  version: 1;
  cardSize: { width: number; height: number } | null;
  strokes: CanvasStroke[];
}

export type StrikeTarget =
  | { type: "alternative"; id: number }
  | { type: "statement-block"; index: number };

export interface StrikesState {
  version: 1;
  targets: StrikeTarget[];
}

export interface AnnotationState {
  id: number | null;
  caderno_id: number;
  questao_id: number;
  canvas_json: CanvasState;
  strikes_json: StrikesState;
  updated_at: string | null;
}

export interface CalculatorHistoryItem {
  id: number;
  caderno_id: number | null;
  questao_id: number | null;
  expression: string;
  result: string;
  created_at: string | null;
}

export function emptyCanvas(): CanvasState {
  return { version: 1, cardSize: null, strokes: [] };
}

export function emptyStrikes(): StrikesState {
  return { version: 1, targets: [] };
}
```

- [ ] **Step 3: Create API helpers**

Create `fontend/app/q/caderno/[id]/annotations/api.ts`:

```ts
import type { AnnotationState, CalculatorHistoryItem, CanvasState, StrikesState } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

export async function fetchAnnotations(cadernoId: number, questaoId: number): Promise<AnnotationState> {
  const response = await fetch(`${API}/api/q/cadernos/${cadernoId}/questoes/${questaoId}/annotations`);
  if (!response.ok) throw new Error(`Falha ao carregar anotacoes: ${response.status}`);
  return response.json();
}

export async function saveAnnotations(
  cadernoId: number,
  questaoId: number,
  canvas_json: CanvasState,
  strikes_json: StrikesState,
): Promise<AnnotationState> {
  const response = await fetch(`${API}/api/q/cadernos/${cadernoId}/questoes/${questaoId}/annotations`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ canvas_json, strikes_json }),
  });
  if (!response.ok) throw new Error(`Falha ao salvar anotacoes: ${response.status}`);
  return response.json();
}

export async function fetchCalculatorHistory(cadernoId?: number, questaoId?: number): Promise<CalculatorHistoryItem[]> {
  const params = new URLSearchParams();
  if (cadernoId != null) params.set("caderno_id", String(cadernoId));
  if (questaoId != null) params.set("questao_id", String(questaoId));
  const qs = params.toString();
  const response = await fetch(`${API}/api/q/calculator/history${qs ? `?${qs}` : ""}`);
  if (!response.ok) throw new Error(`Falha ao carregar historico: ${response.status}`);
  const data = await response.json();
  return data.items || [];
}

export async function createCalculatorHistory(input: {
  expression: string;
  result: string;
  caderno_id: number | null;
  questao_id: number | null;
}): Promise<CalculatorHistoryItem> {
  const response = await fetch(`${API}/api/q/calculator/history`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(`Falha ao salvar historico: ${response.status}`);
  return response.json();
}
```

- [ ] **Step 4: Create annotation hook**

Create `fontend/app/q/caderno/[id]/annotations/useQuestionAnnotations.ts`:

```ts
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchAnnotations, saveAnnotations } from "./api";
import type { CanvasState, StrikeTarget, StrikesState } from "./types";
import { emptyCanvas, emptyStrikes } from "./types";

function keyFor(cadernoId: number, questaoId: number) {
  return `studia:q:${cadernoId}:${questaoId}:annotations`;
}

function hasTarget(targets: StrikeTarget[], target: StrikeTarget) {
  return targets.some((item) => {
    if (item.type !== target.type) return false;
    if (item.type === "alternative" && target.type === "alternative") return item.id === target.id;
    if (item.type === "statement-block" && target.type === "statement-block") return item.index === target.index;
    return false;
  });
}

export function useQuestionAnnotations(cadernoId: number | null, questaoId: number | null) {
  const [canvas, setCanvas] = useState<CanvasState>(emptyCanvas);
  const [strikes, setStrikes] = useState<StrikesState>(emptyStrikes);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadedKey = useMemo(() => (cadernoId && questaoId ? keyFor(cadernoId, questaoId) : null), [cadernoId, questaoId]);

  useEffect(() => {
    if (!cadernoId || !questaoId) return;
    let cancelled = false;
    setLoading(true);
    setSaveError(null);

    const localRaw = localStorage.getItem(keyFor(cadernoId, questaoId));
    if (localRaw) {
      try {
        const local = JSON.parse(localRaw);
        setCanvas(local.canvas_json || emptyCanvas());
        setStrikes(local.strikes_json || emptyStrikes());
      } catch {
        localStorage.removeItem(keyFor(cadernoId, questaoId));
      }
    } else {
      setCanvas(emptyCanvas());
      setStrikes(emptyStrikes());
    }

    fetchAnnotations(cadernoId, questaoId)
      .then((data) => {
        if (cancelled) return;
        setCanvas(data.canvas_json || emptyCanvas());
        setStrikes(data.strikes_json || emptyStrikes());
        localStorage.removeItem(keyFor(cadernoId, questaoId));
      })
      .catch((error) => {
        if (!cancelled) setSaveError(error instanceof Error ? error.message : "Falha ao carregar anotacoes");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cadernoId, questaoId]);

  const flush = useCallback(async (nextCanvas: CanvasState, nextStrikes: StrikesState) => {
    if (!cadernoId || !questaoId) return;
    setSaving(true);
    setSaveError(null);
    try {
      await saveAnnotations(cadernoId, questaoId, nextCanvas, nextStrikes);
      localStorage.removeItem(keyFor(cadernoId, questaoId));
    } catch (error) {
      localStorage.setItem(keyFor(cadernoId, questaoId), JSON.stringify({ canvas_json: nextCanvas, strikes_json: nextStrikes }));
      setSaveError(error instanceof Error ? error.message : "Falha ao salvar anotacoes");
    } finally {
      setSaving(false);
    }
  }, [cadernoId, questaoId]);

  const scheduleSave = useCallback((nextCanvas: CanvasState, nextStrikes: StrikesState) => {
    if (!loadedKey) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      void flush(nextCanvas, nextStrikes);
    }, 700);
  }, [flush, loadedKey]);

  const updateCanvas = useCallback((updater: (current: CanvasState) => CanvasState) => {
    setCanvas((current) => {
      const next = updater(current);
      scheduleSave(next, strikes);
      return next;
    });
  }, [scheduleSave, strikes]);

  const toggleStrike = useCallback((target: StrikeTarget) => {
    setStrikes((current) => {
      const nextTargets = hasTarget(current.targets, target)
        ? current.targets.filter((item) => !hasTarget([item], target))
        : [...current.targets, target];
      const next = { version: 1 as const, targets: nextTargets };
      scheduleSave(canvas, next);
      return next;
    });
  }, [canvas, scheduleSave]);

  const clearCanvas = useCallback(() => {
    const next = emptyCanvas();
    setCanvas(next);
    scheduleSave(next, strikes);
  }, [scheduleSave, strikes]);

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  return {
    canvas,
    strikes,
    loading,
    saving,
    saveError,
    updateCanvas,
    setCanvas,
    toggleStrike,
    clearCanvas,
    flush: () => flush(canvas, strikes),
  };
}
```

- [ ] **Step 5: Run frontend lint**

Run:

```bash
cd fontend
pnpm lint
```

Expected: no new lint errors from the files added in this task.

- [ ] **Step 6: Commit**

```bash
git add fontend/app/hooks/useHotkeys.ts fontend/app/q/caderno/[id]/annotations
git commit -m "feat(frontend): add question annotation data layer"
```

---

### Task 6: Canvas Overlay UI

**Files:**
- Create: `fontend/app/q/caderno/[id]/components/CanvasToolbar.tsx`
- Create: `fontend/app/q/caderno/[id]/components/QuestionCanvasOverlay.tsx`

- [ ] **Step 1: Create toolbar component**

Create `fontend/app/q/caderno/[id]/components/CanvasToolbar.tsx`:

```tsx
"use client";

import { Icon } from "../../../../components/ds/Icon";
import type { CanvasTool } from "../annotations/types";

interface CanvasToolbarProps {
  active: boolean;
  tool: CanvasTool;
  color: string;
  width: number;
  hasStrokes: boolean;
  saving: boolean;
  saveError: string | null;
  onActiveChange: (active: boolean) => void;
  onToolChange: (tool: CanvasTool) => void;
  onColorChange: (color: string) => void;
  onWidthChange: (width: number) => void;
  onClear: () => void;
  onOpenCalculator: () => void;
}

export function CanvasToolbar({
  active,
  tool,
  color,
  width,
  hasStrokes,
  saving,
  saveError,
  onActiveChange,
  onToolChange,
  onColorChange,
  onWidthChange,
  onClear,
  onOpenCalculator,
}: CanvasToolbarProps) {
  const tools: Array<{ id: CanvasTool; icon: string; label: string }> = [
    { id: "pen", icon: "draw", label: "Lapis" },
    { id: "highlight", icon: "ink_highlighter", label: "Marca-texto" },
    { id: "eraser", icon: "ink_eraser", label: "Borracha" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <button
        type="button"
        onClick={() => onActiveChange(!active)}
        className={`h-8 inline-flex items-center gap-2 rounded-full border px-2.5 transition ${
          active ? "border-cyan-400 bg-cyan-500/15 text-cyan-200" : "border-gray-700 bg-gray-900/60 text-gray-400 hover:text-gray-100"
        }`}
        title="Ativar/desativar canvas"
      >
        <span className={`h-4 w-7 rounded-full p-0.5 transition ${active ? "bg-cyan-500" : "bg-gray-700"}`}>
          <span className={`block h-3 w-3 rounded-full bg-white transition ${active ? "translate-x-3" : ""}`} />
        </span>
        Canvas
      </button>

      {active && (
        <>
          <div className="flex items-center gap-1 rounded-lg border border-gray-700 bg-gray-950/70 p-1">
            {tools.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onToolChange(item.id)}
                className={`grid h-7 w-7 place-items-center rounded ${tool === item.id ? "bg-cyan-500 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"}`}
                title={item.label}
              >
                <Icon name={item.icon} size={18} />
              </button>
            ))}
          </div>
          <input
            type="color"
            value={color}
            onChange={(event) => onColorChange(event.target.value)}
            className="h-8 w-8 rounded border border-gray-700 bg-gray-900"
            title="Cor do traco"
          />
          <input
            type="range"
            min={2}
            max={18}
            value={width}
            onChange={(event) => onWidthChange(Number(event.target.value))}
            className="w-24 accent-cyan-500"
            title="Espessura"
          />
          <button
            type="button"
            disabled={!hasStrokes}
            onClick={onClear}
            className="h-8 inline-flex items-center gap-1 rounded border border-gray-700 px-2 text-gray-300 hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
            title="Limpar canvas"
          >
            <Icon name="delete" size={16} />
            Limpar
          </button>
        </>
      )}

      <button
        type="button"
        onClick={onOpenCalculator}
        className="h-8 inline-flex items-center gap-1 rounded border border-gray-700 px-2 text-gray-300 hover:bg-gray-800"
        title="Calculadora cientifica"
      >
        <Icon name="calculate" size={16} />
        Calc
      </button>

      <span className="text-[11px] text-gray-500">
        {saving ? "Salvando..." : saveError ? "Salvamento pendente" : ""}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Create canvas overlay component**

Create `fontend/app/q/caderno/[id]/components/QuestionCanvasOverlay.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CanvasState, CanvasStroke, CanvasTool } from "../annotations/types";

interface QuestionCanvasOverlayProps {
  active: boolean;
  canvas: CanvasState;
  tool: CanvasTool;
  color: string;
  width: number;
  onChange: (updater: (current: CanvasState) => CanvasState) => void;
}

function makeStroke(tool: Exclude<CanvasTool, "eraser">, color: string, width: number, x: number, y: number, pressure: number): CanvasStroke {
  return {
    id: `stroke_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    tool,
    color,
    width,
    points: [{ x, y, p: pressure }],
  };
}

function distanceToStroke(stroke: CanvasStroke, x: number, y: number) {
  return Math.min(...stroke.points.map((point) => Math.hypot(point.x - x, point.y - y)));
}

export function QuestionCanvasOverlay({ active, canvas, tool, color, width, onChange }: QuestionCanvasOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState({ width: 1, height: 1 });
  const currentStroke = useRef<CanvasStroke | null>(null);

  useEffect(() => {
    const node = canvasRef.current;
    const parent = node?.parentElement;
    if (!node || !parent) return;

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      node.width = Math.max(1, Math.floor(rect.width * dpr));
      node.height = Math.max(1, Math.floor(rect.height * dpr));
      node.style.width = `${rect.width}px`;
      node.style.height = `${rect.height}px`;
      setSize({ width: rect.width, height: rect.height });
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const node = canvasRef.current;
    if (!node) return;
    const ctx = node.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.clearRect(0, 0, node.width, node.height);
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    for (const stroke of canvas.strokes) {
      if (stroke.points.length === 0) continue;
      ctx.globalAlpha = stroke.tool === "highlight" ? 0.35 : 1;
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.width;
      ctx.beginPath();
      ctx.moveTo(stroke.points[0].x * size.width, stroke.points[0].y * size.height);
      for (const point of stroke.points.slice(1)) {
        ctx.lineTo(point.x * size.width, point.y * size.height);
      }
      ctx.stroke();
    }

    ctx.restore();
  }, [canvas.strokes, size]);

  const pointFromEvent = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
      p: event.pressure || 0.5,
    };
  }, []);

  const onPointerDown = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!active) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointFromEvent(event);
    if (tool === "eraser") {
      onChange((current) => ({
        ...current,
        strokes: current.strokes.filter((stroke) => distanceToStroke(stroke, point.x, point.y) > 0.025),
      }));
      return;
    }
    currentStroke.current = makeStroke(tool, color, width, point.x, point.y, point.p);
  }, [active, color, onChange, pointFromEvent, tool, width]);

  const onPointerMove = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!active) return;
    const point = pointFromEvent(event);
    if (tool === "eraser" && event.buttons === 1) {
      onChange((current) => ({
        ...current,
        strokes: current.strokes.filter((stroke) => distanceToStroke(stroke, point.x, point.y) > 0.025),
      }));
      return;
    }
    if (!currentStroke.current || event.buttons !== 1) return;
    currentStroke.current.points.push(point);
  }, [active, onChange, pointFromEvent, tool]);

  const onPointerUp = useCallback(() => {
    if (!currentStroke.current) return;
    const stroke = currentStroke.current;
    currentStroke.current = null;
    onChange((current) => ({
      version: 1,
      cardSize: { width: size.width, height: size.height },
      strokes: [...current.strokes, stroke],
    }));
  }, [onChange, size.height, size.width]);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 z-20 touch-none rounded-lg ${active ? "cursor-crosshair bg-cyan-500/[0.02]" : "pointer-events-none hidden"}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      aria-hidden={!active}
    />
  );
}
```

- [ ] **Step 3: Run frontend lint**

Run:

```bash
cd fontend
pnpm lint
```

Expected: no new lint errors from the toolbar or overlay files.

- [ ] **Step 4: Commit**

```bash
git add fontend/app/q/caderno/[id]/components/CanvasToolbar.tsx fontend/app/q/caderno/[id]/components/QuestionCanvasOverlay.tsx
git commit -m "feat(frontend): add question canvas overlay"
```

---

### Task 7: Calculator UI and Safe Evaluator

**Files:**
- Create: `fontend/app/q/caderno/[id]/components/math.ts`
- Create: `fontend/app/q/caderno/[id]/components/ScientificCalculator.tsx`

- [ ] **Step 1: Create safe evaluator**

Create `fontend/app/q/caderno/[id]/components/math.ts`:

```ts
const FUNCTIONS: Record<string, (value: number) => number> = {
  sin: (value) => Math.sin((value * Math.PI) / 180),
  cos: (value) => Math.cos((value * Math.PI) / 180),
  tan: (value) => Math.tan((value * Math.PI) / 180),
  log: (value) => Math.log10(value),
  ln: (value) => Math.log(value),
  sqrt: (value) => Math.sqrt(value),
};

const PRECEDENCE: Record<string, number> = { "+": 1, "-": 1, "*": 2, "/": 2, "^": 3 };

function tokenize(expression: string): string[] {
  const tokens: string[] = [];
  let i = 0;
  while (i < expression.length) {
    const char = expression[i];
    if (/\s/.test(char)) {
      i += 1;
      continue;
    }
    if (/[0-9.]/.test(char)) {
      let value = char;
      i += 1;
      while (i < expression.length && /[0-9.]/.test(expression[i])) {
        value += expression[i];
        i += 1;
      }
      tokens.push(value);
      continue;
    }
    if (/[a-z]/i.test(char)) {
      let value = char.toLowerCase();
      i += 1;
      while (i < expression.length && /[a-z]/i.test(expression[i])) {
        value += expression[i].toLowerCase();
        i += 1;
      }
      tokens.push(value);
      continue;
    }
    if ("+-*/^()%".includes(char)) {
      tokens.push(char);
      i += 1;
      continue;
    }
    throw new Error(`Caractere invalido: ${char}`);
  }
  return tokens;
}

function toRpn(tokens: string[]) {
  const output: string[] = [];
  const ops: string[] = [];
  for (const token of tokens) {
    if (!Number.isNaN(Number(token))) {
      output.push(token);
    } else if (FUNCTIONS[token]) {
      ops.push(token);
    } else if (token === "(") {
      ops.push(token);
    } else if (token === ")") {
      while (ops.length && ops[ops.length - 1] !== "(") output.push(ops.pop() as string);
      if (ops.pop() !== "(") throw new Error("Parenteses invalidos");
      if (ops.length && FUNCTIONS[ops[ops.length - 1]]) output.push(ops.pop() as string);
    } else if (token === "%") {
      output.push(token);
    } else if (PRECEDENCE[token]) {
      while (ops.length && PRECEDENCE[ops[ops.length - 1]] >= PRECEDENCE[token]) output.push(ops.pop() as string);
      ops.push(token);
    } else {
      throw new Error(`Token invalido: ${token}`);
    }
  }
  while (ops.length) {
    const op = ops.pop() as string;
    if (op === "(" || op === ")") throw new Error("Parenteses invalidos");
    output.push(op);
  }
  return output;
}

export function evaluateExpression(expression: string): string {
  const stack: number[] = [];
  for (const token of toRpn(tokenize(expression))) {
    if (!Number.isNaN(Number(token))) {
      stack.push(Number(token));
    } else if (token === "%") {
      const value = stack.pop();
      if (value == null) throw new Error("Expressao invalida");
      stack.push(value / 100);
    } else if (FUNCTIONS[token]) {
      const value = stack.pop();
      if (value == null) throw new Error("Expressao invalida");
      stack.push(FUNCTIONS[token](value));
    } else {
      const b = stack.pop();
      const a = stack.pop();
      if (a == null || b == null) throw new Error("Expressao invalida");
      if (token === "+") stack.push(a + b);
      if (token === "-") stack.push(a - b);
      if (token === "*") stack.push(a * b);
      if (token === "/") stack.push(a / b);
      if (token === "^") stack.push(a ** b);
    }
  }
  if (stack.length !== 1 || !Number.isFinite(stack[0])) throw new Error("Expressao invalida");
  return Number.parseFloat(stack[0].toFixed(10)).toString();
}
```

- [ ] **Step 2: Create calculator panel**

Create `fontend/app/q/caderno/[id]/components/ScientificCalculator.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { createCalculatorHistory, fetchCalculatorHistory } from "../annotations/api";
import type { CalculatorHistoryItem } from "../annotations/types";
import { evaluateExpression } from "./math";

interface ScientificCalculatorProps {
  open: boolean;
  cadernoId: number;
  questaoId: number;
  onClose: () => void;
}

const KEYS = ["sin(", "cos(", "tan(", "log(", "ln(", "sqrt(", "^", "%", "(", ")", "7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "0", ".", "=", "+"];

export function ScientificCalculator({ open, cadernoId, questaoId, onClose }: ScientificCalculatorProps) {
  const [expression, setExpression] = useState("");
  const [result, setResult] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<CalculatorHistoryItem[]>([]);

  useEffect(() => {
    if (!open) return;
    fetchCalculatorHistory(cadernoId, questaoId)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [cadernoId, open, questaoId]);

  if (!open) return null;

  async function calculate() {
    try {
      const next = evaluateExpression(expression);
      setResult(next);
      setError(null);
      const item = await createCalculatorHistory({
        expression,
        result: next,
        caderno_id: cadernoId,
        questao_id: questaoId,
      });
      setHistory((items) => [item, ...items].slice(0, 20));
    } catch (calcError) {
      setError(calcError instanceof Error ? calcError.message : "Expressao invalida");
    }
  }

  function press(key: string) {
    if (key === "=") {
      void calculate();
      return;
    }
    setExpression((value) => `${value}${key}`);
  }

  return (
    <div className="fixed right-6 top-28 z-50 w-[360px] rounded-lg border border-gray-700 bg-[#1a1a1a] shadow-2xl">
      <div className="flex items-center border-b border-gray-700 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-200">Calculadora</h3>
        <button type="button" onClick={onClose} className="ml-auto text-gray-400 hover:text-white">Fechar</button>
      </div>
      <div className="p-4">
        <input
          value={expression}
          onChange={(event) => setExpression(event.target.value)}
          className="mb-2 w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-right font-mono text-sm text-gray-100 outline-none focus:border-cyan-500"
          autoFocus
        />
        <div className="mb-3 text-right font-mono text-3xl text-white">{result}</div>
        {error && <div className="mb-2 rounded border border-red-900 bg-red-950/50 px-2 py-1 text-xs text-red-300">{error}</div>}
        <div className="grid grid-cols-4 gap-1.5">
          {KEYS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => press(key)}
              className={`h-10 rounded border border-gray-700 text-sm hover:bg-gray-800 ${key === "=" ? "bg-cyan-600 text-white" : "bg-gray-900 text-gray-200"}`}
            >
              {key}
            </button>
          ))}
          <button type="button" onClick={() => setExpression("")} className="col-span-2 h-10 rounded border border-gray-700 bg-gray-900 text-sm text-gray-200 hover:bg-gray-800">C</button>
          <button type="button" onClick={() => setExpression((value) => value.slice(0, -1))} className="col-span-2 h-10 rounded border border-gray-700 bg-gray-900 text-sm text-gray-200 hover:bg-gray-800">Apagar</button>
        </div>
        <div className="mt-4 max-h-40 overflow-y-auto border-t border-gray-800 pt-3">
          <div className="mb-2 text-xs uppercase text-gray-500">Historico</div>
          {history.length === 0 && <div className="text-xs text-gray-500">Sem contas salvas nesta questao.</div>}
          {history.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                setExpression(item.expression);
                setResult(item.result);
              }}
              className="block w-full rounded px-2 py-1 text-left font-mono text-xs text-gray-400 hover:bg-gray-800"
            >
              {item.expression} = <span className="text-cyan-300">{item.result}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run frontend lint**

Run:

```bash
cd fontend
pnpm lint
```

Expected: no new lint errors from calculator files.

- [ ] **Step 4: Commit**

```bash
git add fontend/app/q/caderno/[id]/components/math.ts fontend/app/q/caderno/[id]/components/ScientificCalculator.tsx
git commit -m "feat(frontend): add scientific calculator panel"
```

---

### Task 8: Strike Targets and Page Integration

**Files:**
- Create: `fontend/app/q/caderno/[id]/components/StrikableAlternative.tsx`
- Modify: `fontend/app/q/caderno/[id]/page.tsx`

- [ ] **Step 1: Create strikable alternative component**

Create `fontend/app/q/caderno/[id]/components/StrikableAlternative.tsx`:

```tsx
"use client";

import type { ReactNode } from "react";

interface StrikableAlternativeProps {
  id: number;
  letra: string;
  selected: boolean;
  disabled: boolean;
  struck: boolean;
  className: string;
  onSelect: () => void;
  onToggleStrike: () => void;
  children: ReactNode;
}

export function StrikableAlternative({
  letra,
  selected,
  disabled,
  struck,
  className,
  onSelect,
  onToggleStrike,
  children,
}: StrikableAlternativeProps) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onSelect()}
      onDoubleClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onToggleStrike();
      }}
      disabled={disabled}
      className={className}
      title="Dois cliques riscam ou restauram esta alternativa"
    >
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-sm ${
        selected ? "border-cyan-400 text-cyan-300" : "border-gray-600 text-gray-400"
      }`}>
        {letra}
      </span>
      <span className={`flex-1 ${struck ? "text-gray-500 line-through decoration-red-500 decoration-2" : ""}`}>
        {children}
      </span>
    </button>
  );
}
```

- [ ] **Step 2: Import new components and hook in page**

Modify imports at the top of `fontend/app/q/caderno/[id]/page.tsx`:

```ts
import type { CanvasTool, StrikeTarget } from "./annotations/types";
import { useQuestionAnnotations } from "./annotations/useQuestionAnnotations";
import { CanvasToolbar } from "./components/CanvasToolbar";
import { QuestionCanvasOverlay } from "./components/QuestionCanvasOverlay";
import { ScientificCalculator } from "./components/ScientificCalculator";
import { StrikableAlternative } from "./components/StrikableAlternative";
```

- [ ] **Step 3: Add canvas/calculator state to `CadernoPage`**

Inside `CadernoPage`, after existing UI state declarations:

```ts
  const [canvasActive, setCanvasActive] = useState(false);
  const [canvasTool, setCanvasTool] = useState<CanvasTool>("pen");
  const [canvasColor, setCanvasColor] = useState("#22c55e");
  const [canvasWidth, setCanvasWidth] = useState(5);
  const [calculatorOpen, setCalculatorOpen] = useState(false);
  const questionCardRef = useRef<HTMLDivElement | null>(null);
```

Then, immediately after the existing `currentQid` declaration, add the hook:

```ts
  const annotations = useQuestionAnnotations(caderno?.id ?? null, currentQid ?? null);
```

- [ ] **Step 4: Guard hotkeys while canvas is active**

Change the `useHotkeys` call so navigation callbacks no-op while the canvas is active, and calculator focus disables all page hotkeys:

```ts
  useHotkeys({
    ArrowLeft: () => { if (!canvasActive) avancar(-1); },
    ArrowRight: () => { if (!canvasActive) avancar(1); },
    l: () => { if (!canvasActive) aleatoria(); },
    n: () => { if (!canvasActive) avancar(1); },
    p: () => {
      if (canvasActive) return;
      const num = prompt(`Ir para questão (1 a ${caderno?.total}):`);
      if (num && /^\d+$/.test(num)) {
        const n = Math.min(Math.max(parseInt(num), 1), caderno?.total || 1) - 1;
        setIdx(n);
      }
    },
    m: () => { if (!canvasActive) setFav((f) => !f); },
    j: () => { if (!canvasActive) setFav((f) => !f); },
    k: () => setModoLeitura((m) => !m),
    "+": () => setFontSize((s) => Math.min(28, s + 2)),
    "=": () => setFontSize((s) => Math.min(28, s + 2)),
    "-": () => setFontSize((s) => Math.max(12, s - 2)),
    "0": () => setFontSize(16),
    ".": () => setPausado((p) => !p),
    "?": () => setShowAtalhos(true),
    Escape: () => setCanvasActive(false),
  }, { enabled: !calculatorOpen });
```

- [ ] **Step 5: Add helpers for strike lookup**

Before the `return`, add:

```ts
  function isStruck(target: StrikeTarget) {
    return annotations.strikes.targets.some((item) => {
      if (item.type !== target.type) return false;
      if (item.type === "alternative" && target.type === "alternative") return item.id === target.id;
      if (item.type === "statement-block" && target.type === "statement-block") return item.index === target.index;
      return false;
    });
  }
```

- [ ] **Step 6: Wrap the card with ref, toolbar, and overlay**

In the `tab === "Questoes"` block, change the card wrapper from:

```tsx
<div className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] mb-4">
```

to:

```tsx
<div ref={questionCardRef} className="relative mb-4 rounded-lg border border-gray-700/60 bg-[#1a1a1a]">
  <QuestionCanvasOverlay
    active={canvasActive}
    canvas={annotations.canvas}
    tool={canvasTool}
    color={canvasColor}
    width={canvasWidth}
    onChange={annotations.updateCanvas}
  />
```

Keep the existing card children after the overlay.

- [ ] **Step 7: Place the toolbar in the card header**

Inside the header action area, before the existing comment/theory/forum buttons, add:

```tsx
<CanvasToolbar
  active={canvasActive}
  tool={canvasTool}
  color={canvasColor}
  width={canvasWidth}
  hasStrokes={annotations.canvas.strokes.length > 0}
  saving={annotations.saving}
  saveError={annotations.saveError}
  onActiveChange={setCanvasActive}
  onToolChange={setCanvasTool}
  onColorChange={setCanvasColor}
  onWidthChange={setCanvasWidth}
  onClear={annotations.clearCanvas}
  onOpenCalculator={() => setCalculatorOpen(true)}
/>
```

- [ ] **Step 8: Make enunciado strikeable as one safe block**

Replace the `article` with:

```tsx
<article
  onDoubleClick={() => annotations.toggleStrike({ type: "statement-block", index: 0 })}
  className={`prose prose-invert prose-cyan max-w-none mb-4 ${
    isStruck({ type: "statement-block", index: 0 }) ? "text-gray-500 line-through decoration-red-500 decoration-2" : ""
  }`}
  title="Dois cliques riscam ou restauram o enunciado"
  dangerouslySetInnerHTML={{ __html: questao.enunciado_html }}
/>
```

- [ ] **Step 9: Replace alternative button with `StrikableAlternative`**

Inside the alternatives map, replace the current `<button>` with:

```tsx
<StrikableAlternative
  id={alt.id}
  letra={alt.letra}
  selected={selecionada === alt.letra}
  disabled={resolvida}
  struck={isStruck({ type: "alternative", id: alt.id })}
  onSelect={() => setSelecionada(alt.letra)}
  onToggleStrike={() => annotations.toggleStrike({ type: "alternative", id: alt.id })}
  className={`w-full text-left flex items-start gap-3 px-3 py-2 rounded border transition ${
    isCorreta ? "border-green-500 bg-green-950/40" :
    isErrada ? "border-red-500 bg-red-950/40" :
    selecionada === alt.letra ? "border-cyan-500 bg-cyan-950/40" :
    "border-gray-700 hover:bg-gray-800/40"
  }`}
>
  <span dangerouslySetInnerHTML={{ __html: alt.texto_md || "" }} />
</StrikableAlternative>
```

- [ ] **Step 10: Mount calculator**

Before the shortcut modal near the bottom of the component return, add:

```tsx
{caderno && questao && (
  <ScientificCalculator
    open={calculatorOpen}
    cadernoId={caderno.id}
    questaoId={questao.id}
    onClose={() => setCalculatorOpen(false)}
  />
)}
```

- [ ] **Step 11: Flush annotations before changing question**

Change `avancar` to:

```ts
  function avancar(delta: number) {
    if (!caderno) return;
    void annotations.flush();
    const novo = Math.max(0, Math.min(caderno.total - 1, idx + delta));
    setIdx(novo);
  }
```

Change `aleatoria` to:

```ts
  function aleatoria() {
    if (!caderno) return;
    void annotations.flush();
    setIdx(Math.floor(Math.random() * caderno.total));
  }
```

- [ ] **Step 12: Run frontend lint**

Run:

```bash
cd fontend
pnpm lint
```

Expected: no new lint errors from the caderno page integration.

- [ ] **Step 13: Commit**

```bash
git add fontend/app/q/caderno/[id]/page.tsx fontend/app/q/caderno/[id]/components/StrikableAlternative.tsx
git commit -m "feat(frontend): integrate canvas overlay into question card"
```

---

### Task 9: End-to-End Verification

**Files:**
- Modify only files needed to fix failures found by the commands below.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
python -m pytest tests -q
```

Expected: PASS for model, annotation API, and calculator API tests.

- [ ] **Step 2: Run migrations**

Run:

```bash
./dev.sh migrate
```

Expected: command exits `0`; output either says migrations were applied or the database is already updated.

- [ ] **Step 3: Run frontend lint**

Run:

```bash
cd fontend
pnpm lint
```

Expected: PASS or only pre-existing lint issues unrelated to the files in this plan. If there are new lint issues in files from this plan, fix them.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd fontend
pnpm build
```

Expected: Next.js build exits `0`.

- [ ] **Step 5: Start the app**

Run:

```bash
./dev.sh detached
```

Expected: frontend available at `http://localhost:3000` and backend available at `http://localhost:8011`.

- [ ] **Step 6: Manual browser verification**

Open `http://localhost:3000/q/caderno/5` and verify:

- Canvas switch appears in the question card header.
- With canvas off, alternative selection works.
- Double-clicking an alternative toggles red strike-through.
- Turning canvas on shows the toolbar and lets the user draw over the whole card.
- Turning canvas off hides strokes and restores normal click behavior.
- Turning canvas on again restores strokes.
- `Limpar` removes canvas strokes and preserves strike-through targets.
- Calculator opens, evaluates `2+2`, saves `4` in history, and does not trigger question navigation while focused.
- Reloading the page restores strike-through and canvas strokes.

- [ ] **Step 7: Commit verification fixes**

If verification required fixes, commit only those fixes:

```bash
git add <fixed-files>
git commit -m "fix: stabilize question canvas overlay verification"
```

If no fixes were needed, do not create an empty commit.
