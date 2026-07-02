# Perfil Completo de Usuário — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expandir `/conta` para perfil completo (apelido único do fórum, avatar, visibilidade, pontuação derivada) + rota pública `/u/[apelido]`.

**Architecture:** Nova tabela `perfis_usuario` no backend FastAPI (Alembic); pontuação 100% derivada (`SUM(score)` do fórum + metas/combos derivados de `resolucoes` por dia local); router novo `/api/q/perfil`; fórum passa a exibir apelido/avatar; frontend Next.js com React Query v5.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + Pillow (novo) + MinIO; Next.js 16 + React 19 + TanStack Query v5 + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-07-02-perfil-completo-design.md`

## Global Constraints

- Trabalho no worktree `/home/wital/studia/.claude/worktrees/perfil-completo` (branch `worktree-perfil-completo`). NUNCA tocar o checkout principal.
- Toda UI em Português BR. **Proibido** escrever "TC"/"tec" em texto visível de UI.
- Frontend: React Query v5 obrigatório (nunca `fetch` cru em `useEffect`); todo load assíncrono reserva espaço com `<Skeleton>` (`fontend/app/components/ds/Skeleton.tsx`) — dados não podem "pular" na tela.
- **Nunca** expor `owner_uid`, e-mail ou nome real do usuário em endpoint público ou no serializer do fórum.
- Apelido: lowercase, regex `^[a-z0-9][a-z0-9-]{2,31}$` (3–32 chars), único; erros: 409 (em uso), 422 (formato).
- Pontuação: fórum = `SUM(score)` (origem `studia`, `deleted_at IS NULL`); estudo = metas×10 + X2×20 + X3×30 + X4×40; marcos por dia local America/Fortaleza com questões DISTINTAS: ≥15 meta, ≥25 X2, ≥35 X3, ≥45 X4 (cumulativos no mesmo dia).
- **Comando de teste backend** (o container monta só `./backend` do checkout principal, então o worktree entra por volume override; stack dev precisa estar de pé — `./dev.sh up:d` a partir de `/home/wital/studia` se não estiver):

```bash
cd /home/wital/studia && docker compose -f docker-compose.dev.yml run --rm -T \
  -v /home/wital/studia/.claude/worktrees/perfil-completo/backend:/app \
  backend python -m pytest tests/<ARQUIVO> -v
```

  (abrevio como `PYTEST tests/<ARQUIVO>` nos passos.)
- Lint frontend: `cd /home/wital/studia/.claude/worktrees/perfil-completo/fontend && pnpm install && pnpm lint`.
- Commits pequenos por tarefa, mensagens em pt-BR `tipo(escopo): descrição`, rodapé `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Modelo `PerfilUsuario` + migration Alembic + dependência Pillow

**Files:**
- Modify: `backend/models.py` (fim do arquivo, após `QuestaoTcImport`)
- Create: `backend/alembic/versions/e7f8a9b0c1d2_perfis_usuario.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_perfil_models.py`

**Interfaces:**
- Produces: classe `models.PerfilUsuario` (tabela `perfis_usuario`) com campos `id: int`, `owner_uid: str` (unique), `apelido: Optional[str]` (unique), `avatar_key: Optional[str]`, `perfil_publico: bool`, `mostrar_estatisticas: bool`, `mostrar_foto: bool`, `created_at`, `updated_at`. Head do Alembic passa a ser `e7f8a9b0c1d2`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_perfil_models.py`:

```python
"""PerfilUsuario: criação, defaults e unicidade de owner_uid/apelido."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models import PerfilUsuario

pytestmark = pytest.mark.asyncio


async def test_cria_perfil_com_defaults(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A"))
    await db_session.commit()
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.apelido is None
    assert p.avatar_key is None
    assert p.perfil_publico is True
    assert p.mostrar_estatisticas is True
    assert p.mostrar_foto is True


async def test_apelido_unico(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A", apelido="rochedo-16"))
    await db_session.commit()
    db_session.add(PerfilUsuario(owner_uid="user-B", apelido="rochedo-16"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_owner_uid_unico(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A"))
    await db_session.commit()
    db_session.add(PerfilUsuario(owner_uid="user-A"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST tests/test_perfil_models.py`
Expected: FAIL — `ImportError: cannot import name 'PerfilUsuario'`

- [ ] **Step 3: Adicionar o modelo ao fim de `backend/models.py`**

(imports `Boolean, DateTime, Integer, String, func, Mapped, mapped_column, Optional, datetime` já existem no arquivo)

```python
class PerfilUsuario(Base):
    """Perfil público do usuário (apelido do fórum, avatar, visibilidade).

    Linha criada lazy no primeiro PATCH/upload do usuário; ausência de linha
    equivale a todos os defaults. `owner_uid` = Better Auth "user".id.
    """

    __tablename__ = "perfis_usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    apelido: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, unique=True, index=True
    )
    # Objeto MinIO "avatars/{uuid}.webp" — uuid aleatório por upload (nunca o
    # uid, que não pode vazar em URL); re-upload gera chave nova = cache-busting.
    avatar_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    perfil_publico: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    mostrar_estatisticas: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    mostrar_foto: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Criar a migration `backend/alembic/versions/e7f8a9b0c1d2_perfis_usuario.py`**

(head atual da cadeia é `a7c8d9e0f1b2`, após o merge da main de 2026-07-02)

```python
"""perfis_usuario (apelido do fórum, avatar e visibilidade do perfil)"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "a7c8d9e0f1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "perfis_usuario",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_uid", sa.String(length=64), nullable=False),
        sa.Column("apelido", sa.String(length=32), nullable=True),
        sa.Column("avatar_key", sa.String(length=128), nullable=True),
        sa.Column("perfil_publico", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("mostrar_estatisticas", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("mostrar_foto", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_perfis_usuario_owner_uid", "perfis_usuario", ["owner_uid"], unique=True
    )
    op.create_index(
        "ix_perfis_usuario_apelido", "perfis_usuario", ["apelido"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_perfis_usuario_apelido", table_name="perfis_usuario")
    op.drop_index("ix_perfis_usuario_owner_uid", table_name="perfis_usuario")
    op.drop_table("perfis_usuario")
```

- [ ] **Step 5: Adicionar Pillow ao `backend/requirements.txt`** (após o bloco do openpyxl)

```
# avatar do perfil: crop/resize da foto
Pillow>=10.0.0
```

- [ ] **Step 6: Rodar os testes do modelo + drift de migrations**

Run: `PYTEST tests/test_perfil_models.py tests/test_alembic_no_drift.py`
Expected: PASS (o teste de drift valida que a migration casa com o modelo; se falhar, ajustar a migration até casar)

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/alembic/versions/e7f8a9b0c1d2_perfis_usuario.py backend/requirements.txt backend/tests/test_perfil_models.py
git commit -m "feat(perfil): tabela perfis_usuario (apelido, avatar, visibilidade) + Pillow"
```

---

### Task 2: `perfil_service.py` — pontuação derivada

**Files:**
- Create: `backend/perfil_service.py`
- Test: `backend/tests/test_perfil_service.py`

**Interfaces:**
- Consumes: `models.PerfilUsuario`, `models.QuestaoComentario`, `models.Resolucao`, `entitlements.META_DIARIA_PRO`, `entitlements.COMBOS_META_DIARIA`.
- Produces (usados nas Tasks 3–6):
  - `APELIDO_RE: re.Pattern`
  - `contar_marcos(contagens_por_dia: list[int]) -> dict` → `{"metas", "combos_x2", "combos_x3", "combos_x4"}`
  - `pontos_estudo(marcos: dict) -> int`
  - `async pontos_forum(db, uid: str) -> dict` → `{"pontos": int, "comentarios": int}`
  - `async resumo_perfil(db, uid: str) -> dict` → `{"pontuacao": {"total","forum","estudo","metas","combos_x2","combos_x3","combos_x4","comentarios"}, "resolvidas", "acertos", "taxa", "streak_dias"}`
  - `async perfis_forum_por_uids(db, uids: set[str]) -> dict[str, dict]` → `{uid: {"apelido": str, "avatar_url": str|None}}` (só perfis públicos com apelido; `avatar_url` só se `mostrar_foto` e `avatar_key`)

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/test_perfil_service.py`:

```python
"""perfil_service: derivação de pontuação (fórum + metas/combos de resolucoes)."""

from datetime import datetime, timedelta

import pytest

import perfil_service
from models import PerfilUsuario, Questao, QuestaoComentario, Resolucao

pytestmark = pytest.mark.asyncio


def test_contar_marcos_marcos_cumulativos():
    # dia 30 → meta+X2; dia 45 → meta+X2+X3+X4; dia 14 → nada
    marcos = perfil_service.contar_marcos([30, 45, 14])
    assert marcos == {"metas": 2, "combos_x2": 2, "combos_x3": 1, "combos_x4": 1}


def test_pontos_estudo():
    marcos = {"metas": 2, "combos_x2": 2, "combos_x3": 1, "combos_x4": 1}
    # 2*10 + 2*20 + 1*30 + 1*40 = 130
    assert perfil_service.pontos_estudo(marcos) == 130


async def _seed_questoes(db_session, base: int, n: int) -> list[int]:
    ids = list(range(base, base + n))
    for qid in ids:
        db_session.add(Questao(id=qid, id_externo=qid, tipo="MULTIPLA_ESCOLHA",
                               enunciado_html="<p>Q</p>", gabarito="A", status="ATIVA"))
    await db_session.commit()
    return ids


async def _seed_dia(db_session, uid: str, qids: list[int], dia_utc: datetime, acertos: int):
    """Uma resolução por questão no timestamp dado (meio-dia local, longe do corte)."""
    for i, qid in enumerate(qids):
        db_session.add(Resolucao(questao_id=qid, usuario_uid=uid,
                                 resposta="A", acertou=(i < acertos), created_at=dia_utc))
    await db_session.commit()


async def test_pontos_forum_ignora_tc_e_deletados(db_session):
    qids = await _seed_questoes(db_session, 9000, 1)
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="studia",
                                     owner_uid="user-A", texto_md="a", score=5))
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="studia",
                                     owner_uid="user-A", texto_md="b", score=-2))
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="studia", owner_uid="user-A",
                                     texto_md="c", score=100, deleted_at=datetime.utcnow()))
    db_session.add(QuestaoComentario(questao_id=qids[0], origem="tc",
                                     autor_nome="Fulano", texto_md="d", score=50))
    await db_session.commit()
    forum = await perfil_service.pontos_forum(db_session, "user-A")
    assert forum == {"pontos": 3, "comentarios": 2}


async def test_resumo_perfil_deriva_metas_e_combos(db_session):
    # 15:00 UTC = 12:00 America/Fortaleza — bem longe do corte de meia-noite.
    hoje = datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)
    ontem, anteontem = hoje - timedelta(days=1), hoje - timedelta(days=2)
    qids = await _seed_questoes(db_session, 10000, 45)
    await _seed_dia(db_session, "user-A", qids[:30], anteontem, acertos=20)  # meta + X2
    await _seed_dia(db_session, "user-A", qids[:45], ontem, acertos=40)      # meta + X2+X3+X4
    await _seed_dia(db_session, "user-A", qids[:14], hoje, acertos=10)       # nada
    resumo = await perfil_service.resumo_perfil(db_session, "user-A")
    p = resumo["pontuacao"]
    assert p["metas"] == 2 and p["combos_x2"] == 2
    assert p["combos_x3"] == 1 and p["combos_x4"] == 1
    assert p["estudo"] == 130
    assert p["forum"] == 0
    assert p["total"] == 130
    assert resumo["resolvidas"] == 30 + 45 + 14
    assert resumo["streak_dias"] == 3  # anteontem, ontem e hoje


async def test_resumo_repeticao_no_dia_nao_infla(db_session):
    """Repetir a MESMA questão várias vezes no dia conta 1 questão distinta."""
    hoje = datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)
    qids = await _seed_questoes(db_session, 11000, 1)
    for _ in range(20):
        db_session.add(Resolucao(questao_id=qids[0], usuario_uid="user-B",
                                 resposta="A", acertou=True, created_at=hoje))
    await db_session.commit()
    resumo = await perfil_service.resumo_perfil(db_session, "user-B")
    assert resumo["pontuacao"]["metas"] == 0
    assert resumo["pontuacao"]["estudo"] == 0


async def test_perfis_forum_por_uids_respeita_privacidade(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A", apelido="rochedo-16",
                                 avatar_key="avatars/x.webp", mostrar_foto=False))
    db_session.add(PerfilUsuario(owner_uid="user-B", apelido="oculto", perfil_publico=False))
    db_session.add(PerfilUsuario(owner_uid="user-C"))  # sem apelido
    await db_session.commit()
    perfis = await perfil_service.perfis_forum_por_uids(
        db_session, {"user-A", "user-B", "user-C", "user-Z"})
    assert set(perfis) == {"user-A"}
    assert perfis["user-A"]["apelido"] == "rochedo-16"
    assert perfis["user-A"]["avatar_url"] is None  # mostrar_foto=False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST tests/test_perfil_service.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'perfil_service'`

- [ ] **Step 3: Criar `backend/perfil_service.py`**

```python
"""Perfil de usuário: pontuação DERIVADA (nada persistido) e perfis p/ o fórum.

- Fórum: SUM(score) dos comentários do usuário (origem studia, não deletados).
- Estudo: `resolucoes` agrupada por dia local (America/Fortaleza, mesmo corte
  do entitlements) contando questões DISTINTAS por dia; ≥15 bate meta,
  ≥25/35/45 rendem combos X2/X3/X4 — cumulativos no mesmo dia, espelhando os
  marcos ao vivo de COMBOS_META_DIARIA.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from entitlements import COMBOS_META_DIARIA, META_DIARIA_PRO
from models import PerfilUsuario, QuestaoComentario, Resolucao

APELIDO_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")

PONTOS_META = 10
PONTOS_COMBO = {2: 20, 3: 30, 4: 40}

_TZ_APP = ZoneInfo("America/Fortaleza")
_UTC = ZoneInfo("UTC")


def _dia_local(dt: datetime) -> date:
    """created_at é UTC-naive → dia calendário no fuso do app."""
    return dt.replace(tzinfo=_UTC).astimezone(_TZ_APP).date()


def contar_marcos(contagens_por_dia: list[int]) -> dict[str, int]:
    """Metas e combos a partir das contagens de questões distintas por dia."""
    por_nivel = {nivel: marco for marco, nivel in COMBOS_META_DIARIA.items()}
    return {
        "metas": sum(1 for n in contagens_por_dia if n >= META_DIARIA_PRO),
        "combos_x2": sum(1 for n in contagens_por_dia if n >= por_nivel[2]),
        "combos_x3": sum(1 for n in contagens_por_dia if n >= por_nivel[3]),
        "combos_x4": sum(1 for n in contagens_por_dia if n >= por_nivel[4]),
    }


def pontos_estudo(marcos: dict[str, int]) -> int:
    return (
        marcos["metas"] * PONTOS_META
        + marcos["combos_x2"] * PONTOS_COMBO[2]
        + marcos["combos_x3"] * PONTOS_COMBO[3]
        + marcos["combos_x4"] * PONTOS_COMBO[4]
    )


def _streak(dias: set[date], hoje: date) -> int:
    # Mesma regra do _compute_streak do dashboard (tolerância de 1 dia),
    # reimplementada aqui: q_router importa este módulo, não o contrário.
    if not dias:
        return 0
    if hoje in dias:
        cursor = hoje
    elif hoje - timedelta(days=1) in dias:
        cursor = hoje - timedelta(days=1)
    else:
        return 0
    streak = 0
    while cursor in dias:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def pontos_forum(db: AsyncSession, uid: str) -> dict:
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(QuestaoComentario.score), 0),
                func.count(QuestaoComentario.id),
            ).where(
                QuestaoComentario.owner_uid == uid,
                QuestaoComentario.origem == "studia",
                QuestaoComentario.deleted_at.is_(None),
            )
        )
    ).one()
    return {"pontos": int(row[0] or 0), "comentarios": int(row[1] or 0)}


async def _contagens_diarias(db: AsyncSession, uid: str) -> dict[date, int]:
    """{dia local: nº de questões DISTINTAS} — agregação em Python porque o
    deslocamento de fuso em SQL não é portável e o volume por usuário é pequeno."""
    rows = (
        await db.execute(
            select(Resolucao.questao_id, Resolucao.created_at).where(
                Resolucao.usuario_uid == uid
            )
        )
    ).all()
    por_dia: dict[date, set[int]] = {}
    for questao_id, created_at in rows:
        if created_at is None:
            continue
        por_dia.setdefault(_dia_local(created_at), set()).add(questao_id)
    return {d: len(qs) for d, qs in por_dia.items()}


async def resumo_perfil(db: AsyncSession, uid: str) -> dict:
    forum = await pontos_forum(db, uid)
    por_dia = await _contagens_diarias(db, uid)
    marcos = contar_marcos(list(por_dia.values()))
    estudo = pontos_estudo(marcos)

    dono = (Resolucao.usuario_uid == uid,)
    total = (await db.execute(select(func.count()).where(*dono))).scalar_one()
    acertos = (
        await db.execute(select(func.count()).where(*dono, Resolucao.acertou == True))  # noqa: E712
    ).scalar_one()

    return {
        "pontuacao": {
            "total": forum["pontos"] + estudo,
            "forum": forum["pontos"],
            "estudo": estudo,
            **marcos,
            "comentarios": forum["comentarios"],
        },
        "resolvidas": int(total),
        "acertos": int(acertos),
        "taxa": round((acertos / total) * 100, 1) if total else 0,
        "streak_dias": _streak(set(por_dia.keys()), datetime.now(_TZ_APP).date()),
    }


async def perfis_forum_por_uids(db: AsyncSession, uids: set[str]) -> dict[str, dict]:
    """{uid: {"apelido", "avatar_url"}} só para perfis PÚBLICOS com apelido."""
    uids = {u for u in uids if u}
    if not uids:
        return {}
    rows = (
        await db.execute(
            select(PerfilUsuario).where(
                PerfilUsuario.owner_uid.in_(uids),
                PerfilUsuario.perfil_publico == True,  # noqa: E712
                PerfilUsuario.apelido.is_not(None),
            )
        )
    ).scalars().all()
    return {
        p.owner_uid: {
            "apelido": p.apelido,
            "avatar_url": (
                f"/api/q/perfil/avatar/{p.avatar_key}"
                if (p.avatar_key and p.mostrar_foto)
                else None
            ),
        }
        for p in rows
    }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `PYTEST tests/test_perfil_service.py`
Expected: PASS (7 testes)

- [ ] **Step 5: Commit**

```bash
git add backend/perfil_service.py backend/tests/test_perfil_service.py
git commit -m "feat(perfil): perfil_service com pontuação derivada (fórum + metas/combos)"
```

---

### Task 3: Router `/api/q/perfil` — GET (meu perfil) e PATCH (apelido + toggles)

**Files:**
- Create: `backend/perfil_router.py`
- Modify: `backend/main.py` (registrar o router ANTES do `q_router`)
- Test: `backend/tests/test_perfil_api.py`

**Interfaces:**
- Consumes: `perfil_service.resumo_perfil`, `perfil_service.APELIDO_RE`, `models.PerfilUsuario`, `auth.require_user`, `database.get_db`.
- Produces:
  - `GET /api/q/perfil` → `{"apelido", "avatar_url", "perfil_publico", "mostrar_estatisticas", "mostrar_foto", "resumo": <resumo_perfil>}`
  - `PATCH /api/q/perfil` body `{apelido?, perfil_publico?, mostrar_estatisticas?, mostrar_foto?}` → `{"ok": true, "apelido"}`; 409 apelido em uso, 422 formato.
  - Helpers internos reutilizados nas Tasks 4–5: `_get_perfil(db, uid)`, `_get_or_create_perfil(db, uid)`, `_avatar_url(p)`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/test_perfil_api.py`:

```python
"""GET/PATCH /api/q/perfil: criação lazy, apelido (formato/unicidade) e toggles."""

import pytest
from sqlalchemy import select

from conftest import USER_A, USER_B
from models import PerfilUsuario

pytestmark = pytest.mark.asyncio


async def test_get_perfil_sem_linha_retorna_defaults(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.get("/api/q/perfil")
    assert r.status_code == 200
    body = r.json()
    assert body["apelido"] is None
    assert body["avatar_url"] is None
    assert body["perfil_publico"] is True
    assert body["mostrar_estatisticas"] is True
    assert body["mostrar_foto"] is True
    assert body["resumo"]["pontuacao"]["total"] == 0
    assert body["resumo"]["resolvidas"] == 0


async def test_patch_cria_linha_lazy_e_salva_apelido(client, db_session, auth_state):
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={"apelido": "  Rochedo-16 "})
    assert r.status_code == 200
    assert r.json()["apelido"] == "rochedo-16"  # normalizado (trim + lower)
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.apelido == "rochedo-16"


async def test_patch_apelido_invalido_422(client, auth_state):
    auth_state["user"] = USER_A
    for ruim in ["ab", "-comeca-com-hifen", "tem espaço", "açúcar", "x" * 33]:
        r = await client.patch("/api/q/perfil", json={"apelido": ruim})
        assert r.status_code == 422, f"apelido {ruim!r} deveria dar 422"


async def test_patch_apelido_em_uso_409(client, db_session, auth_state):
    db_session.add(PerfilUsuario(owner_uid="user-B", apelido="rochedo-16"))
    await db_session.commit()
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={"apelido": "rochedo-16"})
    assert r.status_code == 409


async def test_patch_apelido_vazio_limpa(client, db_session, auth_state):
    db_session.add(PerfilUsuario(owner_uid="user-A", apelido="rochedo-16"))
    await db_session.commit()
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={"apelido": ""})
    assert r.status_code == 200
    assert r.json()["apelido"] is None


async def test_patch_toggles(client, auth_state):
    auth_state["user"] = USER_A
    r = await client.patch("/api/q/perfil", json={
        "perfil_publico": False, "mostrar_estatisticas": False, "mostrar_foto": False,
    })
    assert r.status_code == 200
    body = (await client.get("/api/q/perfil")).json()
    assert body["perfil_publico"] is False
    assert body["mostrar_estatisticas"] is False
    assert body["mostrar_foto"] is False


async def test_patch_parcial_nao_toca_outros_campos(client, auth_state):
    auth_state["user"] = USER_A
    await client.patch("/api/q/perfil", json={"apelido": "rochedo-16"})
    await client.patch("/api/q/perfil", json={"perfil_publico": False})
    body = (await client.get("/api/q/perfil")).json()
    assert body["apelido"] == "rochedo-16"  # PATCH parcial preservou


async def test_perfil_exige_login(client, auth_state):
    auth_state["user"] = None
    assert (await client.get("/api/q/perfil")).status_code == 401
    assert (await client.patch("/api/q/perfil", json={})).status_code == 401
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST tests/test_perfil_api.py`
Expected: FAIL — 404 em todas as chamadas (router não existe)

- [ ] **Step 3: Criar `backend/perfil_router.py`**

```python
"""Perfil de usuário: /api/q/perfil (próprio), avatar e perfil público /u/{apelido}."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import perfil_service
from auth import CurrentUser, require_user
from database import get_db
from models import PerfilUsuario

router = APIRouter(prefix="/api/q/perfil", tags=["perfil"])


def _avatar_url(p: Optional[PerfilUsuario]) -> Optional[str]:
    if p is not None and p.avatar_key:
        return f"/api/q/perfil/avatar/{p.avatar_key}"
    return None


async def _get_perfil(db: AsyncSession, uid: str) -> Optional[PerfilUsuario]:
    return (
        await db.execute(select(PerfilUsuario).where(PerfilUsuario.owner_uid == uid))
    ).scalars().first()


async def _get_or_create_perfil(db: AsyncSession, uid: str) -> PerfilUsuario:
    p = await _get_perfil(db, uid)
    if p is None:
        p = PerfilUsuario(owner_uid=uid)
        db.add(p)
        await db.flush()
    return p


@router.get("")
async def meu_perfil(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    p = await _get_perfil(db, user.id)
    return {
        "apelido": p.apelido if p else None,
        "avatar_url": _avatar_url(p),
        "perfil_publico": p.perfil_publico if p else True,
        "mostrar_estatisticas": p.mostrar_estatisticas if p else True,
        "mostrar_foto": p.mostrar_foto if p else True,
        "resumo": await perfil_service.resumo_perfil(db, user.id),
    }


class PatchPerfilReq(BaseModel):
    apelido: Optional[str] = None
    perfil_publico: Optional[bool] = None
    mostrar_estatisticas: Optional[bool] = None
    mostrar_foto: Optional[bool] = None


@router.patch("")
async def atualizar_perfil(
    req: PatchPerfilReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    p = await _get_or_create_perfil(db, user.id)
    if "apelido" in req.model_fields_set:
        apelido = (req.apelido or "").strip().lower() or None
        if apelido is not None and not perfil_service.APELIDO_RE.match(apelido):
            raise HTTPException(
                422,
                "apelido inválido: 3 a 32 caracteres, só letras minúsculas, "
                "números e hífens (não pode começar com hífen)",
            )
        p.apelido = apelido
    for campo in ("perfil_publico", "mostrar_estatisticas", "mostrar_foto"):
        valor = getattr(req, campo)
        if campo in req.model_fields_set and valor is not None:
            setattr(p, campo, valor)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "este apelido já está em uso")
    return {"ok": True, "apelido": p.apelido}
```

- [ ] **Step 4: Registrar em `backend/main.py`** — junto dos outros includes, **antes** do `q_router` (o q_router tem rotas `/{questao_id}/...` sob o mesmo prefixo `/api/q`; registrar o perfil primeiro elimina qualquer risco de colisão de match):

```python
from perfil_router import router as perfil_router

app.include_router(perfil_router)  # ANTES de app.include_router(q_router)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `PYTEST tests/test_perfil_api.py`
Expected: PASS (8 testes)

- [ ] **Step 6: Commit**

```bash
git add backend/perfil_router.py backend/main.py backend/tests/test_perfil_api.py
git commit -m "feat(perfil): endpoints GET/PATCH /api/q/perfil (apelido + visibilidade)"
```

---

### Task 4: Avatar — upload (Pillow), remoção e servir por stream

**Files:**
- Modify: `backend/minio_client.py` (novo helper `remove_object`)
- Modify: `backend/perfil_router.py`
- Test: `backend/tests/test_perfil_avatar.py`

**Interfaces:**
- Consumes: `minio_client.upload_bytes`, `minio_client.download_bytes` (existentes), helpers da Task 3.
- Produces:
  - `minio_client.remove_object(object_name: str) -> None`
  - `POST /api/q/perfil/avatar` (multipart `file`) → `{"avatar_url": "/api/q/perfil/avatar/avatars/<uuid>.webp"}`; 415 tipo, 413 tamanho, 422 imagem corrompida.
  - `DELETE /api/q/perfil/avatar` → `{"ok": true}`
  - `GET /api/q/perfil/avatar/{key:path}` (público) → bytes webp, cache immutable; 404 se key inválida/ausente.

- [ ] **Step 1: Adicionar `remove_object` ao fim de `backend/minio_client.py`**

```python
def remove_object(object_name: str) -> None:
    """Remove um objeto do bucket (no-op silencioso fica a cargo do chamador)."""
    client = get_minio_client()
    client.remove_object(BUCKET_NAME, object_name)
```

- [ ] **Step 2: Escrever os testes que falham**

`backend/tests/test_perfil_avatar.py` — MinIO é mockado via monkeypatch no namespace do `perfil_router` (mesma técnica dos testes de upload do fórum):

```python
"""Avatar do perfil: upload (validação + Pillow 256x256 webp), remoção e serving."""

import io

import pytest
from PIL import Image
from sqlalchemy import select

from conftest import USER_A
from models import PerfilUsuario

pytestmark = pytest.mark.asyncio


@pytest.fixture
def minio_fake(monkeypatch):
    """Armazenamento em memória no lugar do MinIO."""
    store: dict[str, bytes] = {}

    def fake_upload(key, data, content_type):
        store[key] = data
        return f"studia-pdfs/{key}"

    def fake_download(key):
        return store[key]  # KeyError vira 404 no endpoint

    def fake_remove(key):
        store.pop(key, None)

    import perfil_router
    monkeypatch.setattr(perfil_router, "upload_bytes", fake_upload)
    monkeypatch.setattr(perfil_router, "download_bytes", fake_download)
    monkeypatch.setattr(perfil_router, "remove_object", fake_remove)
    return store


def _png(largura=800, altura=600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), "#06b6d4").save(buf, format="PNG")
    return buf.getvalue()


async def test_upload_processa_e_salva_webp_256(client, db_session, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("foto.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url.startswith("/api/q/perfil/avatar/avatars/") and url.endswith(".webp")
    key = url.removeprefix("/api/q/perfil/avatar/")
    img = Image.open(io.BytesIO(minio_fake[key]))
    assert img.format == "WEBP"
    assert img.size == (256, 256)  # crop central quadrado
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.avatar_key == key


async def test_reupload_remove_objeto_antigo(client, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r1 = await client.post("/api/q/perfil/avatar",
                           files={"file": ("a.png", _png(), "image/png")})
    key1 = r1.json()["avatar_url"].removeprefix("/api/q/perfil/avatar/")
    r2 = await client.post("/api/q/perfil/avatar",
                           files={"file": ("b.png", _png(), "image/png")})
    key2 = r2.json()["avatar_url"].removeprefix("/api/q/perfil/avatar/")
    assert key1 != key2  # chave nova = cache-busting
    assert key1 not in minio_fake and key2 in minio_fake


async def test_upload_valida_tipo_tamanho_e_conteudo(client, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("f.gif", b"GIF89a", "image/gif")})
    assert r.status_code == 415
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("f.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")})
    assert r.status_code == 413
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("f.png", b"nao-e-imagem", "image/png")})
    assert r.status_code == 422


async def test_delete_avatar(client, db_session, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("a.png", _png(), "image/png")})
    key = r.json()["avatar_url"].removeprefix("/api/q/perfil/avatar/")
    r = await client.delete("/api/q/perfil/avatar")
    assert r.status_code == 200
    assert key not in minio_fake
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.avatar_key is None


async def test_serve_avatar_publico_e_404s(client, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("a.png", _png(), "image/png")})
    url = r.json()["avatar_url"]
    auth_state["user"] = None  # endpoint de serving é público
    ok = await client.get(url)
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/webp"
    assert "immutable" in ok.headers["cache-control"]
    assert (await client.get("/api/q/perfil/avatar/avatars/../segredo.webp")).status_code == 404
    assert (await client.get(
        "/api/q/perfil/avatar/avatars/00000000-0000-0000-0000-000000000000.webp"
    )).status_code == 404
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `PYTEST tests/test_perfil_avatar.py`
Expected: FAIL — 404/405 (rotas de avatar não existem)

- [ ] **Step 4: Implementar em `backend/perfil_router.py`**

Novos imports no topo do arquivo:

```python
import io
import re as _re
import uuid as _uuid

from fastapi import File, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from minio_client import download_bytes, remove_object, upload_bytes
```

Constantes e endpoints (após o `atualizar_perfil`):

```python
_AVATAR_TIPOS = {"image/png", "image/jpeg", "image/webp"}
_AVATAR_MAX = 5 * 1024 * 1024  # 5 MB
_AVATAR_LADO = 256
_AVATAR_KEY_RE = _re.compile(r"^avatars/[0-9a-f-]{36}\.webp$")


def _processar_avatar(data: bytes) -> bytes:
    """Crop central quadrado + resize 256x256 → webp (roda em threadpool)."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = ImageOps.fit(img.convert("RGB"), (_AVATAR_LADO, _AVATAR_LADO))
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)
    return out.getvalue()


@router.post("/avatar")
async def subir_avatar(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if (file.content_type or "").lower() not in _AVATAR_TIPOS:
        raise HTTPException(415, "tipo de imagem não suportado (use png, jpg ou webp)")
    data = await file.read()
    if len(data) > _AVATAR_MAX:
        raise HTTPException(413, "imagem acima de 5 MB")
    try:
        webp = await run_in_threadpool(_processar_avatar, data)
    except Exception as exc:
        raise HTTPException(422, "imagem inválida") from exc

    p = await _get_or_create_perfil(db, user.id)
    key_antiga = p.avatar_key
    key = f"avatars/{_uuid.uuid4()}.webp"
    await run_in_threadpool(upload_bytes, key, webp, "image/webp")
    p.avatar_key = key
    await db.commit()
    if key_antiga:
        try:
            await run_in_threadpool(remove_object, key_antiga)
        except Exception:
            pass  # objeto órfão é aceitável; nunca falhar o upload por isso
    return {"avatar_url": f"/api/q/perfil/avatar/{key}"}


@router.delete("/avatar")
async def remover_avatar(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    p = await _get_or_create_perfil(db, user.id)
    key = p.avatar_key
    p.avatar_key = None
    await db.commit()
    if key:
        try:
            await run_in_threadpool(remove_object, key)
        except Exception:
            pass
    return {"ok": True}


@router.get("/avatar/{key:path}")
async def servir_avatar(key: str) -> Response:
    """Serve o avatar PELO backend (stream do MinIO) — mesmo racional das
    imagens do fórum: o host minio:9000 só resolve na rede dos containers.
    Key é uuid aleatório por upload → cache immutable é seguro."""
    if not _AVATAR_KEY_RE.match(key):
        raise HTTPException(404, "avatar não encontrado")
    try:
        data = await run_in_threadpool(download_bytes, key)
    except Exception as exc:
        raise HTTPException(404, "avatar não encontrado") from exc
    return Response(
        content=data,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
```

- [ ] **Step 5: Rodar e ver passar**

Run: `PYTEST tests/test_perfil_avatar.py`
Expected: PASS (5 testes)

- [ ] **Step 6: Commit**

```bash
git add backend/minio_client.py backend/perfil_router.py backend/tests/test_perfil_avatar.py
git commit -m "feat(perfil): avatar com Pillow 256x256 webp no MinIO (upload/remoção/serving)"
```

---

### Task 5: Perfil público `GET /api/q/perfil/u/{apelido}`

**Files:**
- Modify: `backend/perfil_router.py`
- Test: `backend/tests/test_perfil_publico.py`

**Interfaces:**
- Consumes: `perfil_service.resumo_perfil`, helpers das Tasks 3–4; tabela Better Auth `"user"` via SQL cru (`createdAt`, `role`).
- Produces: `GET /api/q/perfil/u/{apelido}` (público, sem auth) →

```json
{
  "apelido": "rochedo-16",
  "avatar_url": "... ou null",
  "membro_desde": "2026-01-15T...",
  "badge": "professor | admin | null",
  "pontuacao": {"total": 133, "forum": 3, "comentarios": 2},
  "estatisticas": {
    "resolvidas": 89, "acertos": 60, "taxa": 67.4, "streak_dias": 3,
    "estudo": 130, "metas": 2, "combos_x2": 2, "combos_x3": 1, "combos_x4": 1
  }
}
```

  `estatisticas` = `null` quando `mostrar_estatisticas=false` (o breakdown de estudo é estatística; `pontuacao.total` continua incluindo os pontos de estudo). 404 apelido inexistente; 404 com `detail={"privado": true}` quando `perfil_publico=false`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/test_perfil_publico.py`:

```python
"""Perfil público /api/q/perfil/u/{apelido}: toggles e vazamento zero de identidade."""

import json
from datetime import datetime

import pytest
from sqlalchemy import text

from models import PerfilUsuario, Questao, QuestaoComentario

pytestmark = pytest.mark.asyncio


async def _seed_user_better_auth(db_session, uid: str, role: str | None = None):
    await db_session.execute(text(
        'INSERT INTO "user" (id, name, email, role) '
        "VALUES (:id, :name, :email, :role) ON CONFLICT (id) DO NOTHING"
    ), {"id": uid, "name": f"Nome Real {uid}", "email": f"{uid}@x.com", "role": role})
    await db_session.commit()


async def _seed_perfil(db_session, uid: str, apelido: str, **kw):
    await _seed_user_better_auth(db_session, uid, kw.pop("role", None))
    db_session.add(PerfilUsuario(owner_uid=uid, apelido=apelido, **kw))
    await db_session.commit()


async def test_perfil_publico_basico(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-A", "rochedo-16", role="professor")
    db_session.add(Questao(id=9100, id_externo=9100, tipo="MULTIPLA_ESCOLHA",
                           enunciado_html="<p>Q</p>", gabarito="A", status="ATIVA"))
    await db_session.commit()
    db_session.add(QuestaoComentario(questao_id=9100, origem="studia",
                                     owner_uid="user-A", texto_md="oi", score=7))
    await db_session.commit()

    auth_state["user"] = None  # endpoint é público, sem login
    r = await client.get("/api/q/perfil/u/rochedo-16")
    assert r.status_code == 200
    body = r.json()
    assert body["apelido"] == "rochedo-16"
    assert body["badge"] == "professor"
    assert body["membro_desde"] is not None
    assert body["pontuacao"]["forum"] == 7
    assert body["pontuacao"]["comentarios"] == 1
    assert body["estatisticas"] is not None
    # identidade real NUNCA vaza
    dump = json.dumps(body)
    assert "user-A" not in dump and "Nome Real" not in dump and "@x.com" not in dump


async def test_apelido_inexistente_404(client, auth_state):
    auth_state["user"] = None
    assert (await client.get("/api/q/perfil/u/nao-existe")).status_code == 404


async def test_perfil_privado_404_com_flag(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-B", "oculto", perfil_publico=False)
    auth_state["user"] = None
    r = await client.get("/api/q/perfil/u/oculto")
    assert r.status_code == 404
    assert r.json()["detail"] == {"privado": True}


async def test_toggles_de_foto_e_estatisticas(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-C", "reservado",
                       avatar_key="avatars/11111111-1111-1111-1111-111111111111.webp",
                       mostrar_foto=False, mostrar_estatisticas=False)
    auth_state["user"] = None
    body = (await client.get("/api/q/perfil/u/reservado")).json()
    assert body["avatar_url"] is None
    assert body["estatisticas"] is None
    assert "total" in body["pontuacao"]  # pontuação sempre presente


async def test_apelido_casa_case_insensitive(client, db_session, auth_state):
    await _seed_perfil(db_session, "user-D", "rochedo-17")
    auth_state["user"] = None
    assert (await client.get("/api/q/perfil/u/ROCHEDO-17")).status_code == 200
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST tests/test_perfil_publico.py`
Expected: FAIL — 404 sem corpo esperado / rota inexistente (o teste básico falha em `body["apelido"]`)

- [ ] **Step 3: Implementar em `backend/perfil_router.py`**

Import adicional no topo: `from sqlalchemy import select, text` (trocar o import existente de `select`).

```python
@router.get("/u/{apelido}")
async def perfil_publico(
    apelido: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    apelido = apelido.strip().lower()
    p = (
        await db.execute(select(PerfilUsuario).where(PerfilUsuario.apelido == apelido))
    ).scalars().first()
    if p is None:
        raise HTTPException(404, "perfil não encontrado")
    if not p.perfil_publico:
        raise HTTPException(404, detail={"privado": True})

    conta = (
        await db.execute(
            text('SELECT "createdAt", role FROM "user" WHERE id = :uid'),
            {"uid": p.owner_uid},
        )
    ).first()
    role = conta[1] if conta else None
    resumo = await perfil_service.resumo_perfil(db, p.owner_uid)

    estatisticas = None
    if p.mostrar_estatisticas:
        pont = resumo["pontuacao"]
        estatisticas = {
            "resolvidas": resumo["resolvidas"],
            "acertos": resumo["acertos"],
            "taxa": resumo["taxa"],
            "streak_dias": resumo["streak_dias"],
            "estudo": pont["estudo"],
            "metas": pont["metas"],
            "combos_x2": pont["combos_x2"],
            "combos_x3": pont["combos_x3"],
            "combos_x4": pont["combos_x4"],
        }
    return {
        "apelido": p.apelido,
        "avatar_url": _avatar_url(p) if p.mostrar_foto else None,
        "membro_desde": conta[0].isoformat() if conta and conta[0] else None,
        "badge": role if role in ("professor", "admin") else None,
        "pontuacao": {
            "total": resumo["pontuacao"]["total"],
            "forum": resumo["pontuacao"]["forum"],
            "comentarios": resumo["pontuacao"]["comentarios"],
        },
        "estatisticas": estatisticas,
    }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `PYTEST tests/test_perfil_publico.py`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add backend/perfil_router.py backend/tests/test_perfil_publico.py
git commit -m "feat(perfil): endpoint público /api/q/perfil/u/{apelido} com toggles de visibilidade"
```

---

### Task 6: Fórum — apelido e avatar do autor no serializer

**Files:**
- Modify: `backend/q_router.py` (funções `_display_name` ~linha 3147, `_serializar_comentario` ~3156, `listar_forum` ~3207 e os dois pontos de serialização unitária ~3422 e ~3511)
- Test: `backend/tests/test_forum_perfil.py`

**Interfaces:**
- Consumes: `perfil_service.perfis_forum_por_uids` (Task 2).
- Produces: todo comentário serializado ganha `autor_apelido: str|null` e `autor_avatar_url: str|null` (não-nulos apenas quando origem `studia` + apelido definido + perfil público; avatar exige também `mostrar_foto`). `display_name` passa a ser o apelido quando disponível.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/test_forum_perfil.py`:

```python
"""Fórum expõe apelido/avatar do autor conforme o perfil (e nunca o owner_uid)."""

import json

import pytest

from conftest import USER_A
from models import PerfilUsuario, Questao, QuestaoComentario

pytestmark = pytest.mark.asyncio


async def _seed(db_session, *, perfil: PerfilUsuario | None = None):
    db_session.add(Questao(id=99, id_externo=99, tipo="MULTIPLA_ESCOLHA",
                           enunciado_html="<p>E</p>", gabarito="A", status="ATIVA"))
    db_session.add(QuestaoComentario(id=1, questao_id=99, origem="studia",
                                     owner_uid="user-A", autor_nome="Witalo Rocha",
                                     texto_md="oi"))
    if perfil is not None:
        db_session.add(perfil)
    await db_session.commit()


async def test_apelido_substitui_nome_e_expoe_link(client, db_session):
    await _seed(db_session, perfil=PerfilUsuario(
        owner_uid="user-A", apelido="rochedo-16",
        avatar_key="avatars/11111111-1111-1111-1111-111111111111.webp"))
    r = await client.get("/api/q/questoes/99/forum")
    c = r.json()["comentarios"][0]
    assert c["display_name"] == "rochedo-16"
    assert c["autor_apelido"] == "rochedo-16"
    assert c["autor_avatar_url"].endswith(".webp")
    assert "user-A" not in json.dumps(c)  # owner_uid continua não exposto


async def test_sem_apelido_mostra_nome_sem_link(client, db_session):
    await _seed(db_session, perfil=None)
    c = (await client.get("/api/q/questoes/99/forum")).json()["comentarios"][0]
    assert c["display_name"] == "Witalo Rocha"
    assert c["autor_apelido"] is None
    assert c["autor_avatar_url"] is None


async def test_perfil_privado_nao_linka(client, db_session):
    await _seed(db_session, perfil=PerfilUsuario(
        owner_uid="user-A", apelido="oculto", perfil_publico=False))
    c = (await client.get("/api/q/questoes/99/forum")).json()["comentarios"][0]
    assert c["display_name"] == "Witalo Rocha"  # perfil privado → nome, sem apelido
    assert c["autor_apelido"] is None


async def test_mostrar_foto_false_esconde_avatar_mas_linka(client, db_session):
    await _seed(db_session, perfil=PerfilUsuario(
        owner_uid="user-A", apelido="rochedo-16",
        avatar_key="avatars/11111111-1111-1111-1111-111111111111.webp",
        mostrar_foto=False))
    c = (await client.get("/api/q/questoes/99/forum")).json()["comentarios"][0]
    assert c["autor_apelido"] == "rochedo-16"
    assert c["autor_avatar_url"] is None


async def test_criar_comentario_ja_volta_com_apelido(client, db_session, auth_state):
    db_session.add(PerfilUsuario(owner_uid="admin-1", apelido="prof-x"))
    db_session.add(Questao(id=98, id_externo=98, tipo="MULTIPLA_ESCOLHA",
                           enunciado_html="<p>E</p>", gabarito="A", status="ATIVA"))
    await db_session.commit()
    r = await client.post("/api/q/questoes/98/forum", json={"texto_md": "novo post"})
    assert r.status_code == 200, r.text
    assert r.json()["autor_apelido"] == "prof-x"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTEST tests/test_forum_perfil.py`
Expected: FAIL — `KeyError: 'autor_apelido'`

- [ ] **Step 3: Alterar `backend/q_router.py`**

No topo do arquivo, junto dos imports do projeto: `import perfil_service`.

Trocar `_display_name` e `_serializar_comentario`:

```python
def _display_name(c: QuestaoComentario, perfil: dict | None = None) -> str:
    """Persona (admin no quadro professores) > pseudônimo TC > apelido do perfil
    > nome real do studIA."""
    if c.persona_nome:
        return c.persona_nome
    if c.origem == "tc":
        return pseudonimo(c.autor_nome or str(c.tc_comentario_id or c.id))
    if perfil and perfil.get("apelido"):
        return perfil["apelido"]
    return c.autor_nome or "Anônimo"


def _serializar_comentario(
    c: QuestaoComentario, *, meu_voto: int, user: CurrentUser,
    respostas: list[dict[str, Any]], perfil: dict | None = None,
) -> dict[str, Any]:
    removido = c.deleted_at is not None
    nome = _display_name(c, perfil)
    dono = c.origem == "studia" and c.owner_uid == user.id
    eh_studia = c.origem == "studia"
    return {
        "id": c.id,
        "parent_id": c.parent_id,
        "origem": c.origem,
        "display_name": nome,
        "autor_inicial": (nome.strip()[:1] or "?").upper(),
        "autor_apelido": (perfil or {}).get("apelido") if eh_studia else None,
        "autor_avatar_url": (perfil or {}).get("avatar_url") if eh_studia else None,
        "texto_md": None if removido else c.texto_md,
        "score": c.score or 0,
        "meu_voto": meu_voto,
        "criado_em": (c.publicado_em or c.created_at).isoformat() if (c.publicado_em or c.created_at) else None,
        "editado": c.edited_at is not None,
        "removido": removido,
        "eh_professor": c.forum_tipo == "professores",
        "posso_editar": dono and not removido,
        "posso_excluir": (dono or user.is_admin) and not removido,
        "respostas": respostas,
    }
```

Em `listar_forum`, logo após carregar `todos`, carregar os perfis em lote e usar no `_serial`:

```python
    perfis = await perfil_service.perfis_forum_por_uids(
        db, {c.owner_uid for c in todos if c.origem == "studia" and c.owner_uid}
    )

    def _serial(c: QuestaoComentario, respostas: list[dict[str, Any]]) -> dict[str, Any]:
        return _serializar_comentario(
            c, meu_voto=meus.get(c.id, 0), user=user,
            respostas=respostas, perfil=perfis.get(c.owner_uid),
        )
```

Nos dois pontos de serialização unitária, antes do `return`, buscar o perfil do autor e passar. Hoje eles são exatamente:

- ~linha 3422: `return _serializar_comentario(c, meu_voto=meu, user=user, respostas=[])`
- ~linha 3511: `return _serializar_comentario(c, meu_voto=0, user=user, respostas=[])`

Ambos viram (mantendo o `meu_voto` original de cada um — `meu` no primeiro, `0` no segundo):

```python
    perfis = await perfil_service.perfis_forum_por_uids(
        db, {c.owner_uid} if c.origem == "studia" and c.owner_uid else set()
    )
    return _serializar_comentario(
        c, meu_voto=meu, user=user,  # no 2º call site: meu_voto=0
        respostas=[], perfil=perfis.get(c.owner_uid),
    )
```

- [ ] **Step 4: Rodar os testes novos + regressão do fórum**

Run: `PYTEST tests/test_forum_perfil.py tests/test_forum_api.py tests/test_forum_personas.py tests/test_forum_tc_importado.py`
Expected: PASS (novos + regressão intacta)

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_perfil.py
git commit -m "feat(forum): autor exibe apelido/avatar do perfil público (batch, sem N+1)"
```

---

### Task 7: Frontend — query keys + hooks de perfil

**Files:**
- Modify: `fontend/lib/queryKeys.ts`
- Create: `fontend/app/conta/usePerfil.ts`

**Interfaces:**
- Consumes: `apiJson`/`apiFetch`/`ApiError` de `fontend/lib/api.ts`.
- Produces (usados nas Tasks 8–10):
  - `qk.perfil()` e `qk.perfilPublico(apelido)`
  - Tipos `PerfilResumo`, `MeuPerfil`, `PerfilPublico`
  - Hooks: `useMeuPerfil()`, `useAtualizarPerfil()`, `useSubirAvatar()`, `useRemoverAvatar()`, `usePerfilPublico(apelido)`

- [ ] **Step 1: Adicionar as chaves em `fontend/lib/queryKeys.ts`** (antes do fechamento do objeto `qk`):

```ts
  perfil: () => ["q", "perfil"] as const,
  perfilPublico: (apelido: string) => ["q", "perfil", "u", apelido] as const,
```

- [ ] **Step 2: Criar `fontend/app/conta/usePerfil.ts`**

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

export type PerfilResumo = {
  pontuacao: {
    total: number; forum: number; estudo: number;
    metas: number; combos_x2: number; combos_x3: number; combos_x4: number;
    comentarios: number;
  };
  resolvidas: number;
  acertos: number;
  taxa: number;
  streak_dias: number;
};

export type MeuPerfil = {
  apelido: string | null;
  avatar_url: string | null;
  perfil_publico: boolean;
  mostrar_estatisticas: boolean;
  mostrar_foto: boolean;
  resumo: PerfilResumo;
};

export type PerfilPublico = {
  apelido: string;
  avatar_url: string | null;
  membro_desde: string | null;
  badge: "professor" | "admin" | null;
  pontuacao: { total: number; forum: number; comentarios: number };
  estatisticas: {
    resolvidas: number; acertos: number; taxa: number; streak_dias: number;
    estudo: number; metas: number; combos_x2: number; combos_x3: number; combos_x4: number;
  } | null;
};

export function useMeuPerfil() {
  return useQuery({
    queryKey: qk.perfil(),
    queryFn: () => apiJson<MeuPerfil>("/api/q/perfil"),
  });
}

export type PatchPerfil = Partial<{
  apelido: string;
  perfil_publico: boolean;
  mostrar_estatisticas: boolean;
  mostrar_foto: boolean;
}>;

export function useAtualizarPerfil() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PatchPerfil) =>
      apiJson<{ ok: boolean; apelido: string | null }>("/api/q/perfil", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.perfil() }),
  });
}

export function useSubirAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch("/api/q/perfil/avatar", { method: "POST", body: form });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(
          (data && typeof data.detail === "string" && data.detail) || "Erro ao enviar a foto."
        );
      }
      return res.json() as Promise<{ avatar_url: string }>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.perfil() }),
  });
}

export function useRemoverAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiJson<{ ok: boolean }>("/api/q/perfil/avatar", { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.perfil() }),
  });
}

export function usePerfilPublico(apelido: string) {
  return useQuery({
    queryKey: qk.perfilPublico(apelido),
    queryFn: () => apiJson<PerfilPublico>(`/api/q/perfil/u/${encodeURIComponent(apelido)}`),
    retry: false, // 404 (inexistente/privado) não deve re-tentar
  });
}
```

- [ ] **Step 3: Lint**

Run: `cd /home/wital/studia/.claude/worktrees/perfil-completo/fontend && pnpm install && pnpm lint`
Expected: sem erros novos

- [ ] **Step 4: Commit**

```bash
git add fontend/lib/queryKeys.ts fontend/app/conta/usePerfil.ts
git commit -m "feat(conta): hooks React Query do perfil (meu perfil, avatar, público)"
```

---

### Task 8: Frontend — `/conta` expandida (foto, apelido, visibilidade, resumo)

**Files:**
- Modify: `fontend/app/conta/ContaClient.tsx`
- Create: `fontend/app/conta/VisibilidadeCard.tsx`
- Create: `fontend/app/conta/ResumoCard.tsx`

**Interfaces:**
- Consumes: hooks/tipos da Task 7; `SectionCard`, `Field`, `NoticeBox`, `PrimaryBtn` já existentes no `ContaClient.tsx`; `Skeleton` de `@/app/components/ds` (verificar export em `fontend/app/components/ds/index.ts` — importar do caminho que o resto do app usa); `apiUrl` de `@/lib/api`.
- Produces: página `/conta` com header (foto+apelido), card Perfil com apelido+foto, card Visibilidade e card Resumo estatístico.

- [ ] **Step 1: Criar `fontend/app/conta/VisibilidadeCard.tsx`**

```tsx
"use client";

import { useAtualizarPerfil, useMeuPerfil } from "./usePerfil";
import { Skeleton } from "@/app/components/ds";

function Toggle({ label, desc, checked, onChange, disabled }: {
  label: string; desc: string; checked: boolean;
  onChange: (v: boolean) => void; disabled: boolean;
}) {
  return (
    <label className="flex items-start justify-between gap-4 cursor-pointer">
      <span>
        <span className="block text-sm font-medium text-fg-strong">{label}</span>
        <span className="block text-xs text-fg-faint">{desc}</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? "bg-primary" : "bg-border-dark"} disabled:opacity-50`}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
      </button>
    </label>
  );
}

export default function VisibilidadeCard() {
  const { data, isPending } = useMeuPerfil();
  const atualizar = useAtualizarPerfil();

  return (
    <section className="rounded-xl border border-border-dark bg-surface-dark p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg-strong mb-4">
        <span className="material-symbols-outlined text-primary text-[20px]">visibility</span>
        Visibilidade do perfil
      </h2>
      {isPending || !data ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          <Toggle
            label="Perfil público"
            desc="Seu perfil fica acessível pelo apelido e o fórum linka para ele."
            checked={data.perfil_publico}
            disabled={atualizar.isPending}
            onChange={(v) => atualizar.mutate({ perfil_publico: v })}
          />
          <Toggle
            label="Mostrar estatísticas de estudo"
            desc="Questões resolvidas, taxa de acerto, metas e combos no perfil público."
            checked={data.mostrar_estatisticas}
            disabled={atualizar.isPending}
            onChange={(v) => atualizar.mutate({ mostrar_estatisticas: v })}
          />
          <Toggle
            label="Mostrar foto"
            desc="Sem a foto, o perfil e o fórum exibem só as iniciais."
            checked={data.mostrar_foto}
            disabled={atualizar.isPending}
            onChange={(v) => atualizar.mutate({ mostrar_foto: v })}
          />
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Criar `fontend/app/conta/ResumoCard.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useMeuPerfil } from "./usePerfil";
import { Skeleton } from "@/app/components/ds";

function Stat({ label, valor }: { label: string; valor: string | number }) {
  return (
    <div className="rounded-lg bg-bg-dark px-3 py-2.5 text-center">
      <div className="text-lg font-bold text-fg-strong">{valor}</div>
      <div className="text-[0.65rem] uppercase tracking-wide text-fg-faint">{label}</div>
    </div>
  );
}

export default function ResumoCard() {
  const { data, isPending } = useMeuPerfil();
  const r = data?.resumo;

  return (
    <section className="rounded-xl border border-border-dark bg-surface-dark p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg-strong mb-4">
        <span className="material-symbols-outlined text-primary text-[20px]">military_tech</span>
        Resumo estatístico
      </h2>

      {isPending || !r ? (
        <div className="space-y-4">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          <div
            className="flex items-center justify-between rounded-lg bg-gradient-to-r from-primary/15 to-secondary/15 px-4 py-3"
            title="Pontuação final = pontos do fórum + metas ×10 + combos ×2 valem 20, ×3 valem 30 e ×4 valem 40"
          >
            <span className="text-sm font-medium text-fg">Pontuação final</span>
            <span className="text-2xl font-bold text-primary">{r.pontuacao.total}</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Fórum" valor={r.pontuacao.forum} />
            <Stat label="Estudo" valor={r.pontuacao.estudo} />
            <Stat label="Comentários" valor={r.pontuacao.comentarios} />
          </div>
          <div className="grid grid-cols-4 gap-2">
            <Stat label="Metas batidas" valor={r.pontuacao.metas} />
            <Stat label="Combos ×2" valor={r.pontuacao.combos_x2} />
            <Stat label="Combos ×3" valor={r.pontuacao.combos_x3} />
            <Stat label="Combos ×4" valor={r.pontuacao.combos_x4} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Resolvidas" valor={r.resolvidas} />
            <Stat label="Taxa de acerto" valor={`${r.taxa}%`} />
            <Stat label="Sequência (dias)" valor={r.streak_dias} />
          </div>
          <Link href="/painel" className="block text-sm text-primary hover:underline">
            Ver painel completo →
          </Link>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Alterar `fontend/app/conta/ContaClient.tsx`**

3a. Imports novos no topo (o arquivo já importa `useState` do react — estender a linha existente para `import { useRef, useState } from "react";`):

```tsx
import { apiUrl } from "@/lib/api";
import { useAtualizarPerfil, useMeuPerfil, useRemoverAvatar, useSubirAvatar } from "./usePerfil";
import VisibilidadeCard from "./VisibilidadeCard";
import ResumoCard from "./ResumoCard";
```

3b. No componente `ContaClient`, buscar o perfil e trocar o header — o círculo de 56px é espaço reservado fixo (a foto entra NO LUGAR das iniciais, sem deslocar nada):

```tsx
  const { data: perfil } = useMeuPerfil();

  // ... no JSX do header, substituir o <div className="h-14 w-14 ..."> por:
        <div className="h-14 w-14 rounded-full bg-gradient-to-tr from-primary to-secondary p-[2px]">
          {perfil?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={apiUrl(perfil.avatar_url)}
              alt="Foto de perfil"
              className="rounded-full h-full w-full object-cover"
            />
          ) : (
            <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
              <span className="text-lg font-bold text-fg-strong">
                {(user?.name || user?.email || "?").slice(0, 2).toUpperCase()}
              </span>
            </div>
          )}
        </div>
```

e abaixo do `<h1>`, junto ao e-mail:

```tsx
          <p className="text-sm text-fg-faint">
            {user?.email}
            {perfil?.apelido && <span className="text-primary"> · @{perfil.apelido}</span>}
          </p>
```

3c. Na lista de seções, incluir os cards novos:

```tsx
      <div className="space-y-6">
        <BillingSection />
        <ProfileCard name={user?.name} email={user?.email} />
        <VisibilidadeCard />
        <ResumoCard />
        <PasswordCard />
        {isAdmin && <CreateUserCard />}
      </div>
```

3d. Expandir o `ProfileCard` (substituir a função inteira) — nome continua no Better Auth; apelido/foto vão pro FastAPI:

```tsx
function ProfileCard({ name: initialName, email }: { name?: string; email?: string }) {
  const [name, setName] = useState(initialName || "");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const { data: perfil, isPending: perfilPending } = useMeuPerfil();
  const [apelido, setApelido] = useState<string | null>(null); // null = ainda não editado
  const atualizar = useAtualizarPerfil();
  const subirAvatar = useSubirAvatar();
  const removerAvatar = useRemoverAvatar();
  const fileRef = useRef<HTMLInputElement>(null);

  const apelidoAtual = apelido ?? perfil?.apelido ?? "";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setNotice(null);
    const { error } = await authClient.updateUser({ name });
    let msgErro = error?.message;
    if (!msgErro && apelido !== null && apelido !== (perfil?.apelido ?? "")) {
      try {
        await atualizar.mutateAsync({ apelido });
      } catch (err) {
        msgErro = err instanceof Error ? err.message : "Erro ao salvar o apelido.";
      }
    }
    setLoading(false);
    setNotice(msgErro ? { kind: "err", msg: msgErro } : { kind: "ok", msg: "Perfil atualizado." });
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setNotice(null);
    try {
      await subirAvatar.mutateAsync(file);
      setNotice({ kind: "ok", msg: "Foto atualizada." });
    } catch (err) {
      setNotice({ kind: "err", msg: err instanceof Error ? err.message : "Erro ao enviar a foto." });
    }
  }

  return (
    <SectionCard title="Perfil" icon="badge">
      <form onSubmit={save} className="space-y-4">
        <div className="flex items-center gap-4">
          <div className="h-16 w-16 rounded-full bg-bg-dark overflow-hidden flex items-center justify-center shrink-0">
            {perfil?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={apiUrl(perfil.avatar_url)} alt="Foto de perfil" className="h-full w-full object-cover" />
            ) : (
              <span className="material-symbols-outlined text-fg-faint text-[32px]">person</span>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={onFile} />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={subirAvatar.isPending}
              className="text-sm text-primary hover:underline disabled:opacity-50 text-left"
            >
              {subirAvatar.isPending ? "Enviando…" : perfil?.avatar_url ? "Trocar foto" : "Inserir foto"}
            </button>
            {perfil?.avatar_url && (
              <button
                type="button"
                onClick={() => removerAvatar.mutate()}
                disabled={removerAvatar.isPending}
                className="text-sm text-fg-faint hover:text-error disabled:opacity-50 text-left"
              >
                Remover foto
              </button>
            )}
            <span className="text-xs text-fg-faint">png, jpg ou webp, até 5 MB</span>
          </div>
        </div>

        <Field label="Nome" value={name} onChange={(e) => setName(e.target.value)} placeholder="Seu nome" />
        <Field
          label="Apelido único (fórum)"
          value={apelidoAtual}
          onChange={(e) => setApelido(e.target.value.toLowerCase())}
          placeholder={perfilPending ? "carregando…" : "ex.: rochedo-16"}
          disabled={perfilPending}
        />
        <p className="text-xs text-fg-faint -mt-2">
          3 a 32 caracteres: letras minúsculas, números e hífens. Seu perfil público fica em /u/apelido.
        </p>
        <Field label="E-mail" value={email || ""} disabled />
        <NoticeBox notice={notice} />
        <PrimaryBtn loading={loading || atualizar.isPending}>Salvar perfil</PrimaryBtn>
      </form>
    </SectionCard>
  );
}
```

- [ ] **Step 4: Verificar export do Skeleton** — abrir `fontend/app/components/ds/index.ts`; se `Skeleton` não estiver exportado lá, ajustar os imports dos cards para `@/app/components/ds/Skeleton` (conferir como outras telas importam, ex.: `grep -rn "ds/Skeleton\|from \"@/app/components/ds\"" fontend/app | head`).

- [ ] **Step 5: Lint + smoke visual**

Run: `pnpm lint` (na pasta `fontend` do worktree)
Expected: sem erros. (Smoke no navegador fica para a verificação final — o dev server roda o checkout principal.)

- [ ] **Step 6: Commit**

```bash
git add fontend/app/conta/ContaClient.tsx fontend/app/conta/VisibilidadeCard.tsx fontend/app/conta/ResumoCard.tsx
git commit -m "feat(conta): perfil expandido — foto, apelido, visibilidade e resumo estatístico"
```

---

### Task 9: Frontend — página pública `/u/[apelido]`

**Files:**
- Create: `fontend/app/u/[apelido]/page.tsx`
- Create: `fontend/app/u/[apelido]/PerfilPublicoClient.tsx`

**Interfaces:**
- Consumes: `usePerfilPublico` (Task 7), `ApiError` de `@/lib/api`, `Skeleton` do ds.
- Produces: rota `/u/<apelido>` com estados: skeleton → perfil | "perfil privado" | "não encontrado".

- [ ] **Step 1: Criar `fontend/app/u/[apelido]/page.tsx`** (Next 16: `params` é Promise)

```tsx
import PerfilPublicoClient from "./PerfilPublicoClient";

export default async function PerfilPublicoPage({
  params,
}: {
  params: Promise<{ apelido: string }>;
}) {
  const { apelido } = await params;
  return <PerfilPublicoClient apelido={apelido} />;
}
```

- [ ] **Step 2: Criar `fontend/app/u/[apelido]/PerfilPublicoClient.tsx`**

```tsx
"use client";

import Link from "next/link";
import { ApiError, apiUrl } from "@/lib/api";
import { Skeleton } from "@/app/components/ds";
import { usePerfilPublico } from "../../conta/usePerfil";

function Stat({ label, valor }: { label: string; valor: string | number }) {
  return (
    <div className="rounded-lg bg-surface-dark px-3 py-3 text-center">
      <div className="text-xl font-bold text-fg-strong">{valor}</div>
      <div className="text-[0.65rem] uppercase tracking-wide text-fg-faint">{label}</div>
    </div>
  );
}

function EstadoVazio({ icone, titulo, texto }: { icone: string; titulo: string; texto: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-border-dark bg-surface-dark px-6 py-16 text-center">
      <span className="material-symbols-outlined text-[40px] text-fg-faint">{icone}</span>
      <h1 className="text-lg font-semibold text-fg-strong">{titulo}</h1>
      <p className="text-sm text-fg-faint">{texto}</p>
      <Link href="/" className="mt-2 text-sm text-primary hover:underline">Voltar ao início</Link>
    </div>
  );
}

export default function PerfilPublicoClient({ apelido }: { apelido: string }) {
  const { data, isPending, error } = usePerfilPublico(apelido);

  if (isPending) {
    return (
      <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-20 w-20 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-32" />
          </div>
        </div>
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !data) {
    const privado =
      error instanceof ApiError &&
      typeof (error.data as { detail?: { privado?: boolean } })?.detail === "object" &&
      (error.data as { detail?: { privado?: boolean } }).detail?.privado === true;
    return (
      <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto">
        {privado ? (
          <EstadoVazio icone="lock" titulo="Perfil privado"
            texto="Este usuário optou por não exibir o perfil publicamente." />
        ) : (
          <EstadoVazio icone="person_off" titulo="Perfil não encontrado"
            texto="Não existe nenhum usuário com este apelido." />
        )}
      </div>
    );
  }

  const e = data.estatisticas;
  return (
    <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <div className="h-20 w-20 rounded-full bg-gradient-to-tr from-primary to-secondary p-[2px] shrink-0">
          {data.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={apiUrl(data.avatar_url)} alt={`Foto de ${data.apelido}`}
              className="rounded-full h-full w-full object-cover" />
          ) : (
            <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
              <span className="text-xl font-bold text-fg-strong">
                {data.apelido.slice(0, 2).toUpperCase()}
              </span>
            </div>
          )}
        </div>
        <div>
          <h1 className="text-2xl font-bold text-fg-strong">@{data.apelido}</h1>
          {data.membro_desde && (
            <p className="text-sm text-fg-faint">
              Membro desde {new Date(data.membro_desde).toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}
            </p>
          )}
        </div>
        {data.badge && (
          <span className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wide text-secondary bg-secondary/10">
            <span className="material-symbols-outlined text-[14px]">
              {data.badge === "admin" ? "shield_person" : "school"}
            </span>
            {data.badge}
          </span>
        )}
      </div>

      <div
        className="flex items-center justify-between rounded-xl border border-border-dark bg-gradient-to-r from-primary/15 to-secondary/15 px-5 py-4"
        title="Pontuação final = pontos do fórum + metas ×10 + combos ×2 valem 20, ×3 valem 30 e ×4 valem 40"
      >
        <span className="text-sm font-medium text-fg">Pontuação final</span>
        <span className="text-3xl font-bold text-primary">{data.pontuacao.total}</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat label="Pontos no fórum" valor={data.pontuacao.forum} />
        <Stat label="Comentários" valor={data.pontuacao.comentarios} />
      </div>

      {e && (
        <>
          <div className="grid grid-cols-4 gap-2">
            <Stat label="Metas batidas" valor={e.metas} />
            <Stat label="Combos ×2" valor={e.combos_x2} />
            <Stat label="Combos ×3" valor={e.combos_x3} />
            <Stat label="Combos ×4" valor={e.combos_x4} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Resolvidas" valor={e.resolvidas} />
            <Stat label="Taxa de acerto" valor={`${e.taxa}%`} />
            <Stat label="Sequência (dias)" valor={e.streak_dias} />
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Lint**

Run: `pnpm lint`
Expected: sem erros

- [ ] **Step 4: Commit**

```bash
git add "fontend/app/u/[apelido]/page.tsx" "fontend/app/u/[apelido]/PerfilPublicoClient.tsx"
git commit -m "feat(perfil): página pública /u/[apelido] com pontuação e estatísticas"
```

---

### Task 10: Frontend — fórum linka o autor e mostra o avatar

**Files:**
- Modify: `fontend/app/q/hooks/useForum.ts` (tipo `Comentario`)
- Modify: `fontend/app/q/caderno/[id]/components/CommentItem.tsx`

**Interfaces:**
- Consumes: campos `autor_apelido`/`autor_avatar_url` do serializer (Task 6).
- Produces: no fórum, autor com apelido vira link para `/u/[apelido]`; avatar real substitui a inicial quando disponível.

- [ ] **Step 1: Adicionar os campos ao tipo `Comentario` em `fontend/app/q/hooks/useForum.ts`** (localizar a interface/type `Comentario` e acrescentar):

```ts
  autor_apelido: string | null;
  autor_avatar_url: string | null;
```

- [ ] **Step 2: Alterar `fontend/app/q/caderno/[id]/components/CommentItem.tsx`**

Imports novos:

```tsx
import Link from "next/link";
import { apiUrl } from "@/lib/api";
```

Substituir o bloco do autor (o `<span>` da inicial + `<span>` do nome, linhas ~55-58) por:

```tsx
          {c.autor_avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={apiUrl(c.autor_avatar_url)} alt=""
              className="h-6 w-6 rounded-full object-cover" />
          ) : (
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20 text-[10px] font-bold text-primary">
              {c.autor_inicial}
            </span>
          )}
          {c.autor_apelido ? (
            <Link href={`/u/${c.autor_apelido}`}
              className="font-semibold text-fg hover:text-primary hover:underline">
              {c.display_name}
            </Link>
          ) : (
            <span className="font-semibold text-fg">{c.display_name}</span>
          )}
```

- [ ] **Step 3: Lint**

Run: `pnpm lint`
Expected: sem erros

- [ ] **Step 4: Commit**

```bash
git add fontend/app/q/hooks/useForum.ts "fontend/app/q/caderno/[id]/components/CommentItem.tsx"
git commit -m "feat(forum): autor com apelido vira link p/ perfil público + avatar real"
```

---

### Task 11: Verificação final (suíte completa + smoke)

**Files:** nenhum novo (só correções que a verificação apontar)

- [ ] **Step 1: Suíte backend completa**

Run: `PYTEST tests/ -q`
Expected: TODOS passam (incluindo `test_alembic_no_drift.py` e regressões do fórum/meta diária). Corrigir qualquer quebra antes de seguir.

- [ ] **Step 2: Lint frontend completo**

Run: `cd /home/wital/studia/.claude/worktrees/perfil-completo/fontend && pnpm lint`
Expected: sem erros

- [ ] **Step 3: Smoke manual end-to-end** — usar a skill `verify`/`run` para exercitar no dev (o dev server serve o checkout principal; o smoke pleno acontece após o merge, antes do `./build.sh`):
  1. `/conta`: definir apelido, subir foto (ver preview trocar), alternar os 3 toggles, conferir card de resumo.
  2. `/u/<apelido>`: perfil aparece; desligar "perfil público" → página vira "Perfil privado".
  3. Fórum de uma questão: comentário próprio mostra apelido linkado + avatar.

- [ ] **Step 4: Commit final de ajustes (se houver)** e encerrar com a skill superpowers:finishing-a-development-branch — fluxo do projeto: merge na `main` a partir do checkout principal (`git merge worktree-perfil-completo`), `git push`, deploy `./build.sh`, `git worktree remove`.
