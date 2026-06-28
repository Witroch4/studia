# Celebração de Meta Diária (15 questões / PRO) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando um usuário ilimitado (PRO/admin) resolve a 15ª questão distinta do dia, disparar confetes + toast de "meta diária batida".

**Architecture:** O backend é a fonte da verdade: o endpoint `POST /api/q/{id}/responder` passa a devolver `meta_diaria.batida_agora`, que só é `true` na transição exata 14→15 para conta ilimitada (idempotência e fuso já existentes garantem disparo único). O frontend reage a esse flag chamando uma nova função de confete e um toast `sonner`.

**Tech Stack:** Backend FastAPI + SQLAlchemy async (pytest + aiosqlite/asyncpg). Frontend Next.js 16 + React 19 + TanStack Query + `canvas-confetti` + `sonner` (novo).

## Global Constraints

- Idioma da UI/cópia: **Português BR**.
- Meta diária = **15** questões; exclusiva de conta **ilimitada** (admin OU `acesso_pro_ativo`). Plano grátis trava em `LIMITE_DIARIO_GRATIS = 10` e nunca dispara.
- Confete da meta deve ser **visualmente distinto** do `celebrarPro()` (assinatura), mantendo a paleta cyan `#06b6d4` / violeta `#8b5cf6`.
- Funções de confete são **SSR-safe** (`if (typeof window === "undefined") return;`).
- Não adicionar contador "x/15" na UI (fora de escopo).
- Backend sem linter; frontend usa `pnpm lint` (ESLint Next+TS).

---

### Task 1: Backend — flag `meta_diaria` no endpoint `/responder`

**Files:**
- Modify: `backend/entitlements.py` (adicionar constante + `meta_diaria_status()` após `contagem_questoes_hoje`, ~linha 90)
- Modify: `backend/q_router.py:28` (import) e os dois `return` do endpoint `responder` (idempotente ~1287-1293 e novo ~1331-1336)
- Test: `backend/tests/test_q_meta_diaria.py` (criar)

**Interfaces:**
- Consumes: `contagem_questoes_hoje(db, uid) -> int`, `acesso_pro_ativo(db, uid) -> bool`, `user.is_admin: bool` (já existem em `entitlements.py` / `auth.py`).
- Produces:
  - `META_DIARIA_PRO = 15` (int, em `entitlements.py`)
  - `async meta_diaria_status(db, user, *, era_nova: bool) -> dict` → `{"meta": int, "total": int, "batida_agora": bool}`
  - Endpoint `/responder` passa a incluir a chave `"meta_diaria"` (esse dict) em **ambos** os caminhos de retorno (questão nova e idempotente).

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/tests/test_q_meta_diaria.py`:

```python
"""Meta diária: conta ilimitada (PRO/admin) que bate 15 questões distintas no
dia recebe meta_diaria.batida_agora=True UMA vez (transição 14→15). Grátis
nunca dispara (trava em 10)."""

from datetime import datetime, timedelta, timezone

import pytest

from auth import CurrentUser
from models import Assinatura, CadernoQuestoes, Questao

pytestmark = pytest.mark.asyncio

USER_A = CurrentUser(id="user-A", email="user-A@studia.test", name="user-A", role="user", banned=False)


async def _seed_caderno(db_session, *, caderno_id: int, owner_uid: str, n: int) -> list[int]:
    """Cria um caderno + n questões distintas (gabarito A). Retorna os ids."""
    base = caderno_id * 1000
    ids = list(range(base, base + n))
    db_session.add(CadernoQuestoes(id=caderno_id, nome="Meta", owner_uid=owner_uid, question_ids=ids, total=n))
    for qid in ids:
        db_session.add(Questao(
            id=qid, id_externo=qid, tipo="MULTIPLA_ESCOLHA",
            enunciado_html="<p>Q</p>", gabarito="A", status="ATIVA",
        ))
    await db_session.commit()
    return ids


async def test_ilimitado_dispara_na_15a_e_so_nela(client, db_session):
    # usuário default do conftest = admin-1 (ilimitado).
    ids = await _seed_caderno(db_session, caderno_id=500, owner_uid="admin-1", n=16)
    for i, qid in enumerate(ids, start=1):
        r = await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 500})
        assert r.status_code == 200, r.text
        md = r.json()["meta_diaria"]
        assert md["meta"] == 15
        assert md["total"] == i
        assert md["batida_agora"] is (i == 15)  # true só na 15ª; 14 e 16 = false


async def test_repetir_a_15a_nao_redispara(client, db_session):
    ids = await _seed_caderno(db_session, caderno_id=501, owner_uid="admin-1", n=15)
    for qid in ids:
        await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 501})
    # repetir a 15ª questão (caminho idempotente) NÃO pode redisparar.
    r = await client.post(f"/api/q/{ids[14]}/responder", json={"resposta": "B", "caderno_id": 501})
    body = r.json()
    assert body["ja_resolvida"] is True
    assert body["meta_diaria"]["batida_agora"] is False
    assert body["meta_diaria"]["total"] == 15


async def test_gratis_nunca_dispara(client, db_session, auth_state):
    auth_state["user"] = USER_A  # plano grátis
    ids = await _seed_caderno(db_session, caderno_id=502, owner_uid="user-A", n=11)
    for qid in ids[:10]:
        r = await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 502})
        assert r.status_code == 200
        assert r.json()["meta_diaria"]["batida_agora"] is False
    # 11ª questão nova → 402 (limite grátis); nunca chega a 15.
    r11 = await client.post(f"/api/q/{ids[10]}/responder", json={"resposta": "A", "caderno_id": 502})
    assert r11.status_code == 402


async def test_assinante_dispara_meta(client, db_session, auth_state):
    auth_state["user"] = USER_A
    db_session.add(Assinatura(
        usuario_uid="user-A", status="active",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    ids = await _seed_caderno(db_session, caderno_id=503, owner_uid="user-A", n=15)
    last = None
    for qid in ids:
        last = await client.post(f"/api/q/{qid}/responder", json={"resposta": "A", "caderno_id": 503})
    assert last.json()["meta_diaria"]["batida_agora"] is True
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd backend && python -m pytest tests/test_q_meta_diaria.py -v`
Expected: FAIL com `KeyError: 'meta_diaria'` (a chave ainda não existe na resposta).

- [ ] **Step 3: Adicionar constante + helper em `entitlements.py`**

Adicionar após a função `contagem_questoes_hoje` (após a linha 90). A constante `META_DIARIA_PRO` pode ficar junto de `LIMITE_DIARIO_GRATIS` (linha 20) ou logo acima do helper — colocar logo acima do helper:

```python
META_DIARIA_PRO = 15  # questões/dia que disparam a celebração de meta (só conta ilimitada)


async def meta_diaria_status(db: AsyncSession, user, *, era_nova: bool) -> dict:
    """Status da meta diária p/ a celebração no front.

    `batida_agora` só é True quando: a conta é ilimitada (admin OU PRO ativo),
    ESTA resposta criou uma resolução nova (`era_nova`) e o total de questões
    DISTINTAS de hoje bateu exatamente META_DIARIA_PRO — i.e. a transição
    14→15. Dispara uma única vez por dia; recarregar/repetir não re-dispara
    (o caminho idempotente passa era_nova=False) e o grátis nunca chega lá.
    """
    total = await contagem_questoes_hoje(db, user.id)
    ilimitado = user.is_admin or await acesso_pro_ativo(db, user.id)
    return {
        "meta": META_DIARIA_PRO,
        "total": total,
        "batida_agora": era_nova and ilimitado and total == META_DIARIA_PRO,
    }
```

- [ ] **Step 4: Importar e usar no endpoint `responder`**

Em `backend/q_router.py:28`, acrescentar `meta_diaria_status` ao import:

```python
from entitlements import acesso_pro_ativo, garantir_pode_resolver, meta_diaria_status, resumo_limite
```

No retorno do **caminho idempotente** (dentro de `if existente is not None:`, ~linha 1287), acrescentar a chave `meta_diaria` (era_nova=False):

```python
        return {
            "acertou": existente.acertou,
            "gabarito": q.gabarito,
            "stats": {"resolvidas": total, "acertos": acertos, "erros": total - acertos},
            "limite": await resumo_limite(db, user),
            "meta_diaria": await meta_diaria_status(db, user, era_nova=False),
            "ja_resolvida": True,
        }
```

No retorno do **caminho de resolução nova** (final do endpoint, ~linha 1331, após o `db.commit()`), acrescentar a chave `meta_diaria` (era_nova=True):

```python
    return {
        "acertou": acertou,
        "gabarito": q.gabarito,
        "stats": {"resolvidas": total, "acertos": acertos, "erros": erros},
        "limite": await resumo_limite(db, user),
        "meta_diaria": await meta_diaria_status(db, user, era_nova=True),
    }
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `cd backend && python -m pytest tests/test_q_meta_diaria.py tests/test_q_responder_idempotente.py -v`
Expected: PASS (4 testes novos + 2 de idempotência, sem regressão).

- [ ] **Step 6: Commit**

```bash
git add backend/entitlements.py backend/q_router.py backend/tests/test_q_meta_diaria.py
git commit -m "feat(q): backend devolve meta_diaria.batida_agora (15 questões/dia PRO)

Endpoint /responder passa a calcular o marco diário (questões distintas) e
sinaliza batida_agora só na transição 14→15 p/ conta ilimitada. Caminho
idempotente e plano grátis nunca disparam. Testes cobrem 14/15/16, repetição
e grátis."
```

---

### Task 2: Frontend — instalar `sonner` + montar `<Toaster />` no layout raiz

**Files:**
- Modify: `fontend/package.json` (via `pnpm add sonner`)
- Modify: `fontend/app/layout.tsx` (import + `<Toaster />` dentro do `<body>`)

**Interfaces:**
- Produces: `<Toaster />` global montado → habilita `toast()` de `sonner` em qualquer client component (consumido pela Task 4).

- [ ] **Step 1: Instalar a dependência**

Run: `cd fontend && pnpm add sonner`
Expected: `sonner` aparece em `package.json` (dependencies) e `pnpm-lock.yaml` atualizado.

- [ ] **Step 2: Importar e montar o `<Toaster />` no layout**

Em `fontend/app/layout.tsx`, adicionar o import junto aos demais (após a linha 7):

```typescript
import { Toaster } from "sonner";
```

E montar o `<Toaster />` logo após `</ThemeProvider>`, ainda dentro do `<body>` (após a linha 90). Tema escuro padrão do app + cores ricas + topo central:

```tsx
        <ThemeProvider>
          <QueryProvider>
            <AppShell>{children}</AppShell>
          </QueryProvider>
        </ThemeProvider>
        <Toaster richColors position="top-center" theme="dark" />
```

- [ ] **Step 3: Verificar lint/build**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos (warnings pré-existentes do projeto são aceitáveis).

- [ ] **Step 4: Commit**

```bash
git add fontend/package.json fontend/pnpm-lock.yaml fontend/app/layout.tsx
git commit -m "feat(ui): adiciona sonner + <Toaster /> global no layout raiz"
```

---

### Task 3: Frontend — função de confete `celebrarMetaDiaria()`

**Files:**
- Modify: `fontend/lib/confetti.ts` (adicionar export `celebrarMetaDiaria`)

**Interfaces:**
- Consumes: `canvas-confetti` (já instalado), padrão SSR-safe da `celebrarPro()` existente.
- Produces: `export function celebrarMetaDiaria(): void` — consumida pela Task 4.

- [ ] **Step 1: Adicionar a função em `fontend/lib/confetti.ts`**

Acrescentar ao final do arquivo (após `celebrarPro`). Efeito distinto: "chuva" contínua caindo do topo por ~2.5s (vs. o leque lateral do PRO), mesma paleta da marca:

```typescript
/**
 * Comemoração de "meta diária batida" (15 questões/dia, PRO): chuva contínua de
 * confetes caindo do topo por ~2.5s — efeito distinto do leque lateral do
 * celebrarPro() (assinatura). Seguro p/ SSR (canvas-confetti depende de window).
 */
export function celebrarMetaDiaria() {
  if (typeof window === "undefined") return;

  const cores = ["#06b6d4", "#8b5cf6", "#22d3ee", "#a78bfa", "#ffffff"];
  const fim = Date.now() + 2500;

  (function chuva() {
    confetti({
      particleCount: 4,
      startVelocity: 0,
      ticks: 200,
      gravity: 0.6,
      spread: 80,
      origin: { x: Math.random(), y: -0.1 },
      colors: cores,
      zIndex: 9999,
    });
    if (Date.now() < fim) requestAnimationFrame(chuva);
  })();
}
```

> Nota: `Math.random()` aqui roda só no browser (a função é client-only), então não há problema de hidratação/SSR.

- [ ] **Step 2: Verificar lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
git add fontend/lib/confetti.ts
git commit -m "feat(ui): celebrarMetaDiaria() — chuva de confetes p/ meta diária"
```

---

### Task 4: Frontend — disparar confete + toast no `onSuccess` de responder

**Files:**
- Modify: `fontend/app/q/caderno/[id]/page.tsx` (imports ~linha 15; tipo de retorno da mutation ~245; `onSuccess` ~247-256)

**Interfaces:**
- Consumes: `celebrarMetaDiaria()` (Task 3), `toast` de `sonner` (Task 2), `data.meta_diaria` do endpoint (Task 1).
- Produces: comportamento final — ao cruzar 14→15, confete + toast de parabéns.

- [ ] **Step 1: Adicionar os imports**

Em `fontend/app/q/caderno/[id]/page.tsx`, após a linha 17 (`import { useSession } ...`):

```typescript
import { toast } from "sonner";
import { celebrarMetaDiaria } from "@/lib/confetti";
```

- [ ] **Step 2: Estender o tipo de retorno da mutation**

Substituir a linha 245:

```typescript
      return r.json() as Promise<{ acertou: boolean; limite?: typeof limiteQuery }>;
```

por:

```typescript
      return r.json() as Promise<{
        acertou: boolean;
        limite?: typeof limiteQuery;
        meta_diaria?: { meta: number; total: number; batida_agora: boolean };
      }>;
```

- [ ] **Step 3: Disparar a celebração no `onSuccess`**

No início do callback `onSuccess: (data) => {` (linha 247), logo após `setRespostaState(...)` e o `if (data.limite) ...` (após a linha 249), adicionar:

```typescript
      if (data.meta_diaria?.batida_agora) {
        celebrarMetaDiaria();
        toast.success("🎯 Meta diária batida!", {
          description: "Você resolveu 15 questões hoje. Continue assim! 🔥",
        });
      }
```

- [ ] **Step 4: Verificar lint/build**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos.

- [ ] **Step 5: Smoke test manual (dev)**

Subir o dev (`./dev.sh up:d`) logado como admin (ilimitado), abrir um caderno e resolver 15 questões distintas no dia. Na 15ª: confete em chuva + toast "🎯 Meta diária batida!". Recarregar a página e re-responder não re-dispara.

> Atenção ao fuso: `contagem_questoes_hoje` corta à meia-noite em `America/Fortaleza` e conta DISTINCT do dia inteiro — resoluções anteriores de hoje contam. Se já houver resoluções hoje, ajuste o alvo (faltam `15 - total_atual`).

- [ ] **Step 6: Commit**

```bash
git add fontend/app/q/caderno/[id]/page.tsx
git commit -m "feat(q): confete + toast ao bater meta diária de 15 questões (PRO)"
```

---

## Encerramento (após as 4 tasks)

Seguir o **Workflow OBRIGATÓRIO** do `CLAUDE.md`:
1. Garantir que tudo está commitado (4 commits acima).
2. `git push` para a branch ativa.
3. Deploy em produção: `./build.sh`.
4. `git status` limpo ao final.

## Self-Review (preenchido pelo autor do plano)

- **Cobertura do spec:** público só-PRO (Task 1, `ilimitado`); backend detecta marco (Task 1); `sonner` (Task 2); confete distinto (Task 3); gancho no único ponto de resposta (Task 4); fora-de-escopo respeitado (sem contador x/15); testes backend cobrem 14/15/16, repetição e grátis (Task 1). ✅
- **Placeholders:** nenhum TBD/TODO; todo passo de código tem o código. ✅
- **Consistência de tipos:** `meta_diaria_status(... era_nova=bool) -> {meta,total,batida_agora}` usado igual no endpoint e consumido com o mesmo shape no tipo do frontend (`{ meta: number; total: number; batida_agora: boolean }`). ✅
