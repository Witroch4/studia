# Painel Admin de Assinaturas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao admin uma tela (`/admin/assinaturas`) para ver e gerir assinaturas Stripe: overview com MRR, lista de todos os usuários com plano, e ações de conceder Pro manual, cancelar (fim do período / imediato / imediato+reembolso, com motivo e banir opcional) e sincronizar do Stripe.

**Architecture:** Novo `admin_billing_router.py` (FastAPI, todo sob `require_admin`) que lê o DB local rápido para lista/overview e chama o Stripe ao vivo sob demanda no detalhe e nas ações. Reusa `stripe_client.stripe_request`, `billing_router._upsert_sub`, a tabela `user` do Better Auth e o modelo `Voucher` (conceder Pro = voucher auto-resgatado). Frontend é uma página client com guard admin + React Query, espelhando `app/admin/vouchers/page.tsx`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async (raw `text()` p/ tabela `user`) / Alembic / Next.js 16 / React 19 / TanStack Query / Tailwind v4.

> **Nota de verificação:** o projeto **não tem suíte de testes** (CLAUDE.md: "No test suites exist yet"). Verificação por: (a) backend importa sem erro (`python -c "import admin_billing_router"`), (b) `alembic upgrade head` aplica a migração, (c) `pnpm lint` no frontend, (d) smoke manual via `apiJson`/curl. TDD com pytest não se aplica aqui — segue a convenção real do repo.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/models.py` (modificar) | 3 colunas novas em `Assinatura`: `cancel_motivo`, `cancel_admin_uid`, `cancel_em`. |
| `backend/alembic/versions/b2c3d4e5f6a7_cancel_admin_fields.py` (criar) | Migração das 3 colunas. |
| `backend/billing_router.py` (modificar) | Exportar `_upsert_sub` (já é módulo-level; importável). Sem mudança de lógica. |
| `backend/admin_billing_router.py` (criar) | Router admin: `/overview`, `/usuarios`, `/usuarios/{uid}`, `/conceder`, `/cancelar`, `/sincronizar`. |
| `backend/main.py` (modificar) | `include_router(admin_billing_router)`. |
| `fontend/lib/queryKeys.ts` (modificar) | Chaves `adminAssinaturas*`. |
| `fontend/app/components/Sidebar.tsx` (modificar) | Item `adminOnly` "Assinaturas". |
| `fontend/app/admin/assinaturas/page.tsx` (criar) | Overview + tabela + busca/filtro. |
| `fontend/app/admin/assinaturas/DetalheDrawer.tsx` (criar) | Drawer de detalhe + ações (conceder/cancelar/sincronizar). |

---

## Task 1: Migração — colunas de cancelamento em `assinaturas`

**Files:**
- Modify: `backend/models.py` (classe `Assinatura`, após `cancel_at_period_end`)
- Create: `backend/alembic/versions/b2c3d4e5f6a7_cancel_admin_fields.py`

- [ ] **Step 1: Adicionar as colunas ao model**

Em `backend/models.py`, na classe `Assinatura`, logo após a linha `cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)`, inserir:

```python
    # Cancelamento administrativo (por violação etc.) — preenchido pelo painel admin.
    cancel_motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancel_admin_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cancel_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

Confirmar que `Text` está importado no topo de `models.py` (junto de `String`, `Integer`, etc.). Se não estiver, adicioná-lo ao import `from sqlalchemy import (...)`.

- [ ] **Step 2: Verificar que `Text` está importado**

Run: `cd backend && grep -n "from sqlalchemy import" models.py | head -1 && grep -n "Text" models.py | head -3`
Expected: aparece `Text` no import. Se não, adicionar `Text` ao import e rodar de novo.

- [ ] **Step 3: Criar a migração Alembic**

Criar `backend/alembic/versions/b2c3d4e5f6a7_cancel_admin_fields.py`:

```python
"""campos de cancelamento administrativo em assinaturas

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assinaturas', sa.Column('cancel_motivo', sa.Text(), nullable=True))
    op.add_column('assinaturas', sa.Column('cancel_admin_uid', sa.String(length=64), nullable=True))
    op.add_column('assinaturas', sa.Column('cancel_em', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('assinaturas', 'cancel_em')
    op.drop_column('assinaturas', 'cancel_admin_uid')
    op.drop_column('assinaturas', 'cancel_motivo')
```

- [ ] **Step 4: Aplicar a migração no banco de dev**

Run: `cd backend && alembic upgrade head`
Expected: termina sem erro; saída inclui `Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7`.
(Se rodar fora do container, garanta `DATABASE_URL` apontando ao Postgres de dev — host port 5433. Alternativa: `./dev.sh migrate`.)

- [ ] **Step 5: Confirmar as colunas no banco**

Run: `cd backend && alembic current`
Expected: mostra `b2c3d4e5f6a7 (head)`.

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/alembic/versions/b2c3d4e5f6a7_cancel_admin_fields.py
git commit -m "feat(billing): colunas de cancelamento admin em assinaturas (motivo/admin/data)"
```

---

## Task 2: Backend — `admin_billing_router.py`

**Files:**
- Create: `backend/admin_billing_router.py`

Este é o coração do recurso. Cria o arquivo completo num passo (arquivo novo coeso), depois verifica import.

- [ ] **Step 1: Criar o router completo**

Criar `backend/admin_billing_router.py` com o conteúdo abaixo:

```python
"""Painel admin de assinaturas — visão geral, lista de usuários e gestão.

Tudo aqui é admin-only. Leitura rápida do DB local (lista/overview) e chamadas
ao Stripe ao vivo apenas no detalhe de um usuário e nas ações (cancelar/sincronizar).
Conceder Pro manual reaproveita o modelo Voucher (auto-resgatado na conta).
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_admin
from billing_router import _upsert_sub
from database import get_db
from models import Assinatura, Voucher
from stripe_client import (
    STRIPE_PRICE_ID,
    PRECO_LABEL,
    StripeError,
    stripe_configurado,
    stripe_request,
)

router = APIRouter(prefix="/api/admin/billing", tags=["admin-billing"])

_UTC = timezone.utc
_ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Cache em memória do valor unitário do preço (centavos) p/ MRR. None = ainda não buscado.
_preco_cache: dict[str, Any] = {"centavos": None, "moeda": "brl"}


def _gerar_codigo() -> str:
    bloco = lambda: "".join(secrets.choice(_ALFABETO) for _ in range(4))
    return f"ADM-{bloco()}-{bloco()}"


def _label_para_centavos(label: str) -> Optional[int]:
    """Extrai centavos de um rótulo tipo 'R$ 29,90/mês' (fallback do MRR)."""
    m = re.search(r"(\d+)[.,](\d{2})", label)
    if m:
        return int(m.group(1)) * 100 + int(m.group(2))
    m = re.search(r"(\d+)", label)
    return int(m.group(1)) * 100 if m else None


async def _preco_centavos() -> tuple[Optional[int], str]:
    """Valor unitário do preço (centavos, moeda). Stripe 1×, cacheado; fallback no label."""
    if _preco_cache["centavos"] is not None:
        return _preco_cache["centavos"], _preco_cache["moeda"]
    if stripe_configurado() and STRIPE_PRICE_ID:
        try:
            preco = await stripe_request("GET", f"/prices/{STRIPE_PRICE_ID}")
            if preco.get("unit_amount") is not None:
                _preco_cache["centavos"] = int(preco["unit_amount"])
                _preco_cache["moeda"] = preco.get("currency", "brl")
                return _preco_cache["centavos"], _preco_cache["moeda"]
        except StripeError:
            pass
    return _label_para_centavos(PRECO_LABEL), "brl"


# ─── Overview ───────────────────────────────────────────────────

@router.get("/overview")
async def overview(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Contadores por status, considerando só a assinatura mais recente de cada usuário.
    row = (
        await db.execute(
            text(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (usuario_uid) usuario_uid, status, current_period_end
                    FROM assinaturas
                    ORDER BY usuario_uid, updated_at DESC
                )
                SELECT
                    count(*) FILTER (
                        WHERE status IN ('active','trialing')
                          AND (current_period_end IS NULL OR current_period_end > now())
                    ) AS ativos,
                    count(*) FILTER (WHERE status = 'past_due') AS atraso,
                    count(*) FILTER (
                        WHERE status IN ('canceled','unpaid','incomplete_expired')
                    ) AS cancelados
                FROM latest
                """
            )
        )
    ).mappings().first()
    ativos = int(row["ativos"] or 0)
    atraso = int(row["atraso"] or 0)
    cancelados = int(row["cancelados"] or 0)

    total_usuarios = int(
        (await db.execute(text('SELECT count(*) FROM "user"'))).scalar() or 0
    )
    admins = int(
        (await db.execute(text(
            "SELECT count(*) FROM \"user\" WHERE role = 'admin'"
        ))).scalar() or 0
    )
    # Contas com voucher vigente e SEM assinatura Stripe ativa (não contar duplicado).
    pro_voucher = int(
        (await db.execute(text(
            """
            SELECT count(DISTINCT v.resgatado_por_uid)
            FROM vouchers v
            WHERE v.pro_ate > now()
              AND v.resgatado_por_uid IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM assinaturas a
                  WHERE a.usuario_uid = v.resgatado_por_uid
                    AND a.status IN ('active','trialing')
                    AND (a.current_period_end IS NULL OR a.current_period_end > now())
              )
            """
        ))).scalar() or 0
    )
    gratis = max(0, total_usuarios - ativos - pro_voucher - admins)

    centavos, moeda = await _preco_centavos()
    mrr_centavos = (centavos or 0) * ativos

    return {
        "total_usuarios": total_usuarios,
        "ativos": ativos,
        "atraso": atraso,
        "cancelados": cancelados,
        "pro_voucher": pro_voucher,
        "admins": admins,
        "gratis": gratis,
        "preco_centavos": centavos,
        "moeda": moeda,
        "mrr_centavos": mrr_centavos,
        "stripe_configurado": stripe_configurado(),
    }


# ─── Lista de usuários ──────────────────────────────────────────

@router.get("/usuarios")
async def listar_usuarios(
    q: Optional[str] = None,
    plano: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    like = f"%{q.strip()}%" if q and q.strip() else None
    plano_f = plano if plano in {"admin", "pro_stripe", "pro_voucher", "free"} else None

    rows = (
        await db.execute(
            text(
                """
                SELECT * FROM (
                    SELECT
                        u.id, u.email, u.name,
                        COALESCE(u.role,'user')   AS role,
                        COALESCE(u.banned,false)  AS banned,
                        a.status, a.current_period_end, a.cancel_at_period_end,
                        a.stripe_customer_id, a.stripe_subscription_id,
                        v.pro_ate,
                        CASE
                            WHEN COALESCE(u.role,'user') = 'admin' THEN 'admin'
                            WHEN a.status IN ('active','trialing')
                                 AND (a.current_period_end IS NULL OR a.current_period_end > now())
                                 THEN 'pro_stripe'
                            WHEN v.pro_ate > now() THEN 'pro_voucher'
                            ELSE 'free'
                        END AS plano,
                        count(*) OVER() AS total_rows
                    FROM "user" u
                    LEFT JOIN LATERAL (
                        SELECT * FROM assinaturas
                        WHERE usuario_uid = u.id
                        ORDER BY updated_at DESC LIMIT 1
                    ) a ON true
                    LEFT JOIN LATERAL (
                        SELECT max(pro_ate) AS pro_ate FROM vouchers
                        WHERE resgatado_por_uid = u.id
                    ) v ON true
                ) t
                WHERE (:like IS NULL OR t.email ILIKE :like OR t.name ILIKE :like)
                  AND (:plano IS NULL OR t.plano = :plano)
                ORDER BY t.email
                LIMIT :limit OFFSET :offset
                """
            ),
            {"like": like, "plano": plano_f, "limit": page_size, "offset": offset},
        )
    ).mappings().all()

    total = int(rows[0]["total_rows"]) if rows else 0
    usuarios = [
        {
            "uid": r["id"],
            "email": r["email"],
            "name": r["name"],
            "role": r["role"],
            "banned": bool(r["banned"]),
            "plano": r["plano"],
            "status": r["status"],
            "current_period_end": r["current_period_end"].isoformat() if r["current_period_end"] else None,
            "cancel_at_period_end": bool(r["cancel_at_period_end"]) if r["cancel_at_period_end"] is not None else False,
            "pro_ate": r["pro_ate"].isoformat() if r["pro_ate"] else None,
            "stripe_customer_id": r["stripe_customer_id"],
            "stripe_subscription_id": r["stripe_subscription_id"],
        }
        for r in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "usuarios": usuarios}


# ─── Detalhe (Stripe ao vivo) ───────────────────────────────────

async def _email_do_uid(db: AsyncSession, uid: str) -> Optional[dict[str, Any]]:
    return (
        await db.execute(
            text('SELECT id, email, name, COALESCE(role,\'user\') AS role, '
                 'COALESCE(banned,false) AS banned FROM "user" WHERE id = :uid'),
            {"uid": uid},
        )
    ).mappings().first()


@router.get("/usuarios/{uid}")
async def detalhe_usuario(
    uid: str,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    u = await _email_do_uid(db, uid)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")

    ass = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid)
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()

    vouchers = (
        await db.execute(
            select(Voucher).where(Voucher.resgatado_por_uid == uid).order_by(Voucher.pro_ate.desc())
        )
    ).scalars().all()

    stripe_subs: list[dict[str, Any]] = []
    stripe_erro: Optional[str] = None
    customer_id = ass.stripe_customer_id if ass else None
    if customer_id and stripe_configurado():
        try:
            resp = await stripe_request(
                "GET",
                f"/subscriptions?customer={customer_id}&status=all&limit=10&expand[]=data.latest_invoice",
            )
            for s in resp.get("data", []):
                inv = s.get("latest_invoice") or {}
                inv = inv if isinstance(inv, dict) else {}
                stripe_subs.append({
                    "id": s.get("id"),
                    "status": s.get("status"),
                    "cancel_at_period_end": bool(s.get("cancel_at_period_end")),
                    "current_period_end": s.get("current_period_end"),
                    "ultima_cobranca_centavos": inv.get("amount_paid"),
                    "payment_intent": inv.get("payment_intent"),
                    "moeda": inv.get("currency"),
                })
        except StripeError as exc:
            stripe_erro = exc.message

    return {
        "usuario": {
            "uid": u["id"], "email": u["email"], "name": u["name"],
            "role": u["role"], "banned": bool(u["banned"]),
        },
        "assinatura_local": {
            "status": ass.status if ass else None,
            "stripe_subscription_id": ass.stripe_subscription_id if ass else None,
            "stripe_customer_id": customer_id,
            "current_period_end": ass.current_period_end.isoformat() if ass and ass.current_period_end else None,
            "cancel_at_period_end": ass.cancel_at_period_end if ass else False,
            "cancel_motivo": ass.cancel_motivo if ass else None,
            "cancel_em": ass.cancel_em.isoformat() if ass and ass.cancel_em else None,
        } if ass else None,
        "vouchers": [
            {"codigo": v.codigo, "dias": v.dias,
             "pro_ate": v.pro_ate.isoformat() if v.pro_ate else None,
             "resgatado_em": v.resgatado_em.isoformat() if v.resgatado_em else None}
            for v in vouchers
        ],
        "stripe_subscriptions": stripe_subs,
        "stripe_erro": stripe_erro,
    }


# ─── Conceder Pro manual (via voucher auto-resgatado) ───────────

class ConcederIn(BaseModel):
    dias: int = Field(default=365, ge=1, le=3650)


@router.post("/usuarios/{uid}/conceder")
async def conceder_pro(
    uid: str,
    body: ConcederIn,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    u = await _email_do_uid(db, uid)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")

    # Estende a partir da data PRO mais distante já vigente (Stripe ou voucher anterior).
    base = datetime.now(_UTC)
    ass = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid, Assinatura.status.in_(("active", "trialing")))
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if ass and ass.current_period_end:
        fim = ass.current_period_end
        if fim.tzinfo is None:
            fim = fim.replace(tzinfo=_UTC)
        if fim > base:
            base = fim
    maior_voucher = (
        await db.execute(
            select(Voucher.pro_ate)
            .where(Voucher.resgatado_por_uid == uid, Voucher.pro_ate.isnot(None))
            .order_by(Voucher.pro_ate.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if maior_voucher:
        mv = maior_voucher if maior_voucher.tzinfo else maior_voucher.replace(tzinfo=_UTC)
        if mv > base:
            base = mv

    pro_ate = base + timedelta(days=body.dias)
    v = Voucher(
        codigo=f"{_gerar_codigo()}-{secrets.token_hex(2).upper()}",
        dias=body.dias,
        criado_por_uid=admin.id,
        resgatado_por_uid=uid,
        resgatado_em=datetime.now(_UTC),
        pro_ate=pro_ate,
    )
    db.add(v)
    await db.commit()
    return {"ok": True, "dias": body.dias, "pro_ate": pro_ate.isoformat(), "codigo": v.codigo}


# ─── Cancelar (3 modos + banir opcional) ────────────────────────

class CancelarIn(BaseModel):
    modo: str = Field(default="fim_periodo")  # fim_periodo | imediato | imediato_reembolso
    motivo: Optional[str] = None
    banir: bool = False


@router.post("/usuarios/{uid}/cancelar")
async def cancelar(
    uid: str,
    body: CancelarIn,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if body.modo not in {"fim_periodo", "imediato", "imediato_reembolso"}:
        raise HTTPException(400, "modo inválido")
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado (faltam chaves Stripe)")

    ass = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid, Assinatura.stripe_subscription_id.isnot(None))
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if ass is None or not ass.stripe_subscription_id:
        raise HTTPException(400, "usuário sem assinatura Stripe ativa")
    sub_id = ass.stripe_subscription_id

    reembolso: Optional[dict[str, Any]] = None
    try:
        if body.modo == "fim_periodo":
            sub = await stripe_request(
                "POST", f"/subscriptions/{sub_id}", {"cancel_at_period_end": "true"}
            )
            await _upsert_sub(db, sub)
        else:
            if body.modo == "imediato_reembolso":
                sub_atual = await stripe_request(
                    "GET", f"/subscriptions/{sub_id}?expand[]=latest_invoice"
                )
                inv = sub_atual.get("latest_invoice") or {}
                inv = inv if isinstance(inv, dict) else {}
                pi = inv.get("payment_intent")
                if not pi:
                    raise HTTPException(400, "sem cobrança a reembolsar nesta assinatura")
                ref = await stripe_request("POST", "/refunds", {"payment_intent": pi})
                reembolso = {"id": ref.get("id"), "centavos": ref.get("amount"), "status": ref.get("status")}
            sub = await stripe_request("DELETE", f"/subscriptions/{sub_id}")
            await _upsert_sub(db, sub)
    except StripeError as exc:
        raise HTTPException(502, f"Stripe: {exc.message}") from exc

    # Registro administrativo no DB local.
    ass.cancel_motivo = body.motivo
    ass.cancel_admin_uid = admin.id
    ass.cancel_em = datetime.now(_UTC)

    banido = False
    if body.banir:
        await db.execute(
            text('UPDATE "user" SET banned = true WHERE id = :uid'), {"uid": uid}
        )
        banido = True

    await db.commit()
    return {"ok": True, "modo": body.modo, "reembolso": reembolso, "banido": banido}


# ─── Sincronizar do Stripe ──────────────────────────────────────

@router.post("/usuarios/{uid}/sincronizar")
async def sincronizar(
    uid: str,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado (faltam chaves Stripe)")
    ass = (
        await db.execute(
            select(Assinatura)
            .where(Assinatura.usuario_uid == uid, Assinatura.stripe_customer_id.isnot(None))
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if ass is None or not ass.stripe_customer_id:
        raise HTTPException(400, "usuário sem customer Stripe")
    try:
        resp = await stripe_request(
            "GET", f"/subscriptions?customer={ass.stripe_customer_id}&status=all&limit=10"
        )
    except StripeError as exc:
        raise HTTPException(502, f"Stripe: {exc.message}") from exc

    n = 0
    for sub in resp.get("data", []):
        await _upsert_sub(db, sub, uid_fallback=uid, customer_fallback=ass.stripe_customer_id)
        n += 1
    await db.commit()
    return {"ok": True, "sincronizadas": n}
```

- [ ] **Step 2: Verificar que o módulo importa sem erro**

Run: `cd backend && python -c "import admin_billing_router; print('ok', len(admin_billing_router.router.routes))"`
Expected: imprime `ok 6` (6 rotas). Se faltar dependência, rode dentro do container: `./dev.sh shell backend` e repita.

- [ ] **Step 3: Commit**

```bash
git add backend/admin_billing_router.py
git commit -m "feat(admin): router de gestão de assinaturas (overview, lista, conceder, cancelar, sincronizar)"
```

---

## Task 3: Backend — registrar o router em `main.py`

**Files:**
- Modify: `backend/main.py` (bloco de `include_router`, junto aos demais)

- [ ] **Step 1: Adicionar o include_router**

Em `backend/main.py`, logo após o bloco do `voucher_router`:

```python
from voucher_router import router as voucher_router  # noqa: E402
app.include_router(voucher_router)
```

inserir:

```python
# Painel admin de assinaturas (gestão Stripe)
from admin_billing_router import router as admin_billing_router  # noqa: E402
app.include_router(admin_billing_router)
```

- [ ] **Step 2: Verificar que o app sobe com a rota registrada**

Run: `cd backend && python -c "import main; print([r.path for r in main.app.routes if '/admin/billing' in getattr(r, 'path', '')])"`
Expected: lista contém `/api/admin/billing/overview`, `/api/admin/billing/usuarios`, etc.

- [ ] **Step 3: Smoke do guard admin (não-admin → 403)**

Com o dev rodando (`./dev.sh up:d`), sem cookie de sessão:
Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8011/api/admin/billing/overview`
Expected: `401` (sem sessão) — confirma que a rota existe e exige auth. (403 com sessão não-admin.)

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat(admin): registra admin_billing_router no app"
```

---

## Task 4: Frontend — query keys + item de menu

**Files:**
- Modify: `fontend/lib/queryKeys.ts`
- Modify: `fontend/app/components/Sidebar.tsx`

- [ ] **Step 1: Adicionar chaves de query**

Em `fontend/lib/queryKeys.ts`, dentro do objeto `qk`, após a linha `vouchers: () => ["vouchers"] as const,`, inserir:

```typescript
  adminAssinaturasOverview: () => ["admin", "assinaturas", "overview"] as const,
  adminAssinaturas: (q: string, plano: string, page: number) =>
    ["admin", "assinaturas", "lista", q, plano, page] as const,
  adminAssinaturaDetalhe: (uid: string) => ["admin", "assinaturas", "detalhe", uid] as const,
```

- [ ] **Step 2: Adicionar item de menu adminOnly**

Em `fontend/app/components/Sidebar.tsx`, no array `navItems`, logo após a linha do item de vouchers (`{ href: "/admin/vouchers", label: "Vouchers", icon: "redeem", adminOnly: true },`), inserir:

```typescript
  { href: "/admin/assinaturas", label: "Assinaturas", icon: "paid", adminOnly: true },
```

- [ ] **Step 3: Verificar lint**

Run: `cd fontend && pnpm lint`
Expected: sem novos erros (warnings pré-existentes ok).

- [ ] **Step 4: Commit**

```bash
git add fontend/lib/queryKeys.ts fontend/app/components/Sidebar.tsx
git commit -m "feat(admin): query keys + item de menu Assinaturas"
```

---

## Task 5: Frontend — drawer de detalhe + ações

**Files:**
- Create: `fontend/app/admin/assinaturas/DetalheDrawer.tsx`

Criado antes da página porque a página o importa.

- [ ] **Step 1: Criar o componente do drawer**

Criar `fontend/app/admin/assinaturas/DetalheDrawer.tsx`:

```tsx
"use client";

import { useState } from "react";
import { apiJson, apiPost, ApiError } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";

type StripeSub = {
  id: string;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end: number | null;
  ultima_cobranca_centavos: number | null;
  payment_intent: string | null;
  moeda: string | null;
};

type Detalhe = {
  usuario: { uid: string; email: string; name: string; role: string; banned: boolean };
  assinatura_local: {
    status: string | null;
    stripe_subscription_id: string | null;
    stripe_customer_id: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    cancel_motivo: string | null;
    cancel_em: string | null;
  } | null;
  vouchers: { codigo: string; dias: number; pro_ate: string | null; resgatado_em: string | null }[];
  stripe_subscriptions: StripeSub[];
  stripe_erro: string | null;
};

function fmt(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function fmtCent(c: number | null | undefined, moeda = "brl"): string {
  if (c == null) return "—";
  return (c / 100).toLocaleString("pt-BR", { style: "currency", currency: (moeda || "brl").toUpperCase() });
}

export default function DetalheDrawer({ uid, onClose }: { uid: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [dias, setDias] = useState(365);
  const [modo, setModo] = useState<"fim_periodo" | "imediato" | "imediato_reembolso">("fim_periodo");
  const [motivo, setMotivo] = useState("");
  const [banir, setBanir] = useState(false);

  const { data, isPending, refetch } = useQuery<Detalhe>({
    queryKey: qk.adminAssinaturaDetalhe(uid),
    queryFn: () => apiJson<Detalhe>(`/api/admin/billing/usuarios/${uid}`),
  });

  async function invalidarTudo() {
    await Promise.all([
      refetch(),
      queryClient.invalidateQueries({ queryKey: ["admin", "assinaturas", "lista"] }),
      queryClient.invalidateQueries({ queryKey: qk.adminAssinaturasOverview() }),
    ]);
  }

  async function acao(fn: () => Promise<unknown>, ok: string) {
    setErro(null); setMsg(null); setBusy(true);
    try {
      await fn();
      setMsg(ok);
      await invalidarTudo();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha na operação.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <aside
        className="relative w-full max-w-md h-full bg-surface border-l border-border overflow-y-auto p-6 space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-semibold text-fg-strong">Detalhe da conta</h2>
          <button onClick={onClose} className="text-fg-muted hover:text-fg">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {isPending && <p className="text-sm text-fg-muted">Carregando…</p>}
        {data && (
          <>
            <section className="text-sm space-y-1">
              <div className="text-fg-strong font-medium">{data.usuario.email}</div>
              <div className="text-fg-muted">{data.usuario.name || "—"} · {data.usuario.role}</div>
              {data.usuario.banned && <div className="text-accent-danger text-xs">conta banida</div>}
            </section>

            <section className="text-xs text-fg-muted space-y-1 bg-page rounded-lg p-3">
              <div className="text-fg-strong text-sm font-medium mb-1">Assinatura (local)</div>
              <div>status: {data.assinatura_local?.status ?? "—"}</div>
              <div>vence: {fmt(data.assinatura_local?.current_period_end ?? null)}</div>
              <div>cancela no fim: {data.assinatura_local?.cancel_at_period_end ? "sim" : "não"}</div>
              {data.assinatura_local?.cancel_motivo && (
                <div>motivo cancel.: {data.assinatura_local.cancel_motivo}</div>
              )}
            </section>

            <section className="text-xs text-fg-muted space-y-2 bg-page rounded-lg p-3">
              <div className="text-fg-strong text-sm font-medium">Stripe (ao vivo)</div>
              {data.stripe_erro && <div className="text-accent-danger">erro: {data.stripe_erro}</div>}
              {data.stripe_subscriptions.length === 0 && !data.stripe_erro && <div>nenhuma assinatura no Stripe</div>}
              {data.stripe_subscriptions.map((s) => (
                <div key={s.id} className="border-t border-border pt-2">
                  <div>{s.id}</div>
                  <div>status: {s.status} · última cobrança: {fmtCent(s.ultima_cobranca_centavos, s.moeda || "brl")}</div>
                </div>
              ))}
            </section>

            {data.vouchers.length > 0 && (
              <section className="text-xs text-fg-muted space-y-1 bg-page rounded-lg p-3">
                <div className="text-fg-strong text-sm font-medium mb-1">Vouchers / Pro manual</div>
                {data.vouchers.map((v) => (
                  <div key={v.codigo}>{v.codigo} · {v.dias}d · até {fmt(v.pro_ate)}</div>
                ))}
              </section>
            )}

            {/* Ações */}
            <section className="space-y-3 border-t border-border pt-4">
              <div className="text-fg-strong text-sm font-medium">Conceder Pro manual</div>
              <div className="flex gap-2 items-end">
                <label className="text-xs text-fg-muted flex-1">
                  Dias
                  <input
                    type="number" min={1} max={3650} value={dias}
                    onChange={(e) => setDias(Math.max(1, Number(e.target.value) || 0))}
                    className="mt-1 w-full rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong"
                  />
                </label>
                <button
                  disabled={busy}
                  onClick={() => acao(() => apiPost(`/api/admin/billing/usuarios/${uid}/conceder`, { dias }), "Pro concedido.")}
                  className="bg-secondary hover:opacity-90 text-white px-4 py-2 rounded text-sm font-semibold disabled:opacity-40"
                >
                  Conceder
                </button>
              </div>
            </section>

            <section className="space-y-3 border-t border-border pt-4">
              <div className="text-fg-strong text-sm font-medium">Cancelar assinatura</div>
              <select
                value={modo}
                onChange={(e) => setModo(e.target.value as typeof modo)}
                className="w-full rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong"
              >
                <option value="fim_periodo">Fim do período (mantém acesso pago)</option>
                <option value="imediato">Imediato, sem reembolso</option>
                <option value="imediato_reembolso">Imediato, com reembolso</option>
              </select>
              <input
                type="text" placeholder="Motivo (ex: compartilhamento de contas)"
                value={motivo} onChange={(e) => setMotivo(e.target.value)}
                className="w-full rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong"
              />
              <label className="flex items-center gap-2 text-xs text-fg-muted">
                <input type="checkbox" checked={banir} onChange={(e) => setBanir(e.target.checked)} />
                Banir a conta (bloqueia login)
              </label>
              <button
                disabled={busy}
                onClick={() => {
                  const aviso = modo === "fim_periodo"
                    ? "Cancelar no fim do período?"
                    : modo === "imediato_reembolso"
                    ? "Cancelar AGORA e reembolsar a última cobrança?"
                    : "Cancelar AGORA, sem reembolso?";
                  if (!window.confirm(aviso + (banir ? "\nA conta também será banida." : ""))) return;
                  acao(
                    () => apiPost(`/api/admin/billing/usuarios/${uid}/cancelar`, { modo, motivo: motivo || null, banir }),
                    "Assinatura cancelada.",
                  );
                }}
                className="w-full bg-accent-danger hover:opacity-90 text-white px-4 py-2 rounded text-sm font-semibold disabled:opacity-40"
              >
                Cancelar assinatura
              </button>
            </section>

            <section className="border-t border-border pt-4">
              <button
                disabled={busy}
                onClick={() => acao(() => apiPost(`/api/admin/billing/usuarios/${uid}/sincronizar`, {}), "Sincronizado com o Stripe.")}
                className="w-full bg-page border border-border hover:border-primary text-fg px-4 py-2 rounded text-sm font-semibold disabled:opacity-40"
              >
                Sincronizar do Stripe
              </button>
            </section>

            {msg && <p className="text-sm text-accent-success">{msg}</p>}
            {erro && <p className="text-sm text-accent-danger">{erro}</p>}
          </>
        )}
      </aside>
    </div>
  );
}
```

- [ ] **Step 2: Verificar lint**

Run: `cd fontend && pnpm lint`
Expected: sem novos erros. Se acusar token de cor inexistente (`accent-danger`/`accent-success`), confirmar nome real em `app/globals.css` e ajustar (ver Task 6, Step 1 nota).

- [ ] **Step 3: Commit**

```bash
git add fontend/app/admin/assinaturas/DetalheDrawer.tsx
git commit -m "feat(admin): drawer de detalhe de assinatura + ações (conceder/cancelar/sincronizar)"
```

---

## Task 6: Frontend — página `/admin/assinaturas`

**Files:**
- Create: `fontend/app/admin/assinaturas/page.tsx`

- [ ] **Step 1: Conferir os tokens de cor usados**

Run: `cd fontend && grep -n "accent-danger\|accent-success\|on-primary\|bg-secondary" app/globals.css | head`
Expected: tokens existem. Se `accent-danger`/`accent-success` não existirem com esse nome, descobrir o nome real (ex.: `danger`, `error`, `success`) e substituir nos arquivos das Tasks 5 e 6 antes de prosseguir. (O `app/admin/vouchers/page.tsx` usa `text-accent-success` e `text-fg-*`, então provavelmente existem.)

- [ ] **Step 2: Criar a página**

Criar `fontend/app/admin/assinaturas/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { apiJson } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";
import DetalheDrawer from "./DetalheDrawer";

type Overview = {
  total_usuarios: number;
  ativos: number;
  atraso: number;
  cancelados: number;
  pro_voucher: number;
  admins: number;
  gratis: number;
  mrr_centavos: number;
  moeda: string;
  stripe_configurado: boolean;
};

type UsuarioRow = {
  uid: string;
  email: string;
  name: string | null;
  role: string;
  banned: boolean;
  plano: "admin" | "pro_stripe" | "pro_voucher" | "free";
  status: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  pro_ate: string | null;
};

type Lista = { total: number; page: number; page_size: number; usuarios: UsuarioRow[] };

const PLANO_LABEL: Record<UsuarioRow["plano"], { txt: string; cls: string }> = {
  admin: { txt: "Admin", cls: "bg-secondary/20 text-secondary" },
  pro_stripe: { txt: "Pro (Stripe)", cls: "bg-primary/20 text-primary" },
  pro_voucher: { txt: "Pro (Voucher)", cls: "bg-accent-success/20 text-accent-success" },
  free: { txt: "Grátis", cls: "bg-fg-faint/10 text-fg-muted" },
};

function fmtCent(c: number, moeda = "brl"): string {
  return (c / 100).toLocaleString("pt-BR", { style: "currency", currency: (moeda || "brl").toUpperCase() });
}
function fmtData(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("pt-BR", { dateStyle: "short" });
}

function Card({ label, valor, cor }: { label: string; valor: string; cor?: string }) {
  return (
    <div className="bg-surface border border-border rounded-xl p-4">
      <div className="text-xs text-fg-muted">{label}</div>
      <div className={`text-2xl font-bold ${cor || "text-fg-strong"}`}>{valor}</div>
    </div>
  );
}

export default function AssinaturasAdminPage() {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [q, setQ] = useState("");
  const [busca, setBusca] = useState("");
  const [plano, setPlano] = useState("");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    authClient.getSession()
      .then((res) => setIsAdmin(((res?.data?.user as { role?: string } | undefined)?.role) === "admin"))
      .catch(() => setIsAdmin(false));
  }, []);

  // Debounce simples da busca.
  useEffect(() => {
    const t = setTimeout(() => { setBusca(q); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [q]);

  const overview = useQuery<Overview>({
    queryKey: qk.adminAssinaturasOverview(),
    queryFn: () => apiJson<Overview>("/api/admin/billing/overview"),
    enabled: isAdmin === true,
  });

  const lista = useQuery<Lista>({
    queryKey: qk.adminAssinaturas(busca, plano, page),
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: "30" });
      if (busca) params.set("q", busca);
      if (plano) params.set("plano", plano);
      return apiJson<Lista>(`/api/admin/billing/usuarios?${params.toString()}`);
    },
    enabled: isAdmin === true,
  });

  if (isAdmin === null) return <div className="p-8 text-fg-muted">Carregando…</div>;
  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-page text-fg flex items-center justify-center px-6">
        <div className="max-w-md text-center space-y-3">
          <span className="material-symbols-outlined text-fg-faint text-5xl">lock</span>
          <h1 className="text-xl font-semibold">Área restrita</h1>
          <p className="text-sm text-fg-faint">A gestão de assinaturas é exclusiva para administradores.</p>
          <Link href="/painel" className="inline-block text-sm bg-primary hover:bg-primary-600 text-on-primary px-4 py-2 rounded font-semibold">
            Voltar ao início
          </Link>
        </div>
      </div>
    );
  }

  const totalPaginas = lista.data ? Math.max(1, Math.ceil(lista.data.total / lista.data.page_size)) : 1;
  const o = overview.data;

  return (
    <>
      <header className="hidden md:flex sticky top-0 z-30 bg-page/80 backdrop-blur-md border-b border-border px-8 py-4 items-center gap-2">
        <span className="material-symbols-outlined text-primary">paid</span>
        <h1 className="text-2xl font-bold text-fg-strong">Assinaturas</h1>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full space-y-8">
        {/* Métricas */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card label="Pro ativos" valor={String(o?.ativos ?? "…")} cor="text-primary" />
          <Card label="MRR" valor={o ? fmtCent(o.mrr_centavos, o.moeda) : "…"} cor="text-accent-success" />
          <Card label="Em atraso" valor={String(o?.atraso ?? "…")} />
          <Card label="Grátis" valor={String(o?.gratis ?? "…")} />
        </section>
        {o && !o.stripe_configurado && (
          <p className="text-xs text-accent-danger">Stripe não configurado — cancelar/sincronizar e MRR ao vivo indisponíveis.</p>
        )}

        {/* Filtros */}
        <section className="flex flex-col sm:flex-row gap-3">
          <input
            type="text" placeholder="Buscar por email ou nome…"
            value={q} onChange={(e) => setQ(e.target.value)}
            className="flex-1 rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong"
          />
          <select
            value={plano} onChange={(e) => { setPlano(e.target.value); setPage(1); }}
            className="rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong"
          >
            <option value="">Todos os planos</option>
            <option value="pro_stripe">Pro (Stripe)</option>
            <option value="pro_voucher">Pro (Voucher)</option>
            <option value="free">Grátis</option>
            <option value="admin">Admin</option>
          </select>
        </section>

        {/* Tabela */}
        <section className="bg-surface border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-page text-fg-muted text-xs">
              <tr>
                <th className="text-left px-4 py-3">Email</th>
                <th className="text-left px-4 py-3 hidden md:table-cell">Plano</th>
                <th className="text-left px-4 py-3 hidden md:table-cell">Status</th>
                <th className="text-left px-4 py-3 hidden lg:table-cell">Vence</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {lista.isPending && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-fg-muted">Carregando…</td></tr>
              )}
              {lista.data?.usuarios.map((u) => {
                const pl = PLANO_LABEL[u.plano];
                const vence = u.plano === "pro_voucher" ? u.pro_ate : u.current_period_end;
                return (
                  <tr key={u.uid} className="border-t border-border hover:bg-page/50">
                    <td className="px-4 py-3">
                      <div className="text-fg-strong">{u.email}</div>
                      <div className="text-xs text-fg-faint">{u.name || "—"}{u.banned ? " · banido" : ""}</div>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className={`text-xs px-2 py-1 rounded ${pl.cls}`}>{pl.txt}</span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell text-fg-muted">{u.status ?? "—"}</td>
                    <td className="px-4 py-3 hidden lg:table-cell text-fg-muted">{fmtData(vence)}</td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => setSel(u.uid)} className="text-primary hover:underline text-xs font-semibold">
                        Ver
                      </button>
                    </td>
                  </tr>
                );
              })}
              {lista.data && lista.data.usuarios.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-fg-muted">Nenhum usuário.</td></tr>
              )}
            </tbody>
          </table>
        </section>

        {/* Paginação */}
        <div className="flex items-center justify-between text-sm text-fg-muted">
          <span>{lista.data?.total ?? 0} usuários</span>
          <div className="flex items-center gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 rounded border border-border disabled:opacity-40">Anterior</button>
            <span>{page}/{totalPaginas}</span>
            <button disabled={page >= totalPaginas} onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 rounded border border-border disabled:opacity-40">Próxima</button>
          </div>
        </div>
      </main>

      {sel && <DetalheDrawer uid={sel} onClose={() => setSel(null)} />}
    </>
  );
}
```

- [ ] **Step 3: Verificar lint**

Run: `cd fontend && pnpm lint`
Expected: sem novos erros.

- [ ] **Step 4: Smoke manual no dev**

Com `./dev.sh up:d` rodando e logado como admin, abrir `http://localhost:3000/admin/assinaturas`.
Expected: cards de métrica carregam, tabela lista usuários, busca filtra, "Ver" abre o drawer. (Ações que chamam Stripe podem falhar em dev se as chaves de teste não estiverem no `.env` — conceder Pro funciona sem Stripe.)

- [ ] **Step 5: Commit**

```bash
git add fontend/app/admin/assinaturas/page.tsx
git commit -m "feat(admin): página /admin/assinaturas (overview, tabela, busca, filtro)"
```

---

## Task 7: Deploy (workflow obrigatório do CLAUDE.md)

**Files:** nenhum — etapa de release.

- [ ] **Step 1: Push**

Run: `git push`
Expected: `main` atualizado no `origin`.

- [ ] **Step 2: Deploy em produção**

Run: `./build.sh`
Expected: build + push de imagens + `db_prepare` (roda `alembic upgrade head`, aplica a migração das 3 colunas) + `docker stack deploy`. O backend valida o schema no startup; se a migração não aplicar, o container falha visível.

- [ ] **Step 3: Smoke em produção (admin)**

Logado como admin em `https://studia.witdev.com.br/admin/assinaturas`:
Expected: overview mostra contadores reais; a conta que já assinou (do print) aparece como Pro (Stripe) com renovação em 15/07/2026; "Sincronizar" reconcilia; "Conceder Pro" funciona numa conta grátis de teste.

- [ ] **Step 4: Worktree limpo**

Run: `git status`
Expected: `nothing to commit, working tree clean`.

---

## Self-Review (preenchido)

**Cobertura do spec:**
- Overview (contadores + MRR) → Task 2 `/overview`, Task 6 cards. ✅
- Lista de todos os usuários, busca por email, filtro de plano → Task 2 `/usuarios`, Task 6. ✅
- Detalhe local + Stripe ao vivo → Task 2 `/usuarios/{uid}`, Task 5 drawer. ✅
- Conceder Pro manual (via Voucher) → Task 2 `/conceder`. ✅
- Cancelar 3 modos + reembolso + motivo + banir → Task 1 (colunas) + Task 2 `/cancelar` + Task 5 UI. ✅
- Sincronizar do Stripe → Task 2 `/sincronizar`. ✅
- Guard admin (backend require_admin + frontend) → Tasks 2/3/5/6. ✅
- Migração das colunas → Task 1. ✅
- Item de menu adminOnly → Task 4. ✅
- Deploy (commit/push/build.sh/worktree limpo) → Task 7. ✅

**Placeholders:** nenhum — todo código está completo.

**Consistência de tipos/nomes:** rotas `/api/admin/billing/*` idênticas entre backend (Task 2) e chamadas do frontend (Tasks 5/6); `qk.adminAssinaturas*` definidas na Task 4 e usadas nas Tasks 5/6; `_upsert_sub` importado de `billing_router` (já existe, módulo-level); campos `cancel_motivo/cancel_admin_uid/cancel_em` definidos na Task 1 e usados na Task 2; modos de cancelamento (`fim_periodo|imediato|imediato_reembolso`) iguais no backend e no select da UI.

**Risco conhecido:** nomes de tokens de cor (`accent-danger`/`accent-success`) — mitigado pelo Step 1 da Task 6 (verifica em `globals.css` antes de prosseguir).
```
