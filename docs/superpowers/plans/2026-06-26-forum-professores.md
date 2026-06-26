# Fórum dos Professores + Sistema de Roles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um segundo quadro de comentários por questão (fórum dos professores) onde só `professor`/`admin` escrevem, com personas de cientistas nos posts do admin, mais o sistema de roles e a UI de promoção.

**Architecture:** Reutiliza a tabela `questao_comentarios`, os endpoints do fórum (parametrizados por `quadro`) e os componentes React do fórum dos alunos. Adiciona 2 colunas, a dependency `require_professor`, um pool de personas e uma página admin de gestão de roles. Nenhuma tabela/endpoint/componente paralelo é criado.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL (asyncpg); Next.js 16 + React 19 + TypeScript + TanStack Query; pytest/pytest-asyncio.

## Global Constraints

- Valores de role válidos, exatamente: `"user"` (aluno), `"professor"`, `"admin"`. Nada além disso é aceito na escrita.
- `is_professor` = `role in ("professor", "admin")`. `is_admin` permanece `role == "admin"` (não mudar).
- `quadro` ∈ `{"alunos", "professores"}`, default `"alunos"`. Valor inválido → 422.
- Alunos **leem e votam** em ambos os quadros. Só `professor`/`admin` **escrevem** no quadro `professores` (403 caso contrário).
- Persona de cientista **apenas** em posts do **admin** no quadro `professores`; professor real posta com `autor_nome` (nome real). Persona fica **fixa** na linha (gravada em `persona_nome`, nunca re-sorteada em leitura).
- Pool de personas, exatamente estes 15 nomes: `Albert Einstein, Isaac Newton, Niels Bohr, Gottfried Leibniz, J. Robert Oppenheimer, Werner Heisenberg, Ernest Rutherford, Marie Curie, Galileu Galilei, Nikola Tesla, Richard Feynman, Max Planck, Erwin Schrödinger, Paul Dirac, Michael Faraday`.
- `forum_count` (detalhe) filtra `forum_tipo == "alunos"`; `forum_count_professores` filtra `forum_tipo == "professores"`. Ambos só contam `deleted_at IS NULL`.
- Migração Alembic: `down_revision = '6cfa560c5346'` (head atual).
- Atalho de teclado do 🎓 = tecla **`o`** (a tecla `p` já é usada pelo "ir para questão"; o botão 🎓 já tem o hint "(O)").
- Rotas novas (`/admin/usuarios...`) e as do fórum DEVEM ficar **antes** do catch-all `@router.get("/{questao_id}")` em `q_router.py` (linha ~2134). O router tem `prefix="/api/q"`.
- Persona só para admin: o **toggle** de "persona para todo professor" NÃO é implementado (YAGNI).
- Comandos de teste do backend rodam **dentro do container backend** (onde o host `postgres` resolve). Ex.: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/<arquivo> -v`.

---

## Task 1: Roles no backend (`is_professor` + `require_professor`)

**Files:**
- Modify: `backend/auth.py:43-45` (property) e `backend/auth.py:116-122` (nova dependency)
- Test: `backend/tests/test_auth_roles.py` (criar)

**Interfaces:**
- Produces: `CurrentUser.is_professor -> bool`; `require_professor(user) -> CurrentUser` (FastAPI dependency, 401 deslogado, 403 se não prof/admin).

- [ ] **Step 1: Escrever o teste falhando**

Criar `backend/tests/test_auth_roles.py`:

```python
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from auth import CurrentUser, require_professor, get_current_user_opt
from tests.conftest import make_user


def test_is_professor_property():
    assert make_user("u", role="professor").is_professor is True
    assert make_user("u", role="admin").is_professor is True
    assert make_user("u", role="user").is_professor is False
    # admin continua admin; professor NÃO é admin
    assert make_user("u", role="professor").is_admin is False
    assert make_user("u", role="admin").is_admin is True


def _app_com_user(user):
    app = FastAPI()

    @app.get("/protegido")
    async def protegido(u: CurrentUser = Depends(require_professor)):
        return {"id": u.id}

    async def override():
        return user

    app.dependency_overrides[get_current_user_opt] = override
    return app


@pytest.mark.asyncio
async def test_require_professor_status_por_role():
    casos = {None: 401, "user": 403, "professor": 200, "admin": 200}
    for role, esperado in casos.items():
        user = None if role is None else make_user("u", role=role)
        app = _app_com_user(user)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cli:
            r = await cli.get("/protegido")
        assert r.status_code == esperado, f"role={role}"
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_auth_roles.py -v`
Expected: FAIL com `ImportError: cannot import name 'require_professor'`.

- [ ] **Step 3: Implementar**

Em `backend/auth.py`, dentro de `CurrentUser`, logo após `is_admin` (linha 45):

```python
    @property
    def is_professor(self) -> bool:
        # admin é superset de professor (pode tudo que o professor pode)
        return self.role in ("professor", "admin")
```

E após `require_admin` (após a linha 122), adicionar:

```python
async def require_professor(
    user: CurrentUser = Depends(require_user),
) -> CurrentUser:
    """Exige role professor ou admin; 403 caso contrário."""
    if not user.is_professor:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "acesso restrito a professores")
    return user
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_auth_roles.py -v`
Expected: PASS (3 casos de status + property).

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py backend/tests/test_auth_roles.py
git commit -m "feat(auth): role professor (is_professor + require_professor)"
```

---

## Task 2: Pool de personas de cientistas

**Files:**
- Create: `backend/forum_personas.py`
- Test: `backend/tests/test_forum_personas.py`

**Interfaces:**
- Produces: `POOL: list[str]` (15 nomes); `sortear_persona(excluir: set[str] | None = None) -> str`.

- [ ] **Step 1: Escrever o teste falhando**

Criar `backend/tests/test_forum_personas.py`:

```python
from forum_personas import POOL, sortear_persona


def test_pool_tem_15_nomes_unicos():
    assert len(POOL) == 15
    assert len(set(POOL)) == 15
    assert "Albert Einstein" in POOL
    assert "Isaac Newton" in POOL


def test_sortear_retorna_do_pool():
    for _ in range(50):
        assert sortear_persona() in POOL


def test_sortear_respeita_excluir():
    excluir = set(POOL[:14])  # sobra 1
    for _ in range(20):
        assert sortear_persona(excluir) == POOL[14]


def test_sortear_fallback_quando_todos_excluidos():
    # Se todos estão excluídos, ignora a exclusão e ainda retorna do pool.
    assert sortear_persona(set(POOL)) in POOL
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_forum_personas.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'forum_personas'`.

- [ ] **Step 3: Implementar**

Criar `backend/forum_personas.py`:

```python
"""Personas de cientistas famosos para os posts do admin no fórum dos professores.

Quando o admin (dono) escreve no quadro `professores`, sorteamos um nome deste
pool e gravamos em `questao_comentarios.persona_nome` — dando a sensação de
vários professores renomados respondendo. A persona fica fixa naquele comentário.
"""

import random

POOL: list[str] = [
    "Albert Einstein", "Isaac Newton", "Niels Bohr", "Gottfried Leibniz",
    "J. Robert Oppenheimer", "Werner Heisenberg", "Ernest Rutherford",
    "Marie Curie", "Galileu Galilei", "Nikola Tesla", "Richard Feynman",
    "Max Planck", "Erwin Schrödinger", "Paul Dirac", "Michael Faraday",
]


def sortear_persona(excluir: set[str] | None = None) -> str:
    """Sorteia um cientista do pool, evitando os de `excluir` quando possível.

    Se todos estiverem excluídos, ignora a exclusão (fallback) — sempre retorna
    um nome válido do pool.
    """
    disponiveis = [n for n in POOL if not excluir or n not in excluir]
    if not disponiveis:
        disponiveis = POOL
    return random.choice(disponiveis)
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_forum_personas.py -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/forum_personas.py backend/tests/test_forum_personas.py
git commit -m "feat(forum-prof): pool de personas de cientistas + sortear_persona"
```

---

## Task 3: Colunas `forum_tipo`/`persona_nome` + migração

**Files:**
- Modify: `backend/models.py:678` (após `deleted_at` em `QuestaoComentario`)
- Create: `backend/alembic/versions/b8e4f1a2c3d6_forum_professores.py`
- Test: roda a suíte de drift existente (`tests/test_alembic_no_drift.py`)

**Interfaces:**
- Produces: `QuestaoComentario.forum_tipo: str` (default `"alunos"`, index), `QuestaoComentario.persona_nome: str | None`.

- [ ] **Step 1: Adicionar as colunas no modelo**

Em `backend/models.py`, dentro de `QuestaoComentario`, logo após `deleted_at` (linha 678):

```python
    # ─── Fórum dos professores (mesmo quadro de comentários, segregado) ───
    forum_tipo: Mapped[str] = mapped_column(
        String(16), default="alunos", server_default="alunos", index=True
    )  # "alunos" | "professores"
    persona_nome: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 2: Escrever a migração**

Criar `backend/alembic/versions/b8e4f1a2c3d6_forum_professores.py`:

```python
"""forum_professores: forum_tipo + persona_nome em questao_comentarios

Revision ID: b8e4f1a2c3d6
Revises: 6cfa560c5346
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "b8e4f1a2c3d6"
down_revision = "6cfa560c5346"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questao_comentarios",
        sa.Column("forum_tipo", sa.String(16), nullable=False, server_default="alunos"),
    )
    op.create_index(
        "ix_questao_comentarios_forum_tipo", "questao_comentarios", ["forum_tipo"]
    )
    op.add_column(
        "questao_comentarios",
        sa.Column("persona_nome", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_questao_comentarios_forum_tipo", table_name="questao_comentarios")
    op.drop_column("questao_comentarios", "persona_nome")
    op.drop_column("questao_comentarios", "forum_tipo")
```

- [ ] **Step 3: Aplicar a migração no banco de dev**

Run: `./dev.sh migrate`
Expected: aplica `b8e4f1a2c3d6` sem erro; `alembic current` aponta para `b8e4f1a2c3d6`.

- [ ] **Step 4: Rodar o teste de drift e confirmar que passa**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_alembic_no_drift.py -v`
Expected: PASS (modelo e head batem; sem drift novo). Se acusar diferença nas colunas novas, ajuste tipo/`server_default`/nome do índice na migração até bater (o índice default do SQLAlchemy para `index=True` é `ix_questao_comentarios_forum_tipo`).

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/alembic/versions/b8e4f1a2c3d6_forum_professores.py
git commit -m "feat(forum-prof): colunas forum_tipo + persona_nome (migração b8e4f1a2c3d6)"
```

---

## Task 4: GET fórum por `quadro` + display de persona + contagens no detalhe

**Files:**
- Modify: `backend/q_router.py` — `_display_name` (1876-1880), `_serializar_comentario` (1883-1904), `listar_forum` (1907-1962), `detalhe` (2168-2173)
- Test: `backend/tests/test_forum_api.py` (estender)

**Interfaces:**
- Consumes: `forum_tipo`, `persona_nome` (Task 3).
- Produces: `GET /api/q/questoes/{id}/forum?quadro=alunos|professores` filtra por `forum_tipo`; serialização inclui `eh_professor: bool`; `display_name` usa persona; detalhe inclui `forum_count` (alunos) e `forum_count_professores`.

- [ ] **Step 1: Escrever os testes falhando**

Em `backend/tests/test_forum_api.py`, acrescentar ao final:

```python
@pytest.mark.asyncio
async def test_quadros_isolados_e_contagens(client, auth_state, db_session):
    # admin cria 1 questão e posta nos dois quadros
    qid = await _criar_questao(db_session)  # helper já existente no arquivo
    auth_state["user"] = ADMIN_USER

    r_aluno = await client.post(f"/api/q/questoes/{qid}/forum",
                                json={"texto_md": "post de aluno", "quadro": "alunos"})
    assert r_aluno.status_code == 201
    r_prof = await client.post(f"/api/q/questoes/{qid}/forum",
                               json={"texto_md": "post de prof", "quadro": "professores"})
    assert r_prof.status_code == 201
    # admin no quadro professores recebe persona do pool
    from forum_personas import POOL
    assert r_prof.json()["display_name"] in POOL
    assert r_prof.json()["eh_professor"] is True

    # GET de cada quadro só enxerga o seu
    a = (await client.get(f"/api/q/questoes/{qid}/forum?quadro=alunos")).json()
    p = (await client.get(f"/api/q/questoes/{qid}/forum?quadro=professores")).json()
    assert [c["texto_md"] for c in a["comentarios"]] == ["post de aluno"]
    assert [c["texto_md"] for c in p["comentarios"]] == ["post de prof"]

    # detalhe separa as contagens
    det = (await client.get(f"/api/q/{qid}")).json()
    assert det["forum_count"] == 1
    assert det["forum_count_professores"] == 1


@pytest.mark.asyncio
async def test_quadro_invalido_422(client):
    r = await client.get("/api/q/questoes/1/forum?quadro=xpto")
    assert r.status_code == 422
```

> Reutilize os helpers/constantes já presentes em `test_forum_api.py` (`ADMIN_USER`, `_criar_questao` ou equivalente). Se o nome do helper de criação de questão for outro, ajuste a chamada.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_forum_api.py -k "quadro" -v`
Expected: FAIL (POST ainda não aceita `quadro`; detalhe sem `forum_count_professores`; sem `eh_professor`).

- [ ] **Step 3: Implementar — `_display_name` com persona**

Em `backend/q_router.py`, substituir `_display_name` (1876-1880) por:

```python
def _display_name(c: QuestaoComentario) -> str:
    """Persona (admin no quadro professores) > pseudônimo TC > nome real do studIA."""
    if c.persona_nome:
        return c.persona_nome
    if c.origem == "tc":
        return pseudonimo(c.autor_nome or str(c.tc_comentario_id or c.id))
    return c.autor_nome or "Anônimo"
```

- [ ] **Step 4: Implementar — `eh_professor` na serialização**

Em `_serializar_comentario` (1883-1904), adicionar a chave no dict de retorno (após `"origem": c.origem,`):

```python
        "eh_professor": c.forum_tipo == "professores",
```

- [ ] **Step 5: Implementar — filtro de `quadro` no GET**

Em `listar_forum` (1907-1913), trocar a assinatura e o `select` inicial:

```python
@router.get("/questoes/{questao_id}/forum")
async def listar_forum(
    questao_id: int,
    ordenar: str = "recentes",
    quadro: Literal["alunos", "professores"] = "alunos",
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    todos = (
        await db.execute(
            select(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == quadro,
            )
        )
    ).scalars().all()
```

Garantir que `Literal` está importado no topo do arquivo (em `from typing import ...`). Se não estiver, adicionar `Literal` à linha de import de `typing`.

- [ ] **Step 6: Implementar — contagens no detalhe**

Em `detalhe`, no dict de retorno, trocar o bloco `"forum_count": (...)` (2168-2173) por:

```python
        "forum_count": (await db.execute(
            select(func.count()).select_from(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == "alunos",
                QuestaoComentario.deleted_at.is_(None),
            )
        )).scalar_one(),
        "forum_count_professores": (await db.execute(
            select(func.count()).select_from(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == "professores",
                QuestaoComentario.deleted_at.is_(None),
            )
        )).scalar_one(),
```

- [ ] **Step 7: Rodar e confirmar que passa**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_forum_api.py -v`
Expected: PASS (novos testes + os antigos do fórum dos alunos continuam verdes).

- [ ] **Step 8: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_api.py
git commit -m "feat(forum-prof): GET por quadro, display de persona, eh_professor e contagens no detalhe"
```

---

## Task 5: POST fórum — `quadro`, gate de escrita e atribuição de persona

**Files:**
- Modify: `backend/q_router.py` — `CriarComentarioReq` (1871-1873) e `criar_comentario` (2018-2056)
- Test: `backend/tests/test_forum_api.py` (estender)

**Interfaces:**
- Consumes: `require_professor`/`is_professor` (Task 1), `sortear_persona`/`POOL` (Task 2), `forum_tipo`/`persona_nome` (Task 3).
- Produces: `POST /api/q/questoes/{id}/forum` aceita `quadro`; 403 para aluno em `professores`; persona gravada para admin; respostas só dentro do mesmo quadro.

- [ ] **Step 1: Escrever os testes falhando**

Em `backend/tests/test_forum_api.py`, acrescentar:

```python
@pytest.mark.asyncio
async def test_aluno_nao_escreve_no_quadro_professores(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    auth_state["user"] = USER_A  # role "user"
    r = await client.post(f"/api/q/questoes/{qid}/forum",
                          json={"texto_md": "tentativa", "quadro": "professores"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_professor_real_posta_com_nome_real(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    prof = make_user("prof-1", role="professor")
    auth_state["user"] = prof
    r = await client.post(f"/api/q/questoes/{qid}/forum",
                          json={"texto_md": "explicação do prof", "quadro": "professores"})
    assert r.status_code == 201
    # professor real => nome real, sem persona
    assert r.json()["display_name"] == prof.name
    assert r.json()["eh_professor"] is True


@pytest.mark.asyncio
async def test_aluno_le_e_vota_em_post_de_professor(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    auth_state["user"] = ADMIN_USER
    r = await client.post(f"/api/q/questoes/{qid}/forum",
                          json={"texto_md": "resposta expert", "quadro": "professores"})
    cid = r.json()["id"]
    # aluno lê
    auth_state["user"] = USER_A
    lista = (await client.get(f"/api/q/questoes/{qid}/forum?quadro=professores")).json()
    assert lista["total"] == 1
    # aluno vota
    v = await client.post(f"/api/q/forum/{cid}/voto", json={"valor": 1})
    assert v.status_code == 200
    assert v.json()["score"] == 1


@pytest.mark.asyncio
async def test_resposta_nao_cruza_quadro(client, auth_state, db_session):
    qid = await _criar_questao(db_session)
    auth_state["user"] = ADMIN_USER
    raiz_aluno = (await client.post(f"/api/q/questoes/{qid}/forum",
                  json={"texto_md": "raiz aluno", "quadro": "alunos"})).json()["id"]
    # responder no quadro professores apontando p/ raiz do quadro alunos => 400
    r = await client.post(f"/api/q/questoes/{qid}/forum",
            json={"texto_md": "resp", "quadro": "professores", "parent_id": raiz_aluno})
    assert r.status_code == 400
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_forum_api.py -k "quadro_professores or professor_real or aluno_le or cruza" -v`
Expected: FAIL (POST ignora `quadro`/gate/persona).

- [ ] **Step 3: Implementar — request model**

Em `backend/q_router.py`, trocar `CriarComentarioReq` (1871-1873) por:

```python
class CriarComentarioReq(BaseModel):
    texto_md: str = Field(..., min_length=1, max_length=MAX_COMENTARIO_CHARS)
    parent_id: int | None = None
    quadro: Literal["alunos", "professores"] = "alunos"
```

- [ ] **Step 4: Implementar — gate, quadro do pai e persona**

Substituir `criar_comentario` (2018-2056) por:

```python
@router.post("/questoes/{questao_id}/forum", status_code=status.HTTP_201_CREATED)
async def criar_comentario(
    questao_id: int,
    req: CriarComentarioReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Gate de escrita: só professor/admin escrevem no quadro dos professores.
    if req.quadro == "professores" and not user.is_professor:
        raise HTTPException(403, "apenas professores podem escrever no fórum dos professores")

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
        if pai is None or pai.questao_id != questao_id or pai.forum_tipo != req.quadro:
            raise HTTPException(400, "comentário pai inválido")
        if pai.deleted_at is not None:
            raise HTTPException(400, "não é possível responder a um comentário removido")
        if pai.parent_id is not None:
            raise HTTPException(400, "respostas só podem ser feitas a um comentário raiz")

    # Persona: só o admin no quadro professores ganha nome de cientista.
    persona = None
    if req.quadro == "professores" and user.is_admin:
        usadas = set((await db.execute(
            select(QuestaoComentario.persona_nome).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == "professores",
                QuestaoComentario.parent_id.is_(None),
                QuestaoComentario.persona_nome.is_not(None),
            )
        )).scalars().all())
        persona = sortear_persona(usadas)

    c = QuestaoComentario(
        questao_id=questao_id,
        origem="studia",
        owner_uid=user.id,
        autor_nome=user.name,
        autor_tipo="professor" if req.quadro == "professores" else None,
        forum_tipo=req.quadro,
        persona_nome=persona,
        parent_id=req.parent_id,
        texto_md=texto,
        score=0,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _serializar_comentario(c, meu_voto=0, user=user, respostas=[])
```

Adicionar o import no topo do arquivo (junto aos demais imports locais): `from forum_personas import sortear_persona`.

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_forum_api.py -v`
Expected: PASS (toda a suíte do fórum).

- [ ] **Step 6: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_api.py
git commit -m "feat(forum-prof): POST com quadro, gate de escrita prof/admin e persona do admin"
```

---

## Task 6: Endpoints admin de usuários (listar + trocar role)

**Files:**
- Modify: `backend/q_router.py` (adicionar 2 rotas ANTES do catch-all `@router.get("/{questao_id}")`, ~linha 2134)
- Test: `backend/tests/test_admin_usuarios.py` (criar)

**Interfaces:**
- Produces: `GET /api/q/admin/usuarios?q=&page=` (require_admin) e `PATCH /api/q/admin/usuarios/{uid}/role` (require_admin, body `{role}`).

- [ ] **Step 1: Escrever os testes falhando**

Criar `backend/tests/test_admin_usuarios.py`:

```python
import pytest
from sqlalchemy import text

from tests.conftest import ADMIN_USER, USER_A


async def _semear_usuario(db, uid, email, name, role="user"):
    await db.execute(text(
        'INSERT INTO "user" (id, email, name, role, banned, "createdAt", "updatedAt", "emailVerified") '
        "VALUES (:id, :email, :name, :role, false, now(), now(), true)"
    ), {"id": uid, "email": email, "name": name, "role": role})
    await db.flush()


@pytest.mark.asyncio
async def test_listar_usuarios_admin(client, auth_state, db_session):
    await _semear_usuario(db_session, "alvo-1", "alvo@studia.test", "Aluno Alvo")
    auth_state["user"] = ADMIN_USER
    r = await client.get("/api/q/admin/usuarios?q=alvo")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()["usuarios"]]
    assert "alvo@studia.test" in emails


@pytest.mark.asyncio
async def test_listar_usuarios_nao_admin_403(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.get("/api/q/admin/usuarios")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_role_promove_professor(client, auth_state, db_session):
    await _semear_usuario(db_session, "alvo-2", "p@studia.test", "Promover")
    auth_state["user"] = ADMIN_USER
    r = await client.patch("/api/q/admin/usuarios/alvo-2/role", json={"role": "professor"})
    assert r.status_code == 200
    assert r.json()["role"] == "professor"
    row = (await db_session.execute(
        text('SELECT role FROM "user" WHERE id = :id'), {"id": "alvo-2"}
    )).scalar_one()
    assert row == "professor"


@pytest.mark.asyncio
async def test_patch_role_invalido_422(client, auth_state, db_session):
    await _semear_usuario(db_session, "alvo-3", "x@studia.test", "X")
    auth_state["user"] = ADMIN_USER
    r = await client.patch("/api/q/admin/usuarios/alvo-3/role", json={"role": "rei"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_nao_rebaixa_a_si_mesmo_400(client, auth_state, db_session):
    await _semear_usuario(db_session, ADMIN_USER.id, "admin@studia.test", "Admin", role="admin")
    auth_state["user"] = ADMIN_USER
    r = await client.patch(f"/api/q/admin/usuarios/{ADMIN_USER.id}/role", json={"role": "user"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_role_uid_inexistente_404(client, auth_state):
    auth_state["user"] = ADMIN_USER
    r = await client.patch("/api/q/admin/usuarios/nao-existe/role", json={"role": "user"})
    assert r.status_code == 404
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_admin_usuarios.py -v`
Expected: FAIL (rotas inexistentes → 404 em tudo, inclusive nos casos que esperam 200/403/422/400).

- [ ] **Step 3: Implementar as rotas**

Em `backend/q_router.py`, **imediatamente antes** de `@router.get("/{questao_id}")` (linha 2134), inserir:

```python
# ─── Admin: gestão de roles de usuários ───────────────────────────────────
_ROLES_VALIDOS = ("user", "professor", "admin")


class PatchRoleReq(BaseModel):
    role: Literal["user", "professor", "admin"]


@router.get("/admin/usuarios")
async def admin_listar_usuarios(
    q: str = "",
    page: int = 1,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    page = max(1, page)
    por_pagina = 30
    termo = f"%{q.strip()}%"
    rows = (await db.execute(
        text(
            'SELECT id, email, name, COALESCE(role, \'user\') AS role, '
            'COALESCE(banned, false) AS banned, "createdAt" '
            'FROM "user" '
            "WHERE (:q = '' OR email ILIKE :termo OR name ILIKE :termo) "
            'ORDER BY "createdAt" DESC '
            "LIMIT :lim OFFSET :off"
        ),
        {"q": q.strip(), "termo": termo, "lim": por_pagina + 1, "off": (page - 1) * por_pagina},
    )).mappings().all()
    tem_mais = len(rows) > por_pagina
    usuarios = [
        {
            "id": r["id"], "email": r["email"], "name": r["name"],
            "role": r["role"], "banned": bool(r["banned"]),
            "created_at": r["createdAt"].isoformat() if r["createdAt"] else None,
        }
        for r in rows[:por_pagina]
    ]
    return {"usuarios": usuarios, "page": page, "tem_mais": tem_mais}


@router.patch("/admin/usuarios/{uid}/role")
async def admin_trocar_role(
    uid: str,
    req: PatchRoleReq,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if uid == admin.id:
        raise HTTPException(400, "você não pode alterar o seu próprio papel")
    existe = (await db.execute(
        text('SELECT 1 FROM "user" WHERE id = :id'), {"id": uid}
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(404, "usuário não encontrado")
    await db.execute(
        text('UPDATE "user" SET role = :role, "updatedAt" = now() WHERE id = :id'),
        {"role": req.role, "id": uid},
    )
    await db.commit()
    return {"id": uid, "role": req.role}
```

> O role inválido é barrado pelo `Literal` do Pydantic → 422 automático. `_ROLES_VALIDOS` fica documentando o conjunto (pode ser usado em logs/futuro).

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_admin_usuarios.py -v`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_admin_usuarios.py
git commit -m "feat(admin): listar usuários e trocar role (user/professor/admin)"
```

---

## Task 7: Frontend — query keys + hooks `useForum` com `quadro`

**Files:**
- Modify: `fontend/lib/queryKeys.ts:28-29` e adicionar `adminUsuarios`
- Modify: `fontend/app/q/hooks/useForum.ts` (todos os hooks recebem `quadro`)

**Interfaces:**
- Produces: `qk.forum(questaoId, quadro, ordenar)`, `qk.adminUsuarios(q, page)`; hooks `useForum/useCriarComentario/useEditarComentario/useExcluirComentario/useVotar` com parâmetro `quadro: "alunos" | "professores"`; `Comentario.eh_professor: boolean`.

- [ ] **Step 1: Atualizar `queryKeys.ts`**

Em `fontend/lib/queryKeys.ts`, trocar a entrada `forum` (28-29) e adicionar `adminUsuarios`:

```ts
  forum: (questaoId: number | string, quadro: string, ordenar: string) =>
    ["q", "forum", String(questaoId), quadro, ordenar] as const,
  adminUsuarios: (q: string, page: number) =>
    ["admin", "usuarios", q, page] as const,
```

- [ ] **Step 2: Atualizar `useForum.ts`**

Reescrever `fontend/app/q/hooks/useForum.ts` para propagar `quadro`:

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson, apiPost, API_BASE } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

export type Quadro = "alunos" | "professores";

export interface Comentario {
  id: number;
  parent_id: number | null;
  origem: "studia" | "tc";
  eh_professor: boolean;
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

export function useForum(
  questaoId: number, quadro: Quadro, ordenar: "recentes" | "pontos", enabled = true,
) {
  return useQuery<ForumData>({
    queryKey: qk.forum(questaoId, quadro, ordenar),
    queryFn: () => apiJson(`/api/q/questoes/${questaoId}/forum?quadro=${quadro}&ordenar=${ordenar}`),
    enabled,
  });
}

function useInvalidarForum(questaoId: number, quadro: Quadro) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["q", "forum", String(questaoId), quadro] });
}

export function useCriarComentario(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
  return useMutation({
    mutationFn: (body: { texto_md: string; parent_id?: number | null }) =>
      apiPost<Comentario>(`/api/q/questoes/${questaoId}/forum`, { ...body, quadro }),
    onSuccess: invalidar,
  });
}

export function useEditarComentario(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
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

export function useExcluirComentario(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
  return useMutation({
    mutationFn: (id: number) => apiJson(`/api/q/forum/${id}`, { method: "DELETE" }),
    onSuccess: invalidar,
  });
}

export function useVotar(questaoId: number, quadro: Quadro, ordenar: "recentes" | "pontos") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, valor }: { id: number; valor: -1 | 0 | 1 }) =>
      apiPost<{ score: number; meu_voto: -1 | 0 | 1 }>(`/api/q/forum/${id}/voto`, { valor }),
    onMutate: async ({ id, valor }) => {
      const key = qk.forum(questaoId, quadro, ordenar);
      await qc.cancelQueries({ queryKey: ["q", "forum", String(questaoId), quadro] });
      const anterior = qc.getQueryData<ForumData>(key);
      if (anterior) {
        const aplica = (c: Comentario): Comentario => {
          if (c.id === id) {
            const delta = valor - c.meu_voto;
            return { ...c, meu_voto: valor, score: c.score + delta };
          }
          return { ...c, respostas: c.respostas.map(aplica) };
        };
        qc.setQueryData<ForumData>(key, { ...anterior, comentarios: anterior.comentarios.map(aplica) });
      }
      return { anterior, key };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.anterior) qc.setQueryData(ctx.key, ctx.anterior);
    },
    onSuccess: (data, { id }) => {
      const key = qk.forum(questaoId, quadro, ordenar);
      const atual = qc.getQueryData<ForumData>(key);
      if (!atual) return;
      const aplica = (c: Comentario): Comentario =>
        c.id === id
          ? { ...c, score: data.score, meu_voto: data.meu_voto }
          : { ...c, respostas: c.respostas.map(aplica) };
      qc.setQueryData<ForumData>(key, { ...atual, comentarios: atual.comentarios.map(aplica) });
    },
  });
}

export async function uploadImagemForum(file: File): Promise<string> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await apiFetch("/api/q/forum/upload", { method: "POST", body: fd });
  if (!res.ok) throw new Error("falha no upload");
  const { url } = (await res.json()) as { url: string };
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}
```

- [ ] **Step 3: Type-check + lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos (haverá erros de tipo nos componentes que ainda chamam os hooks sem `quadro` — serão corrigidos na Task 8; se o lint falhar só por isso, prossiga e valide o lint completo ao fim da Task 8).

- [ ] **Step 4: Commit**

```bash
git add fontend/lib/queryKeys.ts fontend/app/q/hooks/useForum.ts
git commit -m "feat(forum-prof): hooks e query keys do fórum parametrizados por quadro"
```

---

## Task 8: Frontend — `ForumPanel` e `CommentItem` com `quadro`/`podeEscrever`/badge

**Files:**
- Modify: `fontend/app/q/caderno/[id]/components/ForumPanel.tsx`
- Modify: `fontend/app/q/caderno/[id]/components/CommentItem.tsx`

**Interfaces:**
- Consumes: hooks com `quadro` (Task 7), `Comentario.eh_professor`.
- Produces: `ForumPanel` com props `{ questaoId, quadro, podeEscrever, onFechar }`; `CommentItem` com prop `quadro`; badge 🎓 quando `eh_professor`.

- [ ] **Step 1: Reescrever `ForumPanel.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useCriarComentario, useForum, type Quadro } from "../../../hooks/useForum";
import { CommentItem } from "./CommentItem";
import { CommentEditor } from "./CommentEditor";

interface ForumPanelProps {
  questaoId: number;
  quadro: Quadro;
  podeEscrever: boolean;
  onFechar: () => void;
}

export function ForumPanel({ questaoId, quadro, podeEscrever, onFechar }: ForumPanelProps) {
  const [ordenar, setOrdenar] = useState<"recentes" | "pontos">("recentes");
  const { data, isPending, isError } = useForum(questaoId, quadro, ordenar);
  const criar = useCriarComentario(questaoId, quadro);

  const ehProf = quadro === "professores";
  const titulo = ehProf ? "🎓 Fórum dos professores" : "💬 Fórum de discussão";

  return (
    <section className="border-y border-border bg-surface-2/30">
      <header className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-fg">
          {titulo}
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

      {podeEscrever ? (
        <div className="px-4 py-3">
          <CommentEditor
            submitting={criar.isPending}
            placeholder={ehProf ? "Escreva a explicação do professor" : "Escreva aqui seu comentário"}
            onSubmit={async (texto) => { await criar.mutateAsync({ texto_md: texto }); }}
          />
        </div>
      ) : ehProf ? (
        <p className="px-4 py-3 text-xs text-fg-faint">
          Somente professores podem escrever aqui. Você pode ler e votar nas explicações.
        </p>
      ) : null}

      <div className="divide-y divide-border/50 px-4 pb-4">
        {isPending && <p className="py-4 text-sm text-fg-faint">Carregando…</p>}
        {isError && <p className="py-4 text-sm text-error">Não foi possível carregar o fórum.</p>}
        {data && data.comentarios.length === 0 && (
          <p className="py-4 text-sm text-fg-faint">
            {ehProf ? "Nenhuma explicação de professor ainda." : "Seja o primeiro a comentar esta questão."}
          </p>
        )}
        {data?.comentarios.map((c) => (
          <CommentItem key={c.id} comentario={c} questaoId={questaoId} quadro={quadro}
            ordenar={ordenar} podeResponder={podeEscrever} />
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Atualizar `CommentItem.tsx`**

Trocar a interface e a assinatura (18-25) para receber `quadro`, repassar aos hooks, ao recursar, e renderizar o badge:

```tsx
import type { Comentario, Quadro } from "../../../hooks/useForum";
```

```tsx
interface CommentItemProps {
  comentario: Comentario;
  questaoId: number;
  quadro: Quadro;
  ordenar: "recentes" | "pontos";
  podeResponder: boolean;
}

export function CommentItem({ comentario: c, questaoId, quadro, ordenar, podeResponder }: CommentItemProps) {
  const votar = useVotar(questaoId, quadro, ordenar);
  const editar = useEditarComentario(questaoId, quadro);
  const excluir = useExcluirComentario(questaoId, quadro);
  const responder = useCriarComentario(questaoId, quadro);
```

No cabeçalho do comentário (após `<span className="font-semibold text-fg">{c.display_name}</span>`, linha 57), inserir o badge:

```tsx
          {c.eh_professor && (
            <span className="rounded bg-secondary/20 px-1.5 py-0.5 text-[10px] font-semibold text-secondary">🎓 Professor</span>
          )}
```

Na recursão das respostas (107), repassar `quadro`:

```tsx
              <CommentItem key={r.id} comentario={r} questaoId={questaoId} quadro={quadro}
                ordenar={ordenar} podeResponder={false} />
```

- [ ] **Step 3: Lint + type-check completo**

Run: `cd fontend && pnpm lint`
Expected: PASS (o `ForumPanel` na `page.tsx` ainda passa props antigas — será corrigido na Task 9; se o lint quebrar só por causa de `page.tsx`, prossiga e revalide ao fim da Task 9).

- [ ] **Step 4: Commit**

```bash
git add fontend/app/q/caderno/\[id\]/components/ForumPanel.tsx fontend/app/q/caderno/\[id\]/components/CommentItem.tsx
git commit -m "feat(forum-prof): ForumPanel/CommentItem com quadro, podeEscrever e badge Professor"
```

---

## Task 9: Frontend — botão 🎓 na página da questão

**Files:**
- Modify: `fontend/app/q/caderno/[id]/page.tsx` (interface `Questao`, estado, botões 🎓/💬, hotkey `o`, render do painel)

**Interfaces:**
- Consumes: `ForumPanel` com `{ quadro, podeEscrever }` (Task 8), `forum_count_professores` do detalhe (Task 4).
- Produces: 🎓 abre o fórum dos professores; 💬 e 🎓 mutuamente exclusivos; `podeEscrever` calculado pelo role da sessão.

- [ ] **Step 1: Detectar o role da sessão**

No topo do componente da página (junto aos outros hooks `use*`), adicionar:

```tsx
  const { data: sessao } = useSession();
  const meuRole = (sessao?.user as { role?: string } | undefined)?.role ?? "user";
  const souProfOuAdmin = meuRole === "professor" || meuRole === "admin";
```

Garantir o import no topo do arquivo:

```tsx
import { useSession } from "@/lib/auth-client";
```

- [ ] **Step 2: Campo no tipo `Questao` + estado do painel**

Na interface `Questao` (linha 27+), após `forum_count?: number;`:

```tsx
  forum_count_professores?: number;
```

Junto ao estado `forumAberto` (linha 92), adicionar:

```tsx
  const [forumProfAberto, setForumProfAberto] = useState(false);
```

- [ ] **Step 3: Hotkey `o` (professores) + exclusão mútua**

No mapa do `useHotkeys` (linha 354-370), ajustar `f` e adicionar `o`:

```tsx
    f: () => { if (!canvasActive) { setForumAberto((v) => !v); setForumProfAberto(false); } },
    o: () => { if (!canvasActive) { setForumProfAberto((v) => !v); setForumAberto(false); } },
```

- [ ] **Step 4: Botões 🎓 e 💬**

Trocar o botão 🎓 placeholder (linha 597) e ajustar o 💬 (599-610) para se fecharem mutuamente:

```tsx
              <button
                title="Fórum dos professores (O)"
                onClick={() => { setForumProfAberto((v) => !v); setForumAberto(false); }}
                className={`relative ${forumProfAberto ? "text-primary" : "hover:text-primary"}`}
              >
                🎓
                {(questao.forum_count_professores ?? 0) > 0 && (
                  <span className="absolute -right-1 -top-1 rounded-full bg-secondary px-1 text-[10px] font-bold leading-tight text-black">
                    {questao.forum_count_professores}
                  </span>
                )}
              </button>
              <button title="Teoria" className="hover:text-primary">📕</button>
              <button
                title="Fórum (F)"
                onClick={() => { setForumAberto((v) => !v); setForumProfAberto(false); }}
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

- [ ] **Step 5: Render dos dois painéis**

Trocar o bloco de render do painel (620-622) por:

```tsx
          {forumAberto && currentQid != null && (
            <ForumPanel questaoId={currentQid} quadro="alunos" podeEscrever onFechar={() => setForumAberto(false)} />
          )}
          {forumProfAberto && currentQid != null && (
            <ForumPanel questaoId={currentQid} quadro="professores" podeEscrever={souProfOuAdmin}
              onFechar={() => setForumProfAberto(false)} />
          )}
```

- [ ] **Step 6: Lint + type-check**

Run: `cd fontend && pnpm lint`
Expected: PASS (sem erros de tipo; todos os chamadores de `ForumPanel`/hooks agora passam `quadro`).

- [ ] **Step 7: Commit**

```bash
git add fontend/app/q/caderno/\[id\]/page.tsx
git commit -m "feat(forum-prof): botão 🎓 abre o fórum dos professores (atalho O), exclusão mútua com 💬"
```

---

## Task 10: Frontend — página admin de usuários + opção professor no CreateUserCard

**Files:**
- Create: `fontend/app/q/admin/usuarios/page.tsx`
- Modify: `fontend/app/conta/ContaClient.tsx` (CreateUserCard: opção `professor` + link p/ a página)

**Interfaces:**
- Consumes: `GET /api/q/admin/usuarios`, `PATCH /api/q/admin/usuarios/{uid}/role`, `qk.adminUsuarios` (Tasks 6-7).
- Produces: tela `/q/admin/usuarios` (admin-only) com busca e troca de role; opção `professor` no card de criar usuário.

- [ ] **Step 1: Criar a página `/q/admin/usuarios`**

Criar `fontend/app/q/admin/usuarios/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/lib/auth-client";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

interface UsuarioAdmin {
  id: string;
  email: string;
  name: string;
  role: "user" | "professor" | "admin";
  banned: boolean;
  created_at: string | null;
}
interface ListaUsuarios {
  usuarios: UsuarioAdmin[];
  page: number;
  tem_mais: boolean;
}

const ROLES: UsuarioAdmin["role"][] = ["user", "professor", "admin"];

export default function AdminUsuariosPage() {
  const router = useRouter();
  const { data: sessao, isPending: carregandoSessao } = useSession();
  const isAdmin = (sessao?.user as { role?: string } | undefined)?.role === "admin";

  const [busca, setBusca] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const qc = useQueryClient();

  // Redireciona não-admin assim que a sessão resolve.
  useEffect(() => {
    if (!carregandoSessao && !isAdmin) router.replace("/q");
  }, [carregandoSessao, isAdmin, router]);

  // Debounce simples da busca.
  useEffect(() => {
    const t = setTimeout(() => { setQ(busca); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [busca]);

  const { data, isPending } = useQuery<ListaUsuarios>({
    queryKey: qk.adminUsuarios(q, page),
    queryFn: () => apiJson(`/api/q/admin/usuarios?q=${encodeURIComponent(q)}&page=${page}`),
    enabled: isAdmin,
  });

  const trocarRole = useMutation({
    mutationFn: ({ uid, role }: { uid: string; role: string }) =>
      apiJson(`/api/q/admin/usuarios/${uid}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "usuarios"] }),
  });

  if (carregandoSessao || !isAdmin) {
    return <div className="p-8 text-fg-muted">Carregando…</div>;
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold text-fg-strong">Usuários e papéis</h1>
      <input
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
        placeholder="Buscar por nome ou e-mail…"
        className="mb-4 w-full rounded-lg border border-border-dark bg-bg-dark px-3 py-2 text-sm text-fg-strong outline-none focus:border-primary"
      />

      {trocarRole.isError && (
        <p className="mb-3 text-sm text-error">
          {(trocarRole.error as Error)?.message || "Erro ao trocar papel."}
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-fg-faint">
            <tr>
              <th className="px-3 py-2">Nome</th>
              <th className="px-3 py-2">E-mail</th>
              <th className="px-3 py-2">Papel</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {isPending && (
              <tr><td colSpan={3} className="px-3 py-4 text-fg-faint">Carregando…</td></tr>
            )}
            {data?.usuarios.map((u) => (
              <tr key={u.id}>
                <td className="px-3 py-2 text-fg">{u.name}</td>
                <td className="px-3 py-2 text-fg-faint">{u.email}</td>
                <td className="px-3 py-2">
                  <select
                    value={u.role}
                    disabled={trocarRole.isPending}
                    onChange={(e) => trocarRole.mutate({ uid: u.id, role: e.target.value })}
                    className="rounded border border-border-dark bg-bg-dark px-2 py-1 text-fg-strong outline-none focus:border-primary"
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
              </tr>
            ))}
            {data && data.usuarios.length === 0 && (
              <tr><td colSpan={3} className="px-3 py-4 text-fg-faint">Nenhum usuário encontrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm text-fg-faint">
        <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="rounded border border-border px-3 py-1 disabled:opacity-40">← Anterior</button>
        <span>Página {data?.page ?? page}</span>
        <button type="button" disabled={!data?.tem_mais} onClick={() => setPage((p) => p + 1)}
          className="rounded border border-border px-3 py-1 disabled:opacity-40">Próxima →</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Opção `professor` + link no CreateUserCard**

Em `fontend/app/conta/ContaClient.tsx`:

- Trocar o cast do role na chamada (linha 177) para incluir professor:

```tsx
    const { error } = await authClient.admin.createUser({ name, email, password, role: role as "user" | "professor" | "admin" });
```

- Acrescentar a opção no `<select>` (entre as linhas 203-205):

```tsx
            <option value="user">user</option>
            <option value="professor">professor</option>
            <option value="admin">admin</option>
```

- Adicionar um link para a página de gestão, logo após o `</form>` do card (antes de fechar `</SectionCard>`, linha 209-210):

```tsx
        <a href="/q/admin/usuarios" className="mt-3 block text-sm text-primary hover:underline">
          Gerenciar usuários e papéis →
        </a>
```

- [ ] **Step 3: Lint + type-check**

Run: `cd fontend && pnpm lint`
Expected: PASS.

- [ ] **Step 4: Verificação manual (smoke)**

Run: `./dev.sh up:d` (se ainda não estiver no ar) e abrir `http://localhost:3000/q/admin/usuarios` logado como admin.
Expected: tabela lista usuários; trocar o papel de um aluno para `professor` persiste (recarregar mantém). Não-admin é redirecionado para `/q`.

- [ ] **Step 5: Commit**

```bash
git add fontend/app/q/admin/usuarios/page.tsx fontend/app/conta/ContaClient.tsx
git commit -m "feat(admin): página de gestão de usuários/papéis + opção professor no criar usuário"
```

---

## Self-Review (preenchido)

**Spec coverage:**
- §1 Roles → Task 1. §2 Promoção (backend+frontend) → Tasks 6, 10. §3 Modelo → Task 3. §4 Personas → Tasks 2, 5. §5 Endpoints (GET/POST/detalhe) → Tasks 4, 5. §6 Frontend (panel/itens/página/keys) → Tasks 7, 8, 9. §7 Testes → distribuídos (Tasks 1, 2, 4, 5, 6). Sem lacunas.
- PATCH/DELETE/voto/upload reutilizados sem mudança (cobertos pelos testes existentes + Task 5 valida voto de aluno em post de professor).

**Placeholder scan:** sem TBD/TODO; todo passo com código tem o código completo.

**Type consistency:** `qk.forum(questaoId, quadro, ordenar)` usado igual em `useForum.ts` (Task 7), `ForumPanel`/`CommentItem` (Task 8). `Comentario.eh_professor` definido na Task 7 e consumido na Task 8. `quadro: "alunos"|"professores"` consistente backend (`Literal`) e frontend (`Quadro`). `forum_count_professores` produzido na Task 4 e consumido na Task 9. Hotkey `o` (não `p`).

**Observação de execução:** ao fim das 10 tasks, seguir o Workflow OBRIGATÓRIO do CLAUDE.md (commit já feito por task → push `origin/main` → `./build.sh` → worktree limpo). A migração `b8e4f1a2c3d6` é aplicada automaticamente no startup do backend em produção (`db_prepare`).
