# Assinatura studIA estilo ChatGPT — Design

**Data:** 2026-06-15
**Status:** Aprovado (aguardando revisão do spec)

## Objetivo

Elevar o sistema de assinatura do studIA ao nível do ChatGPT: página `/assinar`
com comparação de planos persuasiva, **checkout transparente na própria página**
(sem redirect), plano anual, portal de autoatendimento e seção de billing na
`/conta`. Hoje a `/assinar` mostra apenas um card do Pro e redireciona para a
página hospedada do Stripe.

## Estado atual (resumo)

- **Backend** — [billing_router.py](../../../backend/billing_router.py):
  - `POST /api/billing/checkout` ([billing_router.py:95](../../../backend/billing_router.py#L95)) cria uma Checkout Session **hospedada** (`mode=subscription`) e devolve `{url}` para redirect.
  - `POST /api/billing/webhook` ([billing_router.py:176](../../../backend/billing_router.py#L176)) trata `checkout.session.completed` e `customer.subscription.*` → `_upsert_sub`.
  - `GET /api/billing/status` ([billing_router.py:51](../../../backend/billing_router.py#L51)) devolve plano, assinatura, limite, `publishable_key`, `preco_label`.
- **Stripe client** — [stripe_client.py](../../../backend/stripe_client.py): cliente REST fino (httpx, form-encoded), **sem header `Stripe-Version`** (usa a versão default da conta). `STRIPE_PRICE_ID` único (mensal).
- **Frontend** — [fontend/app/assinar/page.tsx](../../../fontend/app/assinar/page.tsx): card único do Pro, lista `BENEFICIOS`, botão "Assinar agora" → `window.location.href = url`. Tem **resgate de cupom** (`/api/vouchers/resgatar`) e estado "já assinante". Polling de `/api/billing/status` após `?status=sucesso`.
- **`/conta`** — sem nenhuma seção de billing.
- **Preço** — mensal R$ 29,90 (`STRIPE_PRICE_LABEL`, `scripts/stripe_setup.py`).

## Decisões tomadas

| Tema | Decisão |
|---|---|
| Layout `/assinar` | **Direção A**: Grátis (seu plano) vs Pro destacado, checklist do que se perde no grátis + toggle Mensal/Anual. |
| Checkout | **Elements + Checkout Sessions API** (`ui_mode: "elements"`, `mode: "subscription"`) — mesmo modelo do ChatGPT. Não é redirect, não é Embedded de página inteira, não é PaymentIntent cru. |
| Métodos de pagamento | **Cartão** via Dynamic Payment Methods (configurado no Dashboard). **Pix e Link ficam de fora** por ora: conta BR não tem Pix Automático (recorrente) e o Payment Element não suporta Link no Brasil. Nada de "Pix em breve" na UI. |
| Cartão salvo | Habilitado via `customer` + `saved_payment_method_options`. |
| Plano anual | **R$ 298,80/ano** (≈ R$ 24,90/mês, "2 meses grátis", ~17% off). Mensal segue R$ 29,90. |
| Stripe Tax | **Off** no MVP (`automatic_tax` desabilitado). R$ é preço final. |
| Fulfillment | **Somente via webhook** — o retorno do front nunca libera acesso. |
| Portal | `POST /api/billing/portal` (cancelar / trocar cartão), retorno para `/conta`. |
| `/conta` | Nova seção: plano, renovação/cancelamento, botão Gerenciar (Pro) / Assinar (grátis). |
| Cupom | Preservar o resgate de cupom existente na `/assinar`. |

## Arquitetura

### Backend

**`stripe_client.py`**
- Fixar a **versão da API** que suporta `ui_mode: "elements"`: enviar header
  `Stripe-Version: 2026-05-27.dahlia` em `stripe_request` (ou variável
  `STRIPE_API_VERSION`). Sem isso, `ui_mode=elements` pode falhar conforme a
  versão default da conta.
- Adicionar constantes: `STRIPE_PRICE_ID_ANUAL`, `PRECO_LABEL_ANUAL`.
- `stripe_configurado()` continua exigindo secret key + price mensal.

**`billing_router.py`**
- `POST /api/billing/checkout` — **reescrito**:
  - Aceita body `{ intervalo: "month" | "year" }` (default `month`).
  - Resolve `price` = `STRIPE_PRICE_ID` (month) ou `STRIPE_PRICE_ID_ANUAL` (year).
  - Mantém `_garantir_customer` ([billing_router.py:72](../../../backend/billing_router.py#L72)).
  - Cria Checkout Session com:
    - `ui_mode=elements`, `mode=subscription`
    - `line_items[0][price]`, `line_items[0][quantity]=1`
    - `customer`, `metadata[usuario_uid]`, `subscription_data[metadata][usuario_uid]`
    - `return_url={FRONTEND_URL}/assinar?status=sucesso&session_id={CHECKOUT_SESSION_ID}`
    - `saved_payment_method_options[payment_method_save]=enabled`
    - **Sem** `success_url`/`cancel_url` (proibidos em `ui_mode=elements`).
    - **Sem** `payment_method_types` (deixa Dynamic Payment Methods decidir).
    - `allow_promotion_codes` não é suportado direto em `ui_mode=elements`; cupom continua pelo fluxo de voucher interno (não Stripe promo).
  - Retorna **`{ client_secret, intervalo }`** (não mais `url`).
- `POST /api/billing/portal` — **novo**: cria `billing_portal/sessions` com
  `customer` + `return_url={FRONTEND_URL}/conta`. Retorna `{ url }`. 400 se o
  usuário não tem `stripe_customer_id`.
- `POST /api/billing/webhook` — mantém `_upsert_sub`. `checkout.session.completed`
  continua disparando para `ui_mode=elements`. Opcional: somar
  `invoice.payment_failed` para refletir falhas (status fica visível na `/conta`).
- `GET /api/billing/status` — acrescentar ao payload: `preco_label_anual`,
  `stripe_customer_id` (ou um booleano `tem_customer`) para a `/conta` saber se
  pode abrir o portal.

### Frontend

**Dependências novas:** `@stripe/stripe-js` + `@stripe/react-stripe-js` (subpath
`/checkout`: `CheckoutElementsProvider`, `PaymentElement`, `useCheckoutElements`).
Confirmar na instalação que a versão expõe esses símbolos (a API teve renome
`CustomCheckoutProvider`→`CheckoutProvider`; pinar versão compatível).

**`/assinar` — reescrita (Direção A):**
1. **Passo 1 — planos:** toggle Mensal/Anual; dois cards (Grátis = "seu plano",
   Pro destacado). Card Pro mostra preço conforme o toggle (`preco_label` /
   `preco_label_anual`) e contador "X/10 hoje". Botão "Assinar agora".
2. **Passo 2 — pagamento (mesma página):** ao clicar, chama
   `POST /api/billing/checkout` com `{intervalo}`, recebe `client_secret`, monta
   `<CheckoutElementsProvider stripe={stripePromise} options={{clientSecret}}>`
   com `<PaymentElement options={{layout:{type:"tabs"}}}/>` + resumo do plano à
   direita (renderizado por nós). Botão confirma via `checkout.confirm()`.
   `stripePromise = loadStripe(status.publishable_key)`.
3. **Retorno:** `checkout.confirm()` redireciona para
   `/assinar?status=sucesso&session_id=...`; mantém o **polling** atual de
   `/api/billing/status` até `ilimitado`.
4. **Preservar:** estado "já assinante", resgate de cupom, mensagem de Stripe
   não configurado.

**`/conta` — nova seção billing:**
- Lê `/api/billing/status`. Mostra badge do plano, "Renova em DD/MM" ou
  "Acesso até DD/MM" (cancelado), e:
  - Pro → botão "Gerenciar assinatura" → `POST /api/billing/portal` → redirect.
  - Grátis → botão "Assinar Pro" → `/assinar`.

**Unificação de features:**
- Criar fonte única dos benefícios do Pro (ex.: `fontend/app/lib/planos.ts`)
  consumida pela landing `#planos` ([fontend/app/page.tsx](../../../fontend/app/page.tsx)) e pela `/assinar`,
  eliminando as duas listas divergentes de hoje.

### Configuração Stripe

- `scripts/stripe_setup.py` — criar **segundo price** anual
  (`recurring[interval]=year`, `unit_amount=29880`) no produto "studIA Pro";
  expor `STRIPE_PRICE_ID_ANUAL`.
- No **Dashboard**: habilitar Dynamic Payment Methods com **cartão** ativo.
- `build.sh` — adicionar `STRIPE_PRICE_ID_ANUAL`, `STRIPE_PRICE_LABEL_ANUAL`,
  `STRIPE_API_VERSION` às envs do backend.

## Fluxos

**Assinar (caminho feliz):**
`/assinar` → escolhe intervalo → "Assinar agora" → `POST /checkout` (`client_secret`)
→ PaymentElement → `checkout.confirm()` → 3DS se preciso → `return_url` sucesso →
webhook `checkout.session.completed` marca assinatura → polling vê `ilimitado` →
estado "já assinante".

**Gerenciar:** `/conta` → "Gerenciar assinatura" → `POST /portal` → portal Stripe
→ retorna a `/conta`; webhook `customer.subscription.updated/deleted` reflete
cancelamento.

## Casos de borda

- **Já Pro tentando assinar:** `/checkout` já bloqueia (`acesso_pro_ativo`) →
  front mostra estado "já assinante".
- **Falha de pagamento / 3DS:** tratado pelo PaymentElement + `checkout.confirm()`;
  exibir `error.message`, permitir novo envio.
- **Sessão expira (24h):** criar nova Checkout Session a cada entrada no passo 2.
- **Sem `customer` ao abrir portal:** `/portal` retorna 400; `/conta` esconde o
  botão Gerenciar (usa `tem_customer`).
- **Stripe não configurado:** botões desabilitados, mensagem (comportamento atual).

## Fora de escopo

- Pix / Link / Apple Pay / Google Pay (reavaliar quando a conta BR suportar).
- Stripe Tax / nota fiscal.
- Trial gratuito.
- Migração de assinantes mensais existentes para anual.

## Plano de validação

- Checkout de teste (cartão `4242…`) em mensal e anual → assinatura ativa via
  webhook → `ilimitado=true`.
- Cartão 3DS (`4000 0025 0000 3155`) → fluxo de autenticação.
- Portal: cancelar → webhook → `/conta` mostra "Acesso até".
- Cupom continua liberando Pro sem pagamento.
- `pnpm lint` limpo; deploy `./build.sh` com as novas envs.
