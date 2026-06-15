# Painel Admin de Assinaturas — Design

**Data:** 2026-06-15
**Status:** Aprovado (aguardando review do spec)

## Objetivo

Dar ao admin uma tela para **ver e gerir** as assinaturas Stripe do studIA: visão
geral (métricas + MRR), lista de todos os usuários com o plano de cada um, e ações
de gestão — conceder Pro manual, cancelar (inclusive forçado por violação, com ou
sem reembolso, opcionalmente banindo a conta) e sincronizar do Stripe.

Motivação: o checkout Stripe já funciona em produção, mas não há nenhuma interface
para o admin acompanhar quem assinou, corrigir estados (webhook perdido) ou agir
sobre violações (compartilhamento de contas).

## Contexto existente (reuso, não reinventar)

- `backend/stripe_client.py` — `stripe_request()` (REST async, sem SDK), `StripeError`,
  `stripe_configurado()`, `STRIPE_PRICE_ID`, `PRECO_LABEL`.
- `backend/billing_router.py` — `_upsert_sub()` (cria/atualiza `Assinatura` a partir de
  um objeto subscription do Stripe). Reaproveitado por cancelar/sincronizar.
- `backend/entitlements.py` — `assinatura_ativa()`, `voucher_pro_ativo()`,
  `acesso_pro_ativo()`. **Conceder Pro manual entra de graça aqui via Voucher.**
- `backend/models.py` — `Assinatura` (status, current_period_end, cancel_at_period_end,
  stripe_customer_id/subscription_id) e `Voucher` (codigo, dias, criado_por_uid,
  resgatado_por_uid, resgatado_em, pro_ate). O Voucher já é "admin concede PRO sem
  pagamento"; só falta router/UI.
- `backend/auth.py` — `require_admin`, `CurrentUser`, e o JOIN na tabela `user` do
  Better Auth (`_carregar_usuario`) que serve de molde para listar todos os usuários.
- Frontend: padrão de página admin com guard (`fontend/app/jobs/page.tsx`), React Query,
  e item de menu `adminOnly` em `fontend/app/components/Sidebar.tsx`.

## Arquitetura

### Backend — `backend/admin_billing_router.py` (novo)

`APIRouter(prefix="/api/admin/billing")`, **todo endpoint sob `Depends(require_admin)`**.
Registrado em `main.py` junto aos demais `include_router`.

Fonte de dados: **DB local rápido + Stripe ao vivo sob demanda** (só no detalhe de um
usuário e nas ações).

| Endpoint | Método | Função |
|---|---|---|
| `/overview` | GET | Contadores por status (active, trialing, past_due, canceled, incomplete), total de usuários, total grátis, e **MRR** = (ativos+trialing) × valor unitário. |
| `/usuarios` | GET | Lista todos os usuários (JOIN `user` ⨝ `assinaturas` ⨝ `vouchers`), filtros `q` (email/nome), `plano`, paginação `page`/`page_size`. Cada linha traz plano resolvido + validade. |
| `/usuarios/{uid}` | GET | Detalhe: dados locais + **Stripe ao vivo** (customer + subscriptions reais). Sinaliza divergência DB↔Stripe. |
| `/usuarios/{uid}/conceder` | POST | Conceder Pro manual: cria Voucher auto-resgatado na conta. Body `{dias?: int=365}`. |
| `/usuarios/{uid}/cancelar` | POST | Cancelar assinatura (3 modos, ver abaixo). Body `{modo, motivo?, banir?}`. |
| `/usuarios/{uid}/sincronizar` | POST | Re-busca subscriptions do customer no Stripe e faz `_upsert_sub` (conserta webhook perdido). |

**Valor unitário p/ MRR:** `GET /prices/{STRIPE_PRICE_ID}` no Stripe (`unit_amount`),
cacheado em variável de módulo (TTL simples ou cache permanente por processo).
Fallback: parse numérico de `PRECO_LABEL` ("R$ 29,90/mês" → 2990 centavos).

#### Conceder Pro manual (via Voucher)

Reaproveita o modelo `Voucher` e a regra `voucher_pro_ativo()`:
- Cria `Voucher` com `codigo` gerado, `dias` (default 365), `criado_por_uid` = admin,
  `resgatado_por_uid` = uid alvo, `resgatado_em` = now,
  `pro_ate` = max(`pro_ate` vigente da conta, now) + `dias`.
- Nenhuma mudança em `entitlements`: `acesso_pro_ativo()` já honra voucher vigente.
- Vantagem sobre criar `Assinatura` "fake": não colide com o `_upsert_sub` do webhook
  (que procura placeholder do mesmo `usuario_uid`) nem polui métricas de Stripe.

#### Cancelar — 3 modos

| Modo | Ação no Stripe | Efeito |
|---|---|---|
| `fim_periodo` (padrão) | `POST /subscriptions/{id}` com `cancel_at_period_end=true` | Mantém acesso já pago até o fim do ciclo. |
| `imediato` | `DELETE /subscriptions/{id}` | Corta acesso agora, sem reembolso. |
| `imediato_reembolso` | `DELETE /subscriptions/{id}` + `POST /refunds` | Corta agora e devolve a última cobrança. |

- Reembolso: a partir da subscription, pega `latest_invoice` → `payment_intent` →
  `POST /refunds {payment_intent}` (valor total da última cobrança). O endpoint de
  detalhe expõe o valor que será reembolsado para confirmação na UI.
- Após qualquer modo, chama `_upsert_sub` com a subscription atualizada (ou marca
  `canceled` local no imediato) para refletir o estado no DB.
- **Campo `motivo`** (texto, ex: "compartilhamento de contas") gravado na `Assinatura`
  junto de `cancel_admin_uid` e `cancel_em` (novas colunas via `migrate.py`).
- **`banir` (bool, opcional, default false):** quando true, `UPDATE "user" SET banned=true`
  na tabela Better Auth (impede novo handoff/login — ver `auth.require_user`).

### Frontend — `fontend/app/admin/assinaturas/page.tsx` (novo)

- Guard admin idêntico ao `/jobs` (se `!isAdmin` → "Área restrita").
- Item `adminOnly` em `Sidebar.tsx` (ex.: "Assinaturas").
- **Topo:** cards de métrica — Ativos · Cancelados/Atraso · Grátis · MRR (R$).
- **Busca** por email/nome + filtro de plano.
- **Tabela** de usuários: email · nome · badge de plano (Admin / Pro-Stripe / Pro-Voucher /
  Grátis) · status · validade · botão "Ver".
- **Drawer de detalhe** (dados Stripe ao vivo + ações):
  - **Conceder Pro:** campo `dias` → `POST /conceder`.
  - **Cancelar:** select de modo (fim do período / imediato / imediato+reembolso),
    campo `motivo`, checkbox `banir conta` (off por padrão). Mostra valor do reembolso
    quando aplicável. → `POST /cancelar`.
  - **Sincronizar:** botão → `POST /sincronizar`.
  - Tudo com React Query `useMutation` + invalidação das queries de overview/usuários/detalhe.

### Migração (`backend/migrate.py`)

Adiciona à tabela `assinaturas` (auto-detect de colunas faltantes, padrão do projeto):
- `cancel_motivo` TEXT NULL
- `cancel_admin_uid` VARCHAR(64) NULL
- `cancel_em` TIMESTAMPTZ NULL

## Fluxo de dados

1. Admin abre `/admin/assinaturas` → React Query busca `/overview` + `/usuarios` (DB local, rápido).
2. Clica "Ver" → `/usuarios/{uid}` busca local + Stripe ao vivo (estado real).
3. Ação (conceder/cancelar/sincronizar) → POST → backend chama Stripe quando preciso →
   `_upsert_sub`/voucher → invalida queries → UI reflete.

## Tratamento de erros

- Stripe fora/sem chave: ações que dependem do Stripe (cancelar/sincronizar/MRR live)
  retornam 503/erro amigável; lista local e conceder-voucher continuam funcionando.
- `StripeError` → HTTP 502 com mensagem (padrão já usado no `billing_router`).
- Refund sem `payment_intent` (ex.: invoice não paga) → 400 explicando que não há
  cobrança a reembolsar; cancelamento ainda procede se o admin confirmar.
- Banir conta: `UPDATE` idempotente; se uid não existe na tabela `user`, 404.
- Todas as mutações: confirmação explícita na UI para ações destrutivas (cancelar imediato,
  reembolso, banir).

## Testes / verificação

- Sem suíte de testes no projeto. Verificação manual em produção após deploy:
  - `/overview` retorna contadores coerentes com o DB.
  - Conceder Pro a uma conta grátis → vira Pro (badge + `acesso_pro_ativo`).
  - Sincronizar uma conta com webhook perdido reconcilia o status.
  - Cancelar (fim do período) → `cancel_at_period_end=true` refletido.
  - (Em ambiente de teste Stripe) cancelar imediato + reembolso → refund criado.
- Smoke do guard admin: usuário não-admin recebe 403 nos endpoints e "Área restrita" na página.

## Fora de escopo (YAGNI)

- Histórico/auditoria completo de ações admin (só gravamos motivo/admin/data no cancelamento).
- Geração/gestão de vouchers em lote com UI própria (conceder Pro usa voucher por baixo,
  mas sem tela de cupons).
- Edição de preço/plano, upgrades/downgrades, múltiplos planos.
- Exportação CSV / relatórios financeiros avançados.
