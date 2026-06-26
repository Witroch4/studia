# Fórum de discussão por questão — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o botão 💬 (placeholder) da página de caderno em um fórum funcional por questão: posts + respostas (1 nível) + votos + ordenação + editar/excluir, com editor markdown+KaTeX e upload de imagem.

**Architecture:** Reaproveita a tabela `questao_comentarios` (hoje dormente/vazia) como tabela única do fórum, com `origem` distinguindo comentário do aluno (`studia`) do importado do TC (`tc`, anonimizado por pseudônimo estável). Backend expõe endpoints em `/api/q/...`; frontend usa React Query + um painel inline. Conteúdo do usuário é renderizado por um pipeline markdown **sanitizado** (anti-XSS), separado do `MarkdownRenderer` confiável existente.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Postgres + MinIO (backend); Next.js 16 + React 19 + React Query + react-markdown + remark-math + rehype-katex + **rehype-sanitize** (frontend).

## Global Constraints

- **Idioma:** comentários de código, mensagens de commit e textos de UI em **Português BR**.
- **Auth:** todos os endpoints do fórum exigem `require_user` (de `auth.py`); `CurrentUser.id` é `str` (Better Auth). Admin = `user.is_admin`.
- **Ordem de rotas:** as rotas novas com prefixo literal (`/questoes/...`, `/forum/...`) DEVEM ser declaradas **antes** de `@router.get("/{questao_id}")` (linha ~1837 de `q_router.py`), senão o catch-all `/{questao_id}` as captura.
- **PK style em `models.py`:** `BigInteger` para PKs (o arquivo já mistura `BigInteger` puro e `.with_variant(Integer, "sqlite")`; siga o estilo local de cada model).
- **Pseudônimo determinístico:** NUNCA use `hash()` do Python (salt por processo). Use `hashlib`.
- **Banco de teste:** `./dev.sh test` cria/migra `studia_test` via `alembic upgrade head` antes do pytest. Toda task de backend que mexe em schema depende da migração (Task 2) já existir.
- **Sanitização obrigatória:** conteúdo de comentário (UGC) é renderizado por `ForumContent` (com `rehype-sanitize`), **nunca** pelo `MarkdownRenderer` (que usa `rehype-raw`).
- **Frontend sem runner de teste unitário:** a verificação de tasks de frontend é `pnpm lint` + `pnpm build` + smoke manual (não há jest/vitest no repo).
- **API base no front:** use os helpers de `@/lib/api` (`apiJson`, `apiPost`, `apiFetch`) e chaves de `@/lib/queryKeys` (`qk`). `API_BASE = process.env.NEXT_PUBLIC_API_URL`.

---

## Mapa de arquivos

**Backend**
- Modificar: `backend/models.py` — colunas novas em `QuestaoComentario`; novo model `ComentarioVoto`.
- Criar: `backend/forum_pseudonimo.py` — pool de nomes + `pseudonimo(seed)`.
- Modificar: `backend/minio_client.py` — `upload_bytes(...)` genérico.
- Modificar: `backend/q_router.py` — endpoints do fórum + `forum_count` no detalhe.
- Criar: `backend/alembic/versions/<hash>_forum_comentarios.py` — migração.
- Criar: `backend/tests/test_forum_pseudonimo.py`, `backend/tests/test_forum_api.py`, `backend/tests/test_forum_upload.py`.

**Frontend**
- Modificar: `fontend/package.json` — dependência `rehype-sanitize`.
- Criar: `fontend/app/components/ForumContent.tsx` — renderer markdown+KaTeX sanitizado.
- Modificar: `fontend/lib/queryKeys.ts` — chave `forum`.
- Criar: `fontend/app/q/hooks/useForum.ts` — tipos + hooks React Query.
- Criar: `fontend/app/q/caderno/[id]/components/CommentEditor.tsx`
- Criar: `fontend/app/q/caderno/[id]/components/CommentItem.tsx`
- Criar: `fontend/app/q/caderno/[id]/components/ForumPanel.tsx`
- Modificar: `fontend/app/q/caderno/[id]/page.tsx` — estado do painel, badge, hotkey `f`.

---

## Task 1: Modelos do fórum + pseudônimo

**Files:**
- Create: `backend/forum_pseudonimo.py`
- Modify: `backend/models.py` (model `QuestaoComentario` ~L643-665; add import `SmallInteger`; novo model `ComentarioVoto`)
- Test: `backend/tests/test_forum_pseudonimo.py`

**Interfaces:**
- Produces: `forum_pseudonimo.pseudonimo(seed: str) -> str` (estável, determinístico).
- Produces: model `QuestaoComentario` com novas colunas `origem: str`, `owner_uid: str|None`, `parent_id: int|None`, `score: int`, `edited_at: datetime|None`, `deleted_at: datetime|None`.
- Produces: model `ComentarioVoto(id, comentario_id, usuario_uid, valor, created_at)` + unique `uq_voto_comentario_usuario`.

- [ ] **Step 1: Escrever o teste do pseudônimo (falhando)**

`backend/tests/test_forum_pseudonimo.py`:

```python
from forum_pseudonimo import pseudonimo, POOL


def test_pseudonimo_e_estavel_para_o_mesmo_seed():
    assert pseudonimo("João da Silva") == pseudonimo("João da Silva")


def test_pseudonimo_vem_do_pool():
    assert pseudonimo("qualquer-autor") in POOL


def test_seeds_diferentes_tendem_a_nomes_diferentes():
    nomes = {pseudonimo(f"autor-{i}") for i in range(20)}
    assert len(nomes) > 1  # não colapsa tudo num nome só


def test_seed_vazio_nao_quebra():
    assert pseudonimo("") in POOL
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./dev.sh test tests/test_forum_pseudonimo.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'forum_pseudonimo'`.

- [ ] **Step 3: Implementar `forum_pseudonimo.py`**

```python
"""Pseudônimo estável para autores importados do TC.

Mesmo autor (mesma `seed`) → sempre o mesmo nome fake, mantendo as threads
coerentes. Determinístico entre processos: usa hashlib (NUNCA hash() do Python,
que é salgado por processo).
"""

from __future__ import annotations

import hashlib

# Pool curado de nomes PT-BR (nome + sobrenome).
POOL: list[str] = [
    "Ana Ribeiro", "Bruno Carvalho", "Camila Nogueira", "Diego Fontes",
    "Elaine Macedo", "Felipe Andrade", "Gabriela Pires", "Henrique Bastos",
    "Isabela Moraes", "João Tavares", "Karina Lemos", "Lucas Barreto",
    "Mariana Cordeiro", "Natália Vasques", "Otávio Peixoto", "Patrícia Coelho",
    "Rafael Quintana", "Sabrina Dorneles", "Thiago Marinho", "Vanessa Aragão",
    "William Sarmento", "Yara Bittencourt", "André Vilela", "Beatriz Couto",
    "Caio Rezende", "Daniela Brito", "Eduardo Sales", "Fernanda Lira",
    "Gustavo Pacheco", "Helena Drummond", "Igor Sampaio", "Juliana Furtado",
]


def pseudonimo(seed: str) -> str:
    """Nome fake determinístico para `seed` (ex.: nome original do autor no TC)."""
    digest = hashlib.sha1((seed or "").encode("utf-8")).hexdigest()
    return POOL[int(digest, 16) % len(POOL)]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./dev.sh test tests/test_forum_pseudonimo.py -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Adicionar `SmallInteger` ao import de `models.py`**

Em `backend/models.py`, no bloco `from sqlalchemy import (...)` (L4-21), adicione `SmallInteger` em ordem alfabética (após `Integer,`):

```python
    Integer,
    JSON,
    SmallInteger,
    String,
```

- [ ] **Step 6: Adicionar colunas novas em `QuestaoComentario`**

Em `backend/models.py`, dentro de `class QuestaoComentario(Base):` (após a linha `curtidas: Mapped[int] = mapped_column(Integer, default=0)`), adicione:

```python
    # ─── Campos do fórum studIA (feed unificado local + TC anonimizado) ───
    origem: Mapped[str] = mapped_column(
        String(16), default="studia", server_default="studia", index=True
    )  # "studia" (aluno) | "tc" (importado, exibido com pseudônimo)
    owner_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("questao_comentarios.id", ondelete="CASCADE"), nullable=True, index=True
    )  # resposta a um post raiz (1 nível só)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 7: Adicionar o model `ComentarioVoto`**

Em `backend/models.py`, logo após a classe `QuestaoComentario` (antes do comentário `# ─── Cronograma ───`):

```python
class ComentarioVoto(Base):
    """Voto (+1/-1) de um usuário em um comentário do fórum. Um por (comentário, usuário)."""

    __tablename__ = "comentario_votos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    comentario_id: Mapped[int] = mapped_column(
        ForeignKey("questao_comentarios.id", ondelete="CASCADE"), index=True
    )
    usuario_uid: Mapped[str] = mapped_column(String(64), index=True)
    valor: Mapped[int] = mapped_column(SmallInteger)  # +1 | -1
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("comentario_id", "usuario_uid", name="uq_voto_comentario_usuario"),
    )
```

- [ ] **Step 8: Sanidade de import dos models**

Run: `./dev.sh shell backend` então `python -c "import models; print(models.ComentarioVoto.__tablename__, [c.name for c in models.QuestaoComentario.__table__.columns])"` (ou rode via `dc exec`).
Expected: imprime `comentario_votos` e a lista de colunas incluindo `origem, owner_uid, parent_id, score, edited_at, deleted_at`. Sem erro de import.

- [ ] **Step 9: Commit**

```bash
git add backend/forum_pseudonimo.py backend/models.py backend/tests/test_forum_pseudonimo.py
git commit -m "feat(forum): models do fórum (comentário unificado + votos) e pseudônimo TC"
```

---

## Task 2: Migração Alembic

**Files:**
- Create: `backend/alembic/versions/<hash>_forum_comentarios.py`
- Test (existente): `backend/tests/test_alembic_no_drift.py`

**Interfaces:**
- Consumes: models da Task 1.
- Produces: schema migrado (colunas em `questao_comentarios` + tabela `comentario_votos`) aplicável via `alembic upgrade head`.

- [ ] **Step 1: Gerar a migração (autogenerate)**

Run (dentro do container backend):
```bash
cd backend && alembic revision --autogenerate -m "forum comentarios e votos"
```
Expected: cria um arquivo em `backend/alembic/versions/`. Anote o `<hash>`.

- [ ] **Step 2: Revisar a migração gerada**

Abra o arquivo gerado e confirme que `upgrade()` contém:
- `op.add_column("questao_comentarios", ...)` para `origem`, `owner_uid`, `parent_id`, `score`, `edited_at`, `deleted_at`;
- `op.create_index(...)` para `owner_uid`, `parent_id`, `score`;
- `op.create_foreign_key(...)` do `parent_id` → `questao_comentarios.id` (`ondelete="CASCADE"`);
- `op.create_table("comentario_votos", ...)` com `uq_voto_comentario_usuario` e índices.

Se o autogenerate não tiver capturado o `server_default` de `origem`/`score`, edite as `add_column` para incluir `server_default="studia"` e `server_default="0"` respectivamente (a tabela está vazia, mas o default protege o `NOT NULL`). Confirme que `down_revision` aponta para a head anterior.

- [ ] **Step 3: Aplicar e rodar o teste de drift**

Run: `./dev.sh test tests/test_alembic_no_drift.py -v`
Expected: PASS — o `alembic upgrade head` roda sem erro e o schema bate com os models (sem drift).

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(forum): migração das tabelas do fórum (questao_comentarios + comentario_votos)"
```

---

## Task 3: Endpoint de leitura do fórum + `forum_count`

**Files:**
- Modify: `backend/q_router.py` (imports; helpers e rotas ANTES de `@router.get("/{questao_id}")`; `forum_count` no `detalhe`)
- Test: `backend/tests/test_forum_api.py`

**Interfaces:**
- Consumes: models `QuestaoComentario`, `ComentarioVoto`; `forum_pseudonimo.pseudonimo`.
- Produces: `GET /api/q/questoes/{questao_id}/forum?ordenar=recentes|pontos` → `{total, comentarios: [...]}`; helper `_serializar_comentario(c, meu_voto, pode_editar, pode_excluir, respostas)`; `forum_count` em `GET /api/q/{questao_id}`.

- [ ] **Step 1: Escrever os testes de leitura (falhando)**

`backend/tests/test_forum_api.py`:

```python
import pytest
from sqlalchemy import select

from conftest import ADMIN_USER, USER_A, USER_B
from models import ComentarioVoto, Questao, QuestaoComentario

pytestmark = pytest.mark.asyncio


async def seed_questao(db_session, qid=99):
    db_session.add(
        Questao(id=qid, id_externo=qid, tipo="MULTIPLA_ESCOLHA",
                enunciado_html="<p>E</p>", gabarito="A", status="ATIVA")
    )
    await db_session.commit()


async def test_forum_vazio_retorna_lista_vazia(client, db_session):
    await seed_questao(db_session)
    r = await client.get("/api/q/questoes/99/forum")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "comentarios": []}


async def test_forum_lista_post_e_resposta_aninhada(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="admin-1", autor_nome="admin-1", texto_md="raiz"))
    await db_session.commit()
    db_session.add(QuestaoComentario(id=2, questao_id=99, origem="studia",
                                     owner_uid="user-A", autor_nome="user-A",
                                     parent_id=1, texto_md="resposta"))
    await db_session.commit()

    r = await client.get("/api/q/questoes/99/forum")
    data = r.json()
    assert data["total"] == 2
    assert len(data["comentarios"]) == 1
    raiz = data["comentarios"][0]
    assert raiz["texto_md"] == "raiz"
    assert raiz["display_name"] == "admin-1"
    assert len(raiz["respostas"]) == 1
    assert raiz["respostas"][0]["texto_md"] == "resposta"


async def test_forum_anonimiza_comentario_do_tc(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="tc",
                                     autor_nome="Fulano Real TC", autor_tipo="aluno",
                                     texto_md="comentário tc", curtidas=5, score=5))
    await db_session.commit()
    r = await client.get("/api/q/questoes/99/forum")
    c = r.json()["comentarios"][0]
    assert c["display_name"] != "Fulano Real TC"  # nome original nunca vaza
    assert c["origem"] == "tc"
    assert c["score"] == 5


async def test_forum_ordena_por_pontos(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="x", autor_nome="x", texto_md="baixo", score=1))
    db_session.add(QuestaoComentario(id=2, questao_id=99, origem="studia",
                                     owner_uid="y", autor_nome="y", texto_md="alto", score=9))
    await db_session.commit()
    r = await client.get("/api/q/questoes/99/forum?ordenar=pontos")
    ids = [c["texto_md"] for c in r.json()["comentarios"]]
    assert ids == ["alto", "baixo"]


async def test_forum_count_no_detalhe(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="x", autor_nome="x", texto_md="a"))
    await db_session.commit()
    r = await client.get("/api/q/99")
    assert r.json()["forum_count"] == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./dev.sh test tests/test_forum_api.py -v`
Expected: FAIL (404 nas rotas `/questoes/.../forum`; `KeyError: forum_count`).

- [ ] **Step 3: Adicionar imports em `q_router.py`**

Em `backend/q_router.py`, no bloco `from models import (...)` (L26-41), adicione `ComentarioVoto,` e `QuestaoComentario,` em ordem alfabética. Após a linha `from auth import ...` adicione:

```python
from forum_pseudonimo import pseudonimo
```

E garanta que `RedirectResponse` e `UploadFile`/`File`/`Form` serão importados nas tasks 5/7 (não agora).

- [ ] **Step 4: Adicionar helpers e a rota de leitura ANTES de `@router.get("/{questao_id}")`**

Imediatamente acima de `@router.get("/{questao_id}")` (L1837), insira:

```python
# ─── Fórum de discussão por questão ───────────────────────────────────────
MAX_COMENTARIO_CHARS = 20_000


def _display_name(c: QuestaoComentario) -> str:
    """studIA: nome real do aluno; TC: pseudônimo estável (nome original nunca vaza)."""
    if c.origem == "tc":
        return pseudonimo(c.autor_nome or str(c.tc_comentario_id or c.id))
    return c.autor_nome or "Anônimo"


def _serializar_comentario(
    c: QuestaoComentario, *, meu_voto: int, user: CurrentUser, respostas: list[dict[str, Any]]
) -> dict[str, Any]:
    removido = c.deleted_at is not None
    nome = _display_name(c)
    dono = c.origem == "studia" and c.owner_uid == user.id
    return {
        "id": c.id,
        "parent_id": c.parent_id,
        "origem": c.origem,
        "display_name": nome,
        "autor_inicial": (nome.strip()[:1] or "?").upper(),
        "texto_md": None if removido else c.texto_md,
        "score": c.score or 0,
        "meu_voto": meu_voto,
        "criado_em": (c.publicado_em or c.created_at).isoformat() if (c.publicado_em or c.created_at) else None,
        "editado": c.edited_at is not None,
        "removido": removido,
        "posso_editar": dono and not removido,
        "posso_excluir": (dono or user.is_admin) and not removido,
        "respostas": respostas,
    }


@router.get("/questoes/{questao_id}/forum")
async def listar_forum(
    questao_id: int,
    ordenar: str = "recentes",
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    todos = (
        await db.execute(
            select(QuestaoComentario).where(QuestaoComentario.questao_id == questao_id)
        )
    ).scalars().all()

    # Votos do usuário atual nesta questão (para `meu_voto`).
    ids = [c.id for c in todos]
    meus: dict[int, int] = {}
    if ids:
        rows = (
            await db.execute(
                select(ComentarioVoto.comentario_id, ComentarioVoto.valor).where(
                    ComentarioVoto.comentario_id.in_(ids),
                    ComentarioVoto.usuario_uid == user.id,
                )
            )
        ).all()
        meus = {cid: val for cid, val in rows}

    # Índice de respostas por pai (1 nível). Respostas deletadas são folhas → descartadas.
    respostas_por_pai: dict[int, list[QuestaoComentario]] = {}
    raizes: list[QuestaoComentario] = []
    for c in todos:
        if c.parent_id is None:
            raizes.append(c)
        elif c.deleted_at is None:
            respostas_por_pai.setdefault(c.parent_id, []).append(c)

    def _serial(c: QuestaoComentario, respostas: list[dict[str, Any]]) -> dict[str, Any]:
        return _serializar_comentario(c, meu_voto=meus.get(c.id, 0), user=user, respostas=respostas)

    out: list[dict[str, Any]] = []
    total = 0
    for raiz in raizes:
        filhos = sorted(respostas_por_pai.get(raiz.id, []), key=lambda x: x.created_at or x.id)
        # Raiz deletada sem filhos vivos → some do feed.
        if raiz.deleted_at is not None and not filhos:
            continue
        respostas = [_serial(f, []) for f in filhos]
        out.append(_serial(raiz, respostas))
        total += (0 if raiz.deleted_at is not None else 1) + len(filhos)

    if ordenar == "pontos":
        out.sort(key=lambda d: (d["score"], d["criado_em"] or ""), reverse=True)
    else:  # recentes
        out.sort(key=lambda d: d["criado_em"] or "", reverse=True)

    return {"total": total, "comentarios": out}
```

- [ ] **Step 5: Adicionar `forum_count` ao `detalhe`**

No `return {...}` da rota `detalhe` (L1854-1871), adicione antes da última chave:

```python
        "forum_count": (await db.execute(
            select(func.count()).select_from(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.deleted_at.is_(None),
            )
        )).scalar_one(),
```

- [ ] **Step 6: Rodar e ver passar**

Run: `./dev.sh test tests/test_forum_api.py -v`
Expected: PASS (5 testes desta task; os de criação/voto vêm depois).

- [ ] **Step 7: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_api.py
git commit -m "feat(forum): GET do fórum (árvore + pseudônimo TC + ordenação) e forum_count no detalhe"
```

---

## Task 4: Criar comentário e resposta (POST)

**Files:**
- Modify: `backend/q_router.py` (modelo Pydantic + rota; ANTES de `/{questao_id}`)
- Test: `backend/tests/test_forum_api.py` (append)

**Interfaces:**
- Consumes: `_serializar_comentario`, `MAX_COMENTARIO_CHARS`.
- Produces: `POST /api/q/questoes/{questao_id}/forum` body `{texto_md: str, parent_id: int|None}` → comentário serializado (201).

- [ ] **Step 1: Escrever os testes (falhando)** — append em `test_forum_api.py`:

```python
async def test_criar_comentario_raiz(client, db_session):
    await seed_questao(db_session)
    r = await client.post("/api/q/questoes/99/forum", json={"texto_md": "olá $x^2$"})
    assert r.status_code == 201
    body = r.json()
    assert body["texto_md"] == "olá $x^2$"
    assert body["parent_id"] is None
    assert body["display_name"] == "admin-1"  # usuário default do conftest


async def test_criar_resposta(client, db_session):
    await seed_questao(db_session)
    raiz = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "raiz"})).json()
    r = await client.post("/api/q/questoes/99/forum",
                          json={"texto_md": "resp", "parent_id": raiz["id"]})
    assert r.status_code == 201
    assert r.json()["parent_id"] == raiz["id"]


async def test_resposta_de_resposta_e_rejeitada(client, db_session):
    await seed_questao(db_session)
    raiz = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "raiz"})).json()
    resp = (await client.post("/api/q/questoes/99/forum",
                              json={"texto_md": "r1", "parent_id": raiz["id"]})).json()
    r = await client.post("/api/q/questoes/99/forum",
                          json={"texto_md": "r2", "parent_id": resp["id"]})
    assert r.status_code == 400


async def test_parent_de_outra_questao_e_rejeitado(client, db_session):
    await seed_questao(db_session, qid=99)
    await seed_questao(db_session, qid=88)
    raiz88 = (await client.post("/api/q/questoes/88/forum", json={"texto_md": "x"})).json()
    r = await client.post("/api/q/questoes/99/forum",
                          json={"texto_md": "y", "parent_id": raiz88["id"]})
    assert r.status_code == 400


async def test_texto_vazio_e_rejeitado(client, db_session):
    await seed_questao(db_session)
    r = await client.post("/api/q/questoes/99/forum", json={"texto_md": "   "})
    assert r.status_code == 422
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./dev.sh test tests/test_forum_api.py -k criar or resposta or parent or vazio -v`
Expected: FAIL (404/405 nas rotas POST).

- [ ] **Step 3: Implementar o modelo Pydantic + rota**

Acima da rota `listar_forum` (ou junto ao bloco do fórum), adicione:

```python
class CriarComentarioReq(BaseModel):
    texto_md: str = Field(..., min_length=1, max_length=MAX_COMENTARIO_CHARS)
    parent_id: int | None = None
```

E após `listar_forum`:

```python
@router.post("/questoes/{questao_id}/forum", status_code=status.HTTP_201_CREATED)
async def criar_comentario(
    questao_id: int,
    req: CriarComentarioReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    texto = req.texto_md.strip()
    if not texto:
        raise HTTPException(422, "comentário vazio")

    existe_q = (await db.execute(select(Questao.id).where(Questao.id == questao_id))).scalar_one_or_none()
    if not existe_q:
        raise HTTPException(404, "questao não encontrada")

    if req.parent_id is not None:
        pai = (await db.execute(
            select(QuestaoComentario).where(QuestaoComentario.id == req.parent_id)
        )).scalar_one_or_none()
        if pai is None or pai.questao_id != questao_id:
            raise HTTPException(400, "comentário pai inválido")
        if pai.parent_id is not None:
            raise HTTPException(400, "respostas só podem ser feitas a um comentário raiz")

    c = QuestaoComentario(
        questao_id=questao_id,
        origem="studia",
        owner_uid=user.id,
        autor_nome=user.name,
        parent_id=req.parent_id,
        texto_md=texto,
        score=0,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _serializar_comentario(c, meu_voto=0, user=user, respostas=[])
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./dev.sh test tests/test_forum_api.py -v`
Expected: PASS (testes de leitura + criação).

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_api.py
git commit -m "feat(forum): criar comentário e resposta (validação de 1 nível e de questão)"
```

---

## Task 5: Editar e excluir (PATCH/DELETE)

**Files:**
- Modify: `backend/q_router.py` (imports `RedirectResponse` ainda não; rotas PATCH/DELETE; ANTES de `/{questao_id}`)
- Test: `backend/tests/test_forum_api.py` (append)

**Interfaces:**
- Produces: `PATCH /api/q/forum/{comentario_id}` body `{texto_md}` → serializado; `DELETE /api/q/forum/{comentario_id}` → `{removido: true}` (soft-delete).

- [ ] **Step 1: Escrever os testes (falhando)** — append:

```python
async def test_editar_proprio_comentario(client, db_session):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    r = await client.patch(f"/api/q/forum/{c['id']}", json={"texto_md": "v2"})
    assert r.status_code == 200
    assert r.json()["texto_md"] == "v2"
    assert r.json()["editado"] is True


async def test_editar_de_outro_usuario_proibido(client, db_session, auth_state):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    auth_state["user"] = USER_B
    r = await client.patch(f"/api/q/forum/{c['id']}", json={"texto_md": "hack"})
    assert r.status_code == 403


async def test_nao_edita_comentario_tc(client, db_session):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=50, questao_id=99, origem="tc",
                                     autor_nome="X", autor_tipo="aluno", texto_md="tc"))
    await db_session.commit()
    r = await client.patch("/api/q/forum/50", json={"texto_md": "edit"})
    assert r.status_code == 403


async def test_excluir_proprio(client, db_session):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    r = await client.delete(f"/api/q/forum/{c['id']}")
    assert r.status_code == 200
    # some do feed (folha deletada)
    assert (await client.get("/api/q/questoes/99/forum")).json()["total"] == 0


async def test_admin_exclui_de_qualquer_um(client, db_session, auth_state):
    await seed_questao(db_session)
    auth_state["user"] = USER_A
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v1"})).json()
    auth_state["user"] = ADMIN_USER
    r = await client.delete(f"/api/q/forum/{c['id']}")
    assert r.status_code == 200


async def test_excluir_raiz_com_resposta_vira_placeholder(client, db_session):
    await seed_questao(db_session)
    raiz = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "raiz"})).json()
    await client.post("/api/q/questoes/99/forum", json={"texto_md": "resp", "parent_id": raiz["id"]})
    await client.delete(f"/api/q/forum/{raiz['id']}")
    data = (await client.get("/api/q/questoes/99/forum")).json()
    assert len(data["comentarios"]) == 1
    assert data["comentarios"][0]["removido"] is True
    assert data["comentarios"][0]["texto_md"] is None
    assert len(data["comentarios"][0]["respostas"]) == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./dev.sh test tests/test_forum_api.py -k editar or excluir or admin or placeholder or tc -v`
Expected: FAIL (404/405).

- [ ] **Step 3: Implementar PATCH e DELETE**

Adicione (no bloco do fórum, antes de `/{questao_id}`):

```python
class EditarComentarioReq(BaseModel):
    texto_md: str = Field(..., min_length=1, max_length=MAX_COMENTARIO_CHARS)


async def _carregar_comentario(comentario_id: int, db: AsyncSession) -> QuestaoComentario:
    c = (await db.execute(
        select(QuestaoComentario).where(QuestaoComentario.id == comentario_id)
    )).scalar_one_or_none()
    if c is None or c.deleted_at is not None:
        raise HTTPException(404, "comentário não encontrado")
    return c


@router.patch("/forum/{comentario_id}")
async def editar_comentario(
    comentario_id: int,
    req: EditarComentarioReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _carregar_comentario(comentario_id, db)
    if c.origem != "studia" or c.owner_uid != user.id:
        raise HTTPException(403, "você só pode editar os seus próprios comentários")
    texto = req.texto_md.strip()
    if not texto:
        raise HTTPException(422, "comentário vazio")
    c.texto_md = texto
    c.edited_at = func.now()
    await db.commit()
    await db.refresh(c)
    meu = (await db.execute(
        select(ComentarioVoto.valor).where(
            ComentarioVoto.comentario_id == c.id, ComentarioVoto.usuario_uid == user.id
        )
    )).scalar_one_or_none() or 0
    return _serializar_comentario(c, meu_voto=meu, user=user, respostas=[])


@router.delete("/forum/{comentario_id}")
async def excluir_comentario(
    comentario_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _carregar_comentario(comentario_id, db)
    dono = c.origem == "studia" and c.owner_uid == user.id
    if not (dono or user.is_admin):
        raise HTTPException(403, "sem permissão para excluir")
    c.deleted_at = func.now()
    await db.commit()
    return {"id": comentario_id, "removido": True}
```

> Nota: o `respostas=[]` no retorno do PATCH é aceitável — o frontend invalida a query do fórum após editar e re-renderiza a árvore completa.

- [ ] **Step 4: Rodar e ver passar**

Run: `./dev.sh test tests/test_forum_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_api.py
git commit -m "feat(forum): editar (dono, só studia) e excluir (dono/admin, soft-delete)"
```

---

## Task 6: Votar (POST) + recálculo de score

**Files:**
- Modify: `backend/q_router.py` (modelo + rota; ANTES de `/{questao_id}`)
- Test: `backend/tests/test_forum_api.py` (append)

**Interfaces:**
- Produces: `POST /api/q/forum/{comentario_id}/voto` body `{valor: -1|0|1}` → `{score: int, meu_voto: int}`.

- [ ] **Step 1: Escrever os testes (falhando)** — append:

```python
async def test_votar_e_recalcular_score(client, db_session, auth_state):
    await seed_questao(db_session)
    auth_state["user"] = USER_A
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v"})).json()
    auth_state["user"] = USER_B
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 1})
    assert r.status_code == 200
    assert r.json() == {"score": 1, "meu_voto": 1}


async def test_trocar_e_remover_voto(client, db_session, auth_state):
    await seed_questao(db_session)
    auth_state["user"] = USER_A
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v"})).json()
    auth_state["user"] = USER_B
    await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 1})
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": -1})
    assert r.json() == {"score": -1, "meu_voto": -1}
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 0})
    assert r.json() == {"score": 0, "meu_voto": 0}


async def test_nao_pode_votar_no_proprio(client, db_session):
    await seed_questao(db_session)
    c = (await client.post("/api/q/questoes/99/forum", json={"texto_md": "v"})).json()
    r = await client.post(f"/api/q/forum/{c['id']}/voto", json={"valor": 1})
    assert r.status_code == 400


async def test_voto_soma_curtidas_do_tc(client, db_session, auth_state):
    await seed_questao(db_session)
    db_session.add(QuestaoComentario(id=70, questao_id=99, origem="tc", autor_nome="X",
                                     autor_tipo="aluno", texto_md="tc", curtidas=3, score=3))
    await db_session.commit()
    auth_state["user"] = USER_A
    r = await client.post("/api/q/forum/70/voto", json={"valor": 1})
    assert r.json()["score"] == 4  # 3 curtidas + 1 voto
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./dev.sh test tests/test_forum_api.py -k voto or votar -v`
Expected: FAIL (404).

- [ ] **Step 3: Implementar voto**

```python
class VotarReq(BaseModel):
    valor: int = Field(..., ge=-1, le=1)  # -1 | 0 | 1 (0 remove)


@router.post("/forum/{comentario_id}/voto")
async def votar_comentario(
    comentario_id: int,
    req: VotarReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _carregar_comentario(comentario_id, db)
    if c.origem == "studia" and c.owner_uid == user.id:
        raise HTTPException(400, "você não pode votar no próprio comentário")

    voto = (await db.execute(
        select(ComentarioVoto).where(
            ComentarioVoto.comentario_id == comentario_id,
            ComentarioVoto.usuario_uid == user.id,
        )
    )).scalar_one_or_none()

    if req.valor == 0:
        if voto is not None:
            await db.delete(voto)
    elif voto is None:
        db.add(ComentarioVoto(comentario_id=comentario_id, usuario_uid=user.id, valor=req.valor))
    else:
        voto.valor = req.valor
    await db.flush()

    soma = (await db.execute(
        select(func.coalesce(func.sum(ComentarioVoto.valor), 0)).where(
            ComentarioVoto.comentario_id == comentario_id
        )
    )).scalar_one()
    c.score = int(c.curtidas or 0) + int(soma)
    await db.commit()
    return {"score": c.score, "meu_voto": req.valor}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./dev.sh test tests/test_forum_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_api.py
git commit -m "feat(forum): votar (toggle/trocar/remover), score = curtidas TC + votos, bloqueia auto-voto"
```

---

## Task 7: Upload de imagem + redirect

**Files:**
- Modify: `backend/minio_client.py` (`upload_bytes`)
- Modify: `backend/q_router.py` (imports `RedirectResponse`, `UploadFile`, `File`; rotas; ANTES de `/{questao_id}`)
- Test: `backend/tests/test_forum_upload.py`

**Interfaces:**
- Consumes: `minio_client.upload_bytes`, `minio_client.get_presigned_url`.
- Produces: `POST /api/q/forum/upload` (multipart `file`) → `{url}`; `GET /api/q/forum/imagem/{key:path}` → 302.

- [ ] **Step 1: Adicionar `upload_bytes` em `minio_client.py`**

Após `upload_pdf`:

```python
def upload_bytes(object_name: str, data: bytes, content_type: str) -> str:
    """Sobe bytes genéricos ao bucket (reusa o bucket dos PDFs com prefixo no nome)."""
    client = get_minio_client()
    ensure_bucket()
    client.put_object(
        BUCKET_NAME,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{BUCKET_NAME}/{object_name}"
```

- [ ] **Step 2: Escrever os testes (falhando)**

`backend/tests/test_forum_upload.py`:

```python
import pytest

import q_router

pytestmark = pytest.mark.asyncio

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f8f0000000049454e44ae426082"
)


async def test_upload_aceita_png(client, monkeypatch):
    monkeypatch.setattr(q_router, "upload_bytes", lambda *a, **k: "studia-pdfs/forum/x.png")
    r = await client.post(
        "/api/q/forum/upload",
        files={"file": ("foto.png", PNG_1x1, "image/png")},
    )
    assert r.status_code == 200
    assert "/api/q/forum/imagem/forum/" in r.json()["url"]


async def test_upload_rejeita_tipo_invalido(client):
    r = await client.post(
        "/api/q/forum/upload",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 400


async def test_upload_rejeita_arquivo_grande(client):
    grande = b"\x00" * (5 * 1024 * 1024 + 1)
    r = await client.post(
        "/api/q/forum/upload",
        files={"file": ("big.png", grande, "image/png")},
    )
    assert r.status_code == 400
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `./dev.sh test tests/test_forum_upload.py -v`
Expected: FAIL (404 + `AttributeError: upload_bytes`).

- [ ] **Step 4: Imports e rotas em `q_router.py`**

No topo, ajuste o import do FastAPI para incluir `File`, `UploadFile`:

```python
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse
```

Adicione perto dos outros imports:

```python
import uuid as _uuid
from minio_client import upload_bytes, get_presigned_url
```

No bloco do fórum (antes de `/{questao_id}`):

```python
_FORUM_IMG_TIPOS = {
    "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif",
}
_FORUM_IMG_MAX = 5 * 1024 * 1024  # 5 MB
_FORUM_KEY_RE = _re.compile(r"^forum/[0-9a-f-]{36}\.(png|jpg|webp|gif)$")


@router.post("/forum/upload")
async def upload_imagem_forum(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
) -> dict[str, Any]:
    ext = _FORUM_IMG_TIPOS.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(400, "tipo de imagem não suportado (use png, jpg, webp ou gif)")
    data = await file.read()
    if len(data) > _FORUM_IMG_MAX:
        raise HTTPException(400, "imagem acima de 5 MB")
    key = f"forum/{_uuid.uuid4()}.{ext}"
    upload_bytes(key, data, file.content_type)
    return {"url": f"/api/q/forum/imagem/{key}"}


@router.get("/forum/imagem/{key:path}")
async def imagem_forum(key: str) -> RedirectResponse:
    if not _FORUM_KEY_RE.match(key):
        raise HTTPException(404, "imagem não encontrada")
    return RedirectResponse(get_presigned_url(key), status_code=302)
```

> O retorno `url` é relativo (`/api/q/...`); o frontend prefixa com `API_BASE` na hora de inserir no markdown (Task 10).

- [ ] **Step 5: Rodar e ver passar**

Run: `./dev.sh test tests/test_forum_upload.py -v`
Expected: PASS (3 testes).

- [ ] **Step 6: Rodar a suíte do fórum inteira**

Run: `./dev.sh test tests/test_forum_api.py tests/test_forum_upload.py tests/test_forum_pseudonimo.py tests/test_alembic_no_drift.py -v`
Expected: PASS (tudo verde).

- [ ] **Step 7: Commit**

```bash
git add backend/minio_client.py backend/q_router.py backend/tests/test_forum_upload.py
git commit -m "feat(forum): upload de imagem (MinIO, valida tipo/tamanho) + redirect presigned"
```

---

## Task 8: Dependência + `ForumContent` (renderer sanitizado)

**Files:**
- Modify: `fontend/package.json` (dep `rehype-sanitize`)
- Create: `fontend/app/components/ForumContent.tsx`

**Interfaces:**
- Produces: `<ForumContent content={string} className?={string} />` — renderiza markdown + `$...$`/`$$...$$`, sanitizado, com `<img>` apenas do endpoint do fórum.

- [ ] **Step 1: Instalar `rehype-sanitize`**

Run: `cd fontend && pnpm add rehype-sanitize`
Expected: adiciona `"rehype-sanitize"` em `dependencies` (compatível com unified 11 / react-markdown 10).

- [ ] **Step 2: Criar `ForumContent.tsx`**

```tsx
"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { API_BASE } from "@/lib/api";

/**
 * Renderiza conteúdo de comentário do fórum (gerado por usuário).
 *
 * Diferente do MarkdownRenderer (que usa rehype-raw e é só para conteúdo
 * CONFIÁVEL), aqui o pipeline é SANITIZADO contra XSS:
 *  - rehype-sanitize roda ANTES do rehype-katex; assim o HTML do usuário é
 *    higienizado e só então o KaTeX renderiza as fórmulas a partir dos nós math.
 *  - <img> só é aceito se apontar para o endpoint de imagem do fórum.
 */
const schema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "span", "div"],
  attributes: {
    ...defaultSchema.attributes,
    span: [...(defaultSchema.attributes?.span ?? []), ["className", "math", "math-inline", "math-display"]],
    div: [...(defaultSchema.attributes?.div ?? []), ["className", "math", "math-display"]],
    img: [...(defaultSchema.attributes?.img ?? []), "src", "alt", "title"],
  },
};

function imagemPermitida(src: string | undefined): boolean {
  if (!src) return false;
  return src.includes("/api/q/forum/imagem/");
}

const components: Components = {
  h1: ({ children }) => <h3 className="text-base font-bold text-fg-strong mt-3 mb-1.5">{children}</h3>,
  h2: ({ children }) => <h3 className="text-base font-bold text-fg-strong mt-3 mb-1.5">{children}</h3>,
  h3: ({ children }) => <h4 className="text-sm font-bold text-fg-strong mt-2 mb-1">{children}</h4>,
  p: ({ children }) => <p className="text-fg text-sm leading-relaxed mb-2">{children}</p>,
  strong: ({ children }) => <strong className="text-fg-strong font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 mb-2 marker:text-primary/50">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 mb-2">{children}</ol>,
  li: ({ children }) => <li className="text-fg text-sm leading-relaxed">{children}</li>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="bg-black/30 px-1.5 py-0.5 rounded text-primary font-mono text-xs">{children}</code>
  ),
  img: ({ src, alt }) => {
    const url = typeof src === "string" ? src : "";
    if (!imagemPermitida(url)) {
      return <span className="text-error text-xs">[imagem bloqueada]</span>;
    }
    const full = url.startsWith("http") ? url : `${API_BASE}${url}`;
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={full} alt={alt || ""} className="max-w-full rounded-lg my-2 border border-border" />;
  },
};

interface ForumContentProps {
  content: string;
  className?: string;
}

export default function ForumContent({ content, className = "" }: ForumContentProps) {
  return (
    <div className={`forum-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeSanitize, schema], rehypeKatex]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
```

- [ ] **Step 3: Verificar lint/types**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos em `ForumContent.tsx`.

- [ ] **Step 4: Smoke manual da sanitização**

Com o dev rodando (`./dev.sh`), num componente temporário ou no painel (depois da Task 12), renderizar `content = "**oi** <script>alert(1)</script> $$D_h = CV \\times TH$$"` e confirmar: **oi** em negrito, fórmula renderizada pelo KaTeX, e o `<script>` **não** executa (removido).

- [ ] **Step 5: Commit**

```bash
git add fontend/package.json fontend/pnpm-lock.yaml fontend/app/components/ForumContent.tsx
git commit -m "feat(forum): ForumContent — markdown+KaTeX sanitizado (anti-XSS) p/ comentários"
```

---

## Task 9: Tipos + hooks React Query

**Files:**
- Modify: `fontend/lib/queryKeys.ts` (chave `forum`)
- Create: `fontend/app/q/hooks/useForum.ts`

**Interfaces:**
- Produces: tipos `Comentario`, `ForumResposta`; hooks `useForum(questaoId, ordenar)`, `useCriarComentario(questaoId)`, `useEditarComentario(questaoId)`, `useExcluirComentario(questaoId)`, `useVotar(questaoId)`; `uploadImagemForum(file)`.
- Consumes: `qk.forum`, `apiJson`, `apiPost`, `apiFetch`, `API_BASE`.

- [ ] **Step 1: Adicionar a chave em `queryKeys.ts`**

Após a linha `favoritas: () => ...`:

```python
# (TS) dentro do objeto qk:
  forum: (questaoId: number | string, ordenar: string) =>
    ["q", "forum", String(questaoId), ordenar] as const,
```

(Em TS, sem o comentário python — adicione a propriedade `forum` ao objeto `qk`.)

- [ ] **Step 2: Criar `useForum.ts`**

```tsx
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson, apiPost, API_BASE, apiUrl } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

export interface Comentario {
  id: number;
  parent_id: number | null;
  origem: "studia" | "tc";
  display_name: string;
  autor_inicial: string;
  texto_md: string | null;
  score: number;
  meu_voto: -1 | 0 | 1;
  criado_em: string | null;
  editado: boolean;
  removido: boolean;
  posso_editar: boolean;
  posso_excluir: boolean;
  respostas: Comentario[];
}

export interface ForumData {
  total: number;
  comentarios: Comentario[];
}

export function useForum(questaoId: number, ordenar: "recentes" | "pontos", enabled = true) {
  return useQuery<ForumData>({
    queryKey: qk.forum(questaoId, ordenar),
    queryFn: () => apiJson(`/api/q/questoes/${questaoId}/forum?ordenar=${ordenar}`),
    enabled,
  });
}

function useInvalidarForum(questaoId: number) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["q", "forum", String(questaoId)] });
}

export function useCriarComentario(questaoId: number) {
  const invalidar = useInvalidarForum(questaoId);
  return useMutation({
    mutationFn: (body: { texto_md: string; parent_id?: number | null }) =>
      apiPost<Comentario>(`/api/q/questoes/${questaoId}/forum`, body),
    onSuccess: invalidar,
  });
}

export function useEditarComentario(questaoId: number) {
  const invalidar = useInvalidarForum(questaoId);
  return useMutation({
    mutationFn: ({ id, texto_md }: { id: number; texto_md: string }) =>
      apiJson<Comentario>(`/api/q/forum/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto_md }),
      }),
    onSuccess: invalidar,
  });
}

export function useExcluirComentario(questaoId: number) {
  const invalidar = useInvalidarForum(questaoId);
  return useMutation({
    mutationFn: (id: number) =>
      apiJson(`/api/q/forum/${id}`, { method: "DELETE" }),
    onSuccess: invalidar,
  });
}

export function useVotar(questaoId: number, ordenar: "recentes" | "pontos") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, valor }: { id: number; valor: -1 | 0 | 1 }) =>
      apiPost<{ score: number; meu_voto: -1 | 0 | 1 }>(`/api/q/forum/${id}/voto`, { valor }),
    // Otimista: atualiza score e meu_voto na árvore imediatamente.
    onMutate: async ({ id, valor }) => {
      const key = qk.forum(questaoId, ordenar);
      await qc.cancelQueries({ queryKey: key });
      const anterior = qc.getQueryData<ForumData>(key);
      if (anterior) {
        const aplica = (c: Comentario): Comentario => {
          if (c.id === id) {
            const delta = valor - c.meu_voto;
            return { ...c, meu_voto: valor, score: c.score + delta };
          }
          return { ...c, respostas: c.respostas.map(aplica) };
        };
        qc.setQueryData<ForumData>(key, {
          ...anterior,
          comentarios: anterior.comentarios.map(aplica),
        });
      }
      return { anterior, key };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.anterior) qc.setQueryData(ctx.key, ctx.anterior);
    },
  });
}

/** Sobe uma imagem e devolve a URL absoluta pronta pra inserir em ![](url). */
export async function uploadImagemForum(file: File): Promise<string> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await apiFetch("/api/q/forum/upload", { method: "POST", body: fd });
  if (!res.ok) throw new Error("falha no upload");
  const { url } = (await res.json()) as { url: string };
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}
```

> Nota: `apiFetch` com `FormData` NÃO seta `Content-Type` (o browser põe o boundary). `withCsrf` em `lib/api.ts` injeta o header CSRF sem tocar no corpo — ok.

- [ ] **Step 3: Verificar lint/types**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos. Se reclamar de `apiUrl` não usado, remova-o do import.

- [ ] **Step 4: Commit**

```bash
git add fontend/lib/queryKeys.ts fontend/app/q/hooks/useForum.ts
git commit -m "feat(forum): hooks React Query (listar/criar/editar/excluir/votar) + upload de imagem"
```

---

## Task 10: `CommentEditor`

**Files:**
- Create: `fontend/app/q/caderno/[id]/components/CommentEditor.tsx`

**Interfaces:**
- Produces: `<CommentEditor onSubmit={(texto)=>Promise} onCancel?={()=>void} submitting={bool} valorInicial?={string} autoFocus?={bool} />`.
- Consumes: `ForumContent`, `uploadImagemForum`.

- [ ] **Step 1: Criar `CommentEditor.tsx`**

```tsx
"use client";

import { useRef, useState } from "react";
import ForumContent from "../../../../components/ForumContent";
import { uploadImagemForum } from "../../../hooks/useForum";

interface CommentEditorProps {
  onSubmit: (texto: string) => Promise<void> | void;
  onCancel?: () => void;
  submitting?: boolean;
  valorInicial?: string;
  autoFocus?: boolean;
  placeholder?: string;
}

export function CommentEditor({
  onSubmit, onCancel, submitting = false, valorInicial = "", autoFocus = false,
  placeholder = "Escreva aqui seu comentário",
}: CommentEditorProps) {
  const [texto, setTexto] = useState(valorInicial);
  const [aba, setAba] = useState<"escrever" | "preview">("escrever");
  const [enviandoImg, setEnviandoImg] = useState(false);
  const ref = useRef<HTMLTextAreaElement | null>(null);

  function envolver(antes: string, depois = antes) {
    const el = ref.current;
    if (!el) return;
    const [a, b] = [el.selectionStart, el.selectionEnd];
    const novo = texto.slice(0, a) + antes + texto.slice(a, b) + depois + texto.slice(b);
    setTexto(novo);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = b + antes.length + depois.length; });
  }

  function inserir(trecho: string) {
    const el = ref.current;
    const pos = el ? el.selectionStart : texto.length;
    setTexto(texto.slice(0, pos) + trecho + texto.slice(pos));
  }

  async function aoEscolherImagem(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setEnviandoImg(true);
    try {
      const url = await uploadImagemForum(file);
      inserir(`\n![imagem](${url})\n`);
    } catch {
      inserir("\n_(falha ao subir imagem)_\n");
    } finally {
      setEnviandoImg(false);
    }
  }

  async function publicar() {
    const t = texto.trim();
    if (!t) return;
    await onSubmit(t);
    setTexto("");
  }

  return (
    <div className="rounded-lg border border-border bg-surface-2/40">
      <div className="flex items-center gap-1 border-b border-border/60 px-2 py-1.5 text-fg-faint">
        <button type="button" onClick={() => setAba("escrever")}
          className={`px-2 py-0.5 rounded text-xs ${aba === "escrever" ? "bg-surface text-fg" : "hover:text-fg"}`}>Escrever</button>
        <button type="button" onClick={() => setAba("preview")}
          className={`px-2 py-0.5 rounded text-xs ${aba === "preview" ? "bg-surface text-fg" : "hover:text-fg"}`}>Pré-visualizar</button>
        <span className="mx-1 h-4 w-px bg-border" />
        <button type="button" title="Negrito" onClick={() => envolver("**")} className="px-1.5 hover:text-fg font-bold">B</button>
        <button type="button" title="Itálico" onClick={() => envolver("_")} className="px-1.5 hover:text-fg italic">I</button>
        <button type="button" title="Lista" onClick={() => inserir("\n- ")} className="px-1.5 hover:text-fg">≡</button>
        <button type="button" title="Fórmula" onClick={() => envolver("$$", "$$")} className="px-1.5 hover:text-fg font-mono">∑</button>
        <label title="Imagem" className="px-1.5 hover:text-fg cursor-pointer">
          {enviandoImg ? "…" : "🖼"}
          <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={aoEscolherImagem} />
        </label>
      </div>

      {aba === "escrever" ? (
        <textarea
          ref={ref}
          value={texto}
          autoFocus={autoFocus}
          onChange={(e) => setTexto(e.target.value)}
          placeholder={placeholder}
          rows={4}
          className="w-full resize-y bg-transparent px-3 py-2 text-sm text-fg outline-none placeholder:text-fg-faint"
        />
      ) : (
        <div className="min-h-[6rem] px-3 py-2">
          {texto.trim() ? <ForumContent content={texto} /> : <span className="text-xs text-fg-faint">Nada para pré-visualizar.</span>}
        </div>
      )}

      <div className="flex items-center gap-2 border-t border-border/60 px-2 py-1.5">
        <button type="button" onClick={publicar} disabled={submitting || !texto.trim()}
          className="rounded bg-primary px-3 py-1 text-xs font-semibold text-black disabled:opacity-50">
          {submitting ? "Publicando…" : "Publicar"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-xs text-fg-faint hover:text-fg">Cancelar</button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verificar lint/types**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
git add "fontend/app/q/caderno/[id]/components/CommentEditor.tsx"
git commit -m "feat(forum): CommentEditor — abas escrever/preview, toolbar e upload de imagem"
```

---

## Task 11: `CommentItem`

**Files:**
- Create: `fontend/app/q/caderno/[id]/components/CommentItem.tsx`

**Interfaces:**
- Produces: `<CommentItem comentario={Comentario} questaoId={number} ordenar={...} podeResponder={bool} />` (recursivo p/ respostas, 1 nível).
- Consumes: `ForumContent`, `CommentEditor`, `useVotar`, `useEditarComentario`, `useExcluirComentario`, `useCriarComentario`.

- [ ] **Step 1: Criar `CommentItem.tsx`**

```tsx
"use client";

import { useState } from "react";
import type { Comentario } from "../../../hooks/useForum";
import {
  useCriarComentario, useEditarComentario, useExcluirComentario, useVotar,
} from "../../../hooks/useForum";
import ForumContent from "../../../../components/ForumContent";
import { CommentEditor } from "./CommentEditor";

function dataRelativa(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" }) +
    " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

interface CommentItemProps {
  comentario: Comentario;
  questaoId: number;
  ordenar: "recentes" | "pontos";
  podeResponder: boolean;
}

export function CommentItem({ comentario: c, questaoId, ordenar, podeResponder }: CommentItemProps) {
  const votar = useVotar(questaoId, ordenar);
  const editar = useEditarComentario(questaoId);
  const excluir = useExcluirComentario(questaoId);
  const responder = useCriarComentario(questaoId);
  const [editando, setEditando] = useState(false);
  const [respondendo, setRespondendo] = useState(false);

  const votarPara = (valor: -1 | 1) => {
    if (votar.isPending) return;
    votar.mutate({ id: c.id, valor: c.meu_voto === valor ? 0 : valor });
  };

  return (
    <div className="flex gap-3 py-3">
      {/* Coluna de voto */}
      <div className="flex w-8 shrink-0 flex-col items-center text-fg-faint">
        <button type="button" aria-label="Votar a favor" disabled={c.removido}
          onClick={() => votarPara(1)}
          className={c.meu_voto === 1 ? "text-primary" : "hover:text-fg"}>▲</button>
        <span className="text-sm font-semibold text-fg">{c.score}</span>
        <button type="button" aria-label="Votar contra" disabled={c.removido}
          onClick={() => votarPara(-1)}
          className={c.meu_voto === -1 ? "text-error" : "hover:text-fg"}>▼</button>
      </div>

      {/* Corpo */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20 text-[10px] font-bold text-primary">
            {c.autor_inicial}
          </span>
          <span className="font-semibold text-fg">{c.display_name}</span>
          <span className="text-fg-faint">{dataRelativa(c.criado_em)}</span>
          {c.editado && <span className="text-fg-faint">(editado)</span>}
        </div>

        <div className="mt-1">
          {c.removido ? (
            <p className="text-sm italic text-fg-faint">[comentário removido]</p>
          ) : editando ? (
            <CommentEditor
              valorInicial={c.texto_md ?? ""}
              submitting={editar.isPending}
              autoFocus
              onSubmit={async (texto) => { await editar.mutateAsync({ id: c.id, texto_md: texto }); setEditando(false); }}
              onCancel={() => setEditando(false)}
            />
          ) : (
            <ForumContent content={c.texto_md ?? ""} />
          )}
        </div>

        {!c.removido && !editando && (
          <div className="mt-1 flex items-center gap-3 text-xs text-fg-faint">
            {podeResponder && c.parent_id === null && (
              <button type="button" onClick={() => setRespondendo((v) => !v)} className="hover:text-fg">Responder</button>
            )}
            {c.posso_editar && <button type="button" onClick={() => setEditando(true)} className="hover:text-fg">Editar</button>}
            {c.posso_excluir && (
              <button type="button" onClick={() => { if (confirm("Excluir este comentário?")) excluir.mutate(c.id); }}
                className="hover:text-error">Excluir</button>
            )}
          </div>
        )}

        {respondendo && (
          <div className="mt-2">
            <CommentEditor
              autoFocus
              submitting={responder.isPending}
              placeholder="Escreva sua resposta"
              onSubmit={async (texto) => { await responder.mutateAsync({ texto_md: texto, parent_id: c.id }); setRespondendo(false); }}
              onCancel={() => setRespondendo(false)}
            />
          </div>
        )}

        {/* Respostas (1 nível) */}
        {c.respostas.length > 0 && (
          <div className="mt-2 space-y-0 border-l-2 border-border/50 pl-3">
            {c.respostas.map((r) => (
              <CommentItem key={r.id} comentario={r} questaoId={questaoId} ordenar={ordenar} podeResponder={false} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verificar lint/types**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
git add "fontend/app/q/caderno/[id]/components/CommentItem.tsx"
git commit -m "feat(forum): CommentItem — voto, responder/editar/excluir e respostas aninhadas"
```

---

## Task 12: `ForumPanel`

**Files:**
- Create: `fontend/app/q/caderno/[id]/components/ForumPanel.tsx`

**Interfaces:**
- Produces: `<ForumPanel questaoId={number} onFechar={()=>void} />`.
- Consumes: `useForum`, `useCriarComentario`, `CommentItem`, `CommentEditor`.

- [ ] **Step 1: Criar `ForumPanel.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useCriarComentario, useForum } from "../../../hooks/useForum";
import { CommentItem } from "./CommentItem";
import { CommentEditor } from "./CommentEditor";

interface ForumPanelProps {
  questaoId: number;
  onFechar: () => void;
}

export function ForumPanel({ questaoId, onFechar }: ForumPanelProps) {
  const [ordenar, setOrdenar] = useState<"recentes" | "pontos">("recentes");
  const { data, isPending, isError } = useForum(questaoId, ordenar);
  const criar = useCriarComentario(questaoId);

  return (
    <section className="border-y border-border bg-surface-2/30">
      <header className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-fg">
          💬 Fórum de discussão
          {data ? <span className="text-fg-faint">({data.total})</span> : null}
        </h3>
        <div className="flex items-center gap-3 text-xs text-fg-faint">
          <span>Ordenar:</span>
          <button type="button" onClick={() => setOrdenar("recentes")}
            className={ordenar === "recentes" ? "font-semibold text-primary" : "hover:text-fg"}>Data</button>
          <button type="button" onClick={() => setOrdenar("pontos")}
            className={ordenar === "pontos" ? "font-semibold text-primary" : "hover:text-fg"}>Pontos</button>
          <button type="button" onClick={onFechar} className="ml-2 rounded bg-error/80 px-2 py-0.5 text-white">✕ Fechar</button>
        </div>
      </header>

      <div className="px-4 py-3">
        <CommentEditor
          submitting={criar.isPending}
          placeholder="Escreva aqui seu comentário"
          onSubmit={(texto) => criar.mutateAsync({ texto_md: texto })}
        />
      </div>

      <div className="divide-y divide-border/50 px-4 pb-4">
        {isPending && <p className="py-4 text-sm text-fg-faint">Carregando…</p>}
        {isError && <p className="py-4 text-sm text-error">Não foi possível carregar o fórum.</p>}
        {data && data.comentarios.length === 0 && (
          <p className="py-4 text-sm text-fg-faint">Seja o primeiro a comentar esta questão.</p>
        )}
        {data?.comentarios.map((c) => (
          <CommentItem key={c.id} comentario={c} questaoId={questaoId} ordenar={ordenar} podeResponder />
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verificar lint/types**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
git add "fontend/app/q/caderno/[id]/components/ForumPanel.tsx"
git commit -m "feat(forum): ForumPanel — painel inline com ordenação, editor e lista"
```

---

## Task 13: Integração na página do caderno

**Files:**
- Modify: `fontend/app/q/caderno/[id]/page.tsx` (import; estado; tipo `Questao`; botão 💬 com badge; hotkey `f`; render do painel)

**Interfaces:**
- Consumes: `ForumPanel`; campo `forum_count` no tipo `Questao`.

- [ ] **Step 1: Importar o painel**

Junto aos imports de componentes (perto de `import QuestionHtml ...`, L13):

```tsx
import { ForumPanel } from "./components/ForumPanel";
```

- [ ] **Step 2: Adicionar `forum_count` ao tipo `Questao`**

Localize a `interface Questao` no arquivo e adicione o campo:

```tsx
  forum_count?: number;
```

- [ ] **Step 3: Adicionar estado do painel**

Junto aos outros `useState` do componente da página (ex.: perto de `const [calculatorOpen, setCalculatorOpen] = useState(false)`):

```tsx
  const [forumAberto, setForumAberto] = useState(false);
```

- [ ] **Step 4: Ligar o botão 💬 com badge**

Substitua a linha do botão Fórum (L595):

```tsx
              <button title="Fórum (F)" className="hover:text-primary">💬</button>
```

por:

```tsx
              <button
                title="Fórum (F)"
                onClick={() => setForumAberto((v) => !v)}
                className={`relative ${forumAberto ? "text-primary" : "hover:text-primary"}`}
              >
                💬
                {(questao.forum_count ?? 0) > 0 && (
                  <span className="absolute -right-1 -top-1 rounded-full bg-primary px-1 text-[10px] font-bold leading-tight text-black">
                    {questao.forum_count}
                  </span>
                )}
              </button>
```

- [ ] **Step 5: Adicionar a hotkey `f`**

No objeto passado ao `useHotkeys` (onde estão `m:` e `j:`, ~L357), adicione:

```tsx
    f: () => { if (!canvasActive) setForumAberto((v) => !v); },
```

- [ ] **Step 6: Renderizar o painel**

Logo após o `</header>` da questão (após L603) e antes da “linha enxuta com código + banca”:

```tsx
          {forumAberto && currentQid != null && (
            <ForumPanel questaoId={currentQid} onFechar={() => setForumAberto(false)} />
          )}
```

> `currentQid` é o id da questão atual já usado na página (ver `useQuery` do `questao` em L179-181). Confirme o nome exato da variável no arquivo; se for `questao.id`, use `questao.id`.

- [ ] **Step 7: Verificar lint/build**

Run: `cd fontend && pnpm lint && pnpm build`
Expected: build sem erros.

- [ ] **Step 8: Smoke manual completo**

Com `./dev.sh` rodando, abra `/q/caderno/<id>`:
1. Clicar 💬 (ou tecla `f`) abre/fecha o painel inline.
2. Publicar um comentário com `**negrito**` e `$$D_h = CV \times TH$$` → renderiza formatado + fórmula KaTeX.
3. Responder a um comentário → aparece aninhado; não há botão "Responder" na resposta.
4. Votar ▲/▼ → score muda na hora (otimista); recarregar mantém.
5. Editar e excluir o próprio → "(editado)" / "[comentário removido]".
6. Upload de imagem pela toolbar → `![imagem](url)` e a imagem aparece no preview/publicado.
7. Badge no 💬 reflete a contagem ao reabrir a questão.

- [ ] **Step 9: Commit**

```bash
git add "fontend/app/q/caderno/[id]/page.tsx"
git commit -m "feat(forum): liga botão 💬 (badge + hotkey f) ao ForumPanel na página do caderno"
```

---

## Task 14: Deploy (workflow obrigatório do projeto)

- [ ] **Step 1: Rodar a suíte de backend inteira**

Run: `./dev.sh test -v`
Expected: tudo verde (incluindo drift de migrations).

- [ ] **Step 2: Push**

```bash
git push
```

- [ ] **Step 3: Deploy em produção**

Run: `./build.sh`
Expected: build + push de imagens + `db_prepare` (aplica a migração do fórum) + `docker stack deploy`. O backend migra o schema no startup.

- [ ] **Step 4: Smoke em produção**

Abrir `https://studia.witdev.com.br/q/caderno/<id>`, abrir o fórum, publicar um comentário de teste e votar. Confirmar persistência.

- [ ] **Step 5: Worktree limpo**

Run: `git status`
Expected: sem pendências.

---

## Self-Review (cobertura do spec)

- Modelo de dados (origem, owner_uid, parent_id, score, edited_at, deleted_at; `comentario_votos`) → Task 1/2. ✅
- Pseudônimo TC estável + só alunos → Task 1 (`pseudonimo`) + Task 3 (`_display_name`; o importador que filtra `autor_tipo="aluno"` é fora de escopo, mas `_display_name` nunca vaza o nome real). ✅
- Renderização sanitizada (anti-XSS) com KaTeX + img só do endpoint → Task 8. ✅
- GET árvore + ordenação + meu_voto + forum_count → Task 3. ✅
- Criar/responder (1 nível) → Task 4. ✅
- Editar/excluir (dono/admin, soft-delete, placeholder) → Task 5. ✅
- Votar (toggle/trocar/remover, sem auto-voto, score = curtidas+votos) → Task 6. ✅
- Upload MinIO + redirect → Task 7. ✅
- UI painel inline + editor + item + hooks RQ + badge + hotkey `f` → Tasks 9-13. ✅
- Deploy (workflow do CLAUDE.md) → Task 14. ✅

Tipos consistentes entre tasks: `Comentario.respostas: Comentario[]`, `meu_voto: -1|0|1`, retorno do voto `{score, meu_voto}` (Task 6 ↔ Task 9). Endpoints idênticos entre backend (Tasks 3-7) e hooks (Task 9). Sem placeholders.
