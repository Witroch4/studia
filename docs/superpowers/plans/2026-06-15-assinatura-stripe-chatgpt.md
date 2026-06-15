# Assinatura studIA estilo ChatGPT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o checkout hospedado por um checkout transparente estilo ChatGPT (Stripe Elements + Checkout Sessions API), com plano anual, portal de gerenciamento e billing na `/conta`.

**Architecture:** Backend cria `Checkout Session` com `ui_mode="elements"` / `mode="subscription"` e devolve `client_secret`; o frontend monta o `PaymentElement` na própria `/assinar` (Direção A: Grátis vs Pro + toggle Mensal/Anual). Fulfillment continua só por webhook. Novo endpoint de portal e nova seção billing na `/conta`.

**Tech Stack:** FastAPI + cliente REST Stripe (httpx, sem SDK) · Next.js 16 / React 19 · `@stripe/stripe-js` + `@stripe/react-stripe-js` · React Query.

**Nota sobre testes:** o projeto não tem harness de testes automatizados (CLAUDE.md). A verificação de cada task é via `pnpm lint`, checagem de import Python, `curl` no dev e smoke manual. Commits frequentes; ao final segue o ciclo obrigatório commit→push→`./build.sh`.

**Spec:** [docs/superpowers/specs/2026-06-15-assinatura-stripe-chatgpt-design.md](../specs/2026-06-15-assinatura-stripe-chatgpt-design.md)

---

## File Structure

**Backend (modificar):**
- `backend/stripe_client.py` — header `Stripe-Version`, constantes do anual.
- `backend/billing_router.py` — checkout `ui_mode=elements`, endpoint `/portal`, status enriquecido.
- `backend/scripts/stripe_setup.py` — price anual.

**Frontend (criar/modificar):**
- `fontend/app/lib/planos.ts` — **criar**: fonte única de features + preços.
- `fontend/app/assinar/page.tsx` — **reescrever**: Direção A + PaymentElement.
- `fontend/app/conta/BillingSection.tsx` — **criar**: bloco de assinatura.
- `fontend/app/conta/ContaClient.tsx` — **modificar**: renderizar `BillingSection`.
- `fontend/app/page.tsx` — **modificar**: `#planos` consome `planos.ts`.

**Infra:**
- `build.sh` — novas envs.

---

## Task 1: Stripe client — versão da API + constantes do anual

**Files:**
- Modify: `backend/stripe_client.py:17-22`, `backend/stripe_client.py:37-56`

- [ ] **Step 1: Adicionar constantes de versão e anual**

Em [backend/stripe_client.py:17-22](../../../backend/stripe_client.py#L17-L22), logo após `STRIPE_PRICE_ID`, inserir:

```python
STRIPE_PRICE_ID_ANUAL = os.getenv("STRIPE_PRICE_ID_ANUAL", "")
PRECO_LABEL = os.getenv("STRIPE_PRICE_LABEL", "R$ 29,90/mês")
PRECO_LABEL_ANUAL = os.getenv("STRIPE_PRICE_LABEL_ANUAL", "R$ 298,80/ano")
# Versão da API que suporta ui_mode="elements" (confirmar a vigente da conta).
STRIPE_API_VERSION = os.getenv("STRIPE_API_VERSION", "2026-05-27.dahlia")
```

(Remover a linha antiga de `PRECO_LABEL` que já existe na L22 para não duplicar.)

- [ ] **Step 2: Enviar o header `Stripe-Version` em toda chamada**

Em `stripe_request` ([backend/stripe_client.py:42-49](../../../backend/stripe_client.py#L42-L49)), trocar o bloco de headers:

```python
        resp = await client.request(
            method,
            url,
            data={k: str(v) for k, v in (data or {}).items()},
            auth=(STRIPE_SECRET_KEY, ""),
            headers={
                "Accept": "application/json",
                **({"Stripe-Version": STRIPE_API_VERSION} if STRIPE_API_VERSION else {}),
            },
        )
```

- [ ] **Step 3: Verificar import**

Run: `cd backend && python -c "import stripe_client as s; print(s.STRIPE_API_VERSION, s.PRECO_LABEL_ANUAL)"`
Expected: imprime `2026-05-27.dahlia R$ 298,80/ano` sem erro.

- [ ] **Step 4: Commit**

```bash
git add backend/stripe_client.py
git commit -m "feat(billing): pin Stripe-Version + constantes do plano anual"
```

---

## Task 2: Script de setup — criar o price anual

**Files:**
- Modify: `backend/scripts/stripe_setup.py`

- [ ] **Step 1: Ler o script atual**

Run: `cat backend/scripts/stripe_setup.py`
Objetivo: localizar onde o price mensal é criado (`recurring[interval]=month`, `unit_amount=2990`) e o produto "studIA Pro".

- [ ] **Step 2: Criar o price anual após o mensal**

Replicar a criação do price, reutilizando o mesmo `product` id, com:

```python
price_anual = stripe_post("/prices", {
    "product": product_id,            # mesmo produto "studIA Pro"
    "unit_amount": "29880",           # R$ 298,80
    "currency": "brl",
    "recurring[interval]": "year",
    "nickname": "studIA Pro Anual",
})
print("STRIPE_PRICE_ID_ANUAL=", price_anual["id"])
```

Adaptar nomes (`stripe_post`/`product_id`) ao que o script já usa. O script deve imprimir o `STRIPE_PRICE_ID_ANUAL` para colar no `build.sh`/env.

- [ ] **Step 3: Rodar contra a conta de teste**

Run: `cd backend && python -m scripts.stripe_setup` (ou o comando que o script usa)
Expected: imprime `STRIPE_PRICE_ID_ANUAL= price_...`. Anotar o id.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/stripe_setup.py
git commit -m "feat(billing): provisiona price anual no stripe_setup"
```

---

## Task 3: Checkout `ui_mode=elements` (client_secret + intervalo)

**Files:**
- Modify: `backend/billing_router.py:23-31` (imports), `backend/billing_router.py:95-126` (rota)

- [ ] **Step 1: Importar as constantes novas**

Em [backend/billing_router.py:23-31](../../../backend/billing_router.py#L23-L31), no import de `stripe_client`, acrescentar `PRECO_LABEL_ANUAL`, `STRIPE_PRICE_ID_ANUAL`:

```python
from stripe_client import (
    PRECO_LABEL,
    PRECO_LABEL_ANUAL,
    STRIPE_PRICE_ID,
    STRIPE_PRICE_ID_ANUAL,
    STRIPE_PUBLISHABLE_KEY,
    StripeError,
    stripe_configurado,
    stripe_request,
    verificar_assinatura_webhook,
)
```

Adicionar import do Pydantic para o body (topo do arquivo, junto aos outros imports):

```python
from pydantic import BaseModel
```

- [ ] **Step 2: Reescrever `criar_checkout`**

Substituir a função inteira ([backend/billing_router.py:95-126](../../../backend/billing_router.py#L95-L126)) por:

```python
class CheckoutBody(BaseModel):
    intervalo: str = "month"  # "month" | "year"


@router.post("/checkout")
async def criar_checkout(
    body: CheckoutBody = CheckoutBody(),
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado (faltam chaves Stripe)")
    if user.is_admin or await acesso_pro_ativo(db, user.id):
        raise HTTPException(400, "você já tem acesso ilimitado")

    intervalo = "year" if body.intervalo == "year" else "month"
    price = STRIPE_PRICE_ID_ANUAL if intervalo == "year" else STRIPE_PRICE_ID
    if not price:
        raise HTTPException(503, f"plano {intervalo} não configurado")

    try:
        customer_id = await _garantir_customer(db, user)
        session = await stripe_request(
            "POST",
            "/checkout/sessions",
            {
                "ui_mode": "elements",
                "mode": "subscription",
                "line_items[0][price]": price,
                "line_items[0][quantity]": "1",
                "customer": customer_id,
                "client_reference_id": user.id,
                "metadata[usuario_uid]": user.id,
                "subscription_data[metadata][usuario_uid]": user.id,
                "saved_payment_method_options[payment_method_save]": "enabled",
                "return_url": (
                    f"{FRONTEND_URL}/assinar?status=sucesso"
                    "&session_id={CHECKOUT_SESSION_ID}"
                ),
            },
        )
    except StripeError as exc:
        raise HTTPException(502, f"Stripe: {exc.message}") from exc

    return {"client_secret": session["client_secret"], "intervalo": intervalo}
```

Notas: em `ui_mode=elements` **não** se envia `success_url`/`cancel_url` (proibidos) nem `payment_method_types` (deixa Dynamic Payment Methods decidir). O `_garantir_customer` e o webhook permanecem como estão.

- [ ] **Step 3: Subir o dev e testar o checkout**

Run: `./dev.sh up:d && sleep 8`
Run (autenticado — usar cookie de sessão de um usuário grátis, ou testar pelo browser): `curl -s -X POST http://localhost:8011/api/billing/checkout -H 'Content-Type: application/json' -d '{"intervalo":"month"}' -b "<cookie>"`
Expected: JSON com `client_secret` começando por `cs_test_..._secret_...` e `"intervalo":"month"`. (Se Stripe reclamar de `ui_mode`, conferir `STRIPE_API_VERSION` com a versão vigente da conta no Dashboard → Developers → API version.)

- [ ] **Step 4: Commit**

```bash
git add backend/billing_router.py
git commit -m "feat(billing): checkout ui_mode=elements devolve client_secret + intervalo"
```

---

## Task 4: Endpoint do portal de gerenciamento

**Files:**
- Modify: `backend/billing_router.py` (nova rota após `criar_checkout`)

- [ ] **Step 1: Adicionar `POST /api/billing/portal`**

Inserir após a função `criar_checkout`:

```python
@router.post("/portal")
async def abrir_portal(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not stripe_configurado():
        raise HTTPException(503, "billing não configurado")
    row = (
        await db.execute(
            select(Assinatura)
            .where(
                Assinatura.usuario_uid == user.id,
                Assinatura.stripe_customer_id.isnot(None),
            )
            .order_by(Assinatura.updated_at.desc())
        )
    ).scalars().first()
    if not row or not row.stripe_customer_id:
        raise HTTPException(400, "nenhuma assinatura para gerenciar")

    try:
        sess = await stripe_request(
            "POST",
            "/billing_portal/sessions",
            {
                "customer": row.stripe_customer_id,
                "return_url": f"{FRONTEND_URL}/conta",
            },
        )
    except StripeError as exc:
        raise HTTPException(502, f"Stripe: {exc.message}") from exc
    return {"url": sess["url"]}
```

- [ ] **Step 2: Testar**

Run: `curl -s -X POST http://localhost:8011/api/billing/portal -b "<cookie de usuário com customer>"`
Expected: `{"url":"https://billing.stripe.com/p/session/..."}`. Para usuário sem customer: HTTP 400 `nenhuma assinatura para gerenciar`. (O portal precisa estar ativado em Dashboard → Settings → Billing → Customer portal.)

- [ ] **Step 3: Commit**

```bash
git add backend/billing_router.py
git commit -m "feat(billing): endpoint /portal (billing portal session)"
```

---

## Task 5: Status enriquecido (label anual + tem_customer)

**Files:**
- Modify: `backend/billing_router.py:51-69`

- [ ] **Step 1: Acrescentar campos ao payload de status**

Em `billing_status` ([backend/billing_router.py:51-69](../../../backend/billing_router.py#L51-L69)), antes do `return`, descobrir se há customer e incluir os novos campos:

```python
    tem_customer = (
        await db.execute(
            select(Assinatura.id).where(
                Assinatura.usuario_uid == user.id,
                Assinatura.stripe_customer_id.isnot(None),
            )
        )
    ).first() is not None
    return {
        "plano": "pro" if ilimitado else "free",
        "is_admin": user.is_admin,
        "ilimitado": ilimitado,
        "assinatura": _assinatura_dict(ass) if ass else None,
        "voucher_pro_ate": voucher_ate.isoformat() if voucher_ate else None,
        "limite": await resumo_limite(db, user),
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "preco_label": PRECO_LABEL,
        "preco_label_anual": PRECO_LABEL_ANUAL,
        "tem_customer": tem_customer,
        "stripe_configurado": stripe_configurado(),
    }
```

- [ ] **Step 2: Testar**

Run: `curl -s http://localhost:8011/api/billing/status -b "<cookie>" | python -m json.tool`
Expected: contém `preco_label_anual` e `tem_customer`.

- [ ] **Step 3: Commit**

```bash
git add backend/billing_router.py
git commit -m "feat(billing): status expõe preco_label_anual e tem_customer"
```

---

## Task 6: Instalar libs Stripe + confirmar exports

**Files:**
- Modify: `fontend/package.json`

- [ ] **Step 1: Instalar**

Run: `cd fontend && pnpm add @stripe/stripe-js @stripe/react-stripe-js`

- [ ] **Step 2: Confirmar os símbolos exportados (CRÍTICO)**

Run: `cd fontend && cat node_modules/@stripe/react-stripe-js/dist/react-stripe.d.ts | grep -iE "CheckoutElementsProvider|useCheckoutElements|CheckoutProvider|useCheckout|PaymentElement" | head -40`
Run: `ls node_modules/@stripe/react-stripe-js/` (ver se existe subpath `/checkout`)

Decidir qual API a versão instalada expõe e usar nas Tasks 8/9:
- Se existir `@stripe/react-stripe-js/checkout` com `CheckoutElementsProvider`/`useCheckoutElements` → usar esse import (o do guia do ChatGPT).
- Se a versão usar `CheckoutProvider`/`useCheckout` no pacote raiz → adaptar os imports e a leitura de estado conforme os tipos. O restante da lógica (montar `PaymentElement`, `checkout.confirm()`) é equivalente.

Anotar a escolha num comentário no topo de `page.tsx` na Task 8.

- [ ] **Step 3: Commit**

```bash
git add fontend/package.json fontend/pnpm-lock.yaml
git commit -m "chore(frontend): adiciona @stripe/stripe-js + react-stripe-js"
```

---

## Task 7: Fonte única de planos/benefícios

**Files:**
- Create: `fontend/app/lib/planos.ts`

- [ ] **Step 1: Criar o módulo**

```ts
// Fonte única dos planos — consumida pela landing (#planos) e por /assinar.

export const BENEFICIOS_PRO = [
  "Questões ilimitadas por dia",
  "Estatísticas e comentários em cada questão",
  "Cadernos e filtros sem limite",
  "Acesso a todo o histórico de resoluções",
  "Disciplinas e PDFs com IA sem limite",
] as const;

export const BENEFICIOS_FREE = [
  "10 questões por dia",
  "Flashcards com repetição espaçada",
  "1 disciplina com IA",
  "Estatísticas básicas",
] as const;

// Preço anual: 12 meses pelo valor de 10 (2 meses grátis).
export const PRECO_MENSAL_LABEL = "R$ 29,90";
export const PRECO_ANUAL_LABEL = "R$ 298,80";
export const PRECO_ANUAL_EQUIV_MES = "R$ 24,90"; // 298,80 / 12
export const ECONOMIA_ANUAL = "2 meses grátis";
```

- [ ] **Step 2: Verificar lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
git add fontend/app/lib/planos.ts
git commit -m "feat(frontend): módulo único de planos/benefícios"
```

---

## Task 8: Reescrever `/assinar` (Direção A + PaymentElement)

**Files:**
- Rewrite: `fontend/app/assinar/page.tsx`

> Preservar: estado "já assinante", resgate de cupom, polling pós-`?status=sucesso`, mensagem de Stripe não configurado. Usar a API do Stripe confirmada na Task 6. O código abaixo assume `@stripe/react-stripe-js/checkout` (`CheckoutElementsProvider`/`useCheckoutElements`); se a Task 6 indicou outra, adaptar imports e a leitura de `checkoutState.type`.

- [ ] **Step 1: Escrever o novo `page.tsx`**

Estrutura: `AssinarInner` (planos + toggle + estados existentes) → ao clicar "Assinar agora", busca `client_secret` e renderiza `<PagamentoTransparente>` dentro do `CheckoutElementsProvider`. Manter o `BillingStatus` type, o `useQuery` com `refetchInterval`, o bloco de cupom e o estado "já assinante" iguais ao arquivo atual ([fontend/app/assinar/page.tsx](../../../fontend/app/assinar/page.tsx)); só trocar (a) o card único pelo comparativo + toggle e (b) a função `assinar()` (que fazia `window.location.href`) pelo fluxo de PaymentElement.

Trechos novos/alterados:

```tsx
// imports adicionais no topo
import { loadStripe } from "@stripe/stripe-js";
import {
  CheckoutElementsProvider,
  PaymentElement,
  useCheckoutElements,
} from "@stripe/react-stripe-js/checkout";
import { BENEFICIOS_PRO, BENEFICIOS_FREE, PRECO_ANUAL_EQUIV_MES, ECONOMIA_ANUAL } from "@/app/lib/planos";
```

```tsx
// estado novo dentro de AssinarInner (junto aos outros useState)
const [intervalo, setIntervalo] = useState<"month" | "year">("month");
const [clientSecret, setClientSecret] = useState<string | null>(null);

// stripePromise memoizado pela publishable_key vinda do status
const stripePromise = useMemo(
  () => (status?.publishable_key ? loadStripe(status.publishable_key) : null),
  [status?.publishable_key],
);

// substitui a antiga assinar() que redirecionava
async function assinar() {
  setErro(null);
  setCheckingOut(true);
  try {
    const { client_secret } = await apiPost<{ client_secret: string }>(
      "/api/billing/checkout",
      { intervalo },
    );
    setClientSecret(client_secret);
  } catch (e) {
    setErro(e instanceof ApiError ? e.message : "Não foi possível iniciar o checkout.");
  } finally {
    setCheckingOut(false);
  }
}
```

Bloco de seleção de plano (substitui o card único atual, dentro do ramo `else` de usuário grátis), exibido enquanto `clientSecret` é null:

```tsx
{!clientSecret ? (
  <>
    {/* toggle Mensal/Anual */}
    <div className="mb-6 flex justify-center">
      <div className="inline-flex rounded-full border border-border-dark bg-page p-1 text-sm">
        <button
          onClick={() => setIntervalo("month")}
          className={`rounded-full px-4 py-1.5 ${intervalo === "month" ? "bg-primary text-on-primary font-semibold" : "text-fg-muted"}`}
        >Mensal</button>
        <button
          onClick={() => setIntervalo("year")}
          className={`rounded-full px-4 py-1.5 ${intervalo === "year" ? "bg-primary text-on-primary font-semibold" : "text-fg-muted"}`}
        >Anual <span className="ml-1 rounded-full bg-secondary/20 px-1.5 text-[10px] text-secondary">{ECONOMIA_ANUAL}</span></button>
      </div>
    </div>

    {/* comparativo Grátis vs Pro */}
    <div className="grid gap-4 sm:grid-cols-2">
      {/* Grátis */}
      <div className="rounded-2xl border border-border-dark bg-surface-dark p-6">
        <div className="text-xs font-semibold text-fg-faint">SEU PLANO</div>
        <div className="mt-1 text-sm font-semibold text-fg-muted">Grátis</div>
        <div className="mt-2 text-3xl font-extrabold text-fg-strong">R$0</div>
        <ul className="mt-5 space-y-2.5">
          {BENEFICIOS_FREE.map((b) => (
            <li key={b} className="flex items-center gap-2 text-sm text-fg-muted">
              <span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>{b}
            </li>
          ))}
        </ul>
        <div className="mt-6 rounded-lg border border-border-dark py-2.5 text-center text-sm text-fg-faint">Plano atual</div>
      </div>

      {/* Pro */}
      <div className="relative rounded-2xl border-2 border-secondary bg-secondary/5 p-6 shadow-xl">
        <span className="absolute -top-2.5 right-5 rounded-full bg-secondary px-2.5 py-0.5 text-[10px] font-bold text-white">RECOMENDADO</span>
        <div className="mt-1 text-sm font-semibold text-secondary">Pro</div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-3xl font-extrabold text-fg-strong">
            {intervalo === "year"
              ? PRECO_ANUAL_EQUIV_MES
              : (status?.preco_label?.split("/")[0] ?? "R$ 29,90")}
          </span>
          <span className="text-fg-faint">/mês</span>
        </div>
        {intervalo === "year" && (
          <p className="mt-1 text-xs text-fg-faint">{status?.preco_label_anual} cobrado anualmente · {ECONOMIA_ANUAL}</p>
        )}
        {status?.limite && !status.limite.ilimitado && (
          <p className="mt-2 text-xs text-fg-muted">Hoje: {status.limite.usado}/{status.limite.limite} questões grátis.</p>
        )}
        <ul className="mt-5 space-y-2.5">
          {BENEFICIOS_PRO.map((b) => (
            <li key={b} className="flex items-center gap-2 text-sm text-fg">
              <span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>{b}
            </li>
          ))}
        </ul>
        {erro && (
          <div className="mt-4 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">{erro}</div>
        )}
        <button
          onClick={assinar}
          disabled={checkingOut || !status?.stripe_configurado}
          className="mt-6 w-full rounded-lg bg-secondary py-3 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition"
        >{checkingOut ? "Carregando…" : "Assinar agora"}</button>
        <p className="mt-3 text-center text-xs text-fg-faint">Pagamento seguro via Stripe · cancele quando quiser</p>
      </div>
    </div>
    {/* ...bloco de cupom existente, mantido aqui... */}
  </>
) : (
  stripePromise && (
    <CheckoutElementsProvider
      stripe={stripePromise}
      options={{ clientSecret, elementsOptions: { appearance: { theme: "night", variables: { colorPrimary: "#06b6d4" } } } }}
    >
      <PagamentoTransparente
        intervalo={intervalo}
        precoAnual={status?.preco_label_anual}
        onVoltar={() => setClientSecret(null)}
      />
    </CheckoutElementsProvider>
  )
)}
```

Componente do passo de pagamento (adicionar no mesmo arquivo):

```tsx
function PagamentoTransparente({
  intervalo,
  precoAnual,
  onVoltar,
}: {
  intervalo: "month" | "year";
  precoAnual?: string;
  onVoltar: () => void;
}) {
  const checkoutState = useCheckoutElements();
  const [erroPg, setErroPg] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (checkoutState.type === "loading") {
    return <p className="text-fg-faint">Carregando pagamento…</p>;
  }
  if (checkoutState.type === "error") {
    return <p className="text-error">{checkoutState.error.message}</p>;
  }
  const { checkout } = checkoutState;

  async function pagar(e: React.FormEvent) {
    e.preventDefault();
    setErroPg(null);
    setEnviando(true);
    const { error } = await checkout.confirm();
    if (error) {
      setErroPg(error.message ?? "Não foi possível confirmar o pagamento.");
      setEnviando(false);
    }
    // sucesso → Stripe redireciona para o return_url (/assinar?status=sucesso)
  }

  return (
    <div className="grid gap-6 sm:grid-cols-[1fr_280px]">
      <form onSubmit={pagar} className="rounded-2xl border border-border-dark bg-surface-dark p-6">
        <button type="button" onClick={onVoltar} className="mb-4 text-xs text-secondary">← voltar aos planos</button>
        <h3 className="mb-4 text-sm font-semibold text-fg-strong">Método de pagamento</h3>
        <PaymentElement options={{ layout: { type: "tabs" } }} />
        {erroPg && <div className="mt-4 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">{erroPg}</div>}
        <button type="submit" disabled={enviando} className="mt-5 w-full rounded-lg bg-secondary py-3 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition">
          {enviando ? "Processando…" : "Assinar"}
        </button>
        <p className="mt-3 text-center text-xs text-fg-faint">🔒 Protegido pelo Stripe</p>
      </form>
      <aside className="rounded-2xl border border-border-dark bg-page p-5 text-sm">
        <div className="font-semibold text-fg-strong">studIA Pro · {intervalo === "year" ? "Anual" : "Mensal"}</div>
        <div className="mt-3 flex justify-between text-fg-muted">
          <span>Total hoje</span>
          <strong className="text-fg-strong">{intervalo === "year" ? precoAnual : "R$ 29,90"}</strong>
        </div>
        <p className="mt-3 text-xs text-fg-faint">Renovação {intervalo === "year" ? "anual" : "mensal"} até cancelar.</p>
      </aside>
    </div>
  );
}
```

Garantir `import { useMemo } from "react";` no topo.

- [ ] **Step 2: Lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros (atenção a imports não usados e tipos do `useCheckoutElements`).

- [ ] **Step 3: Smoke manual**

Abrir `http://localhost:3000/assinar` como usuário grátis. Verificar: toggle Mensal/Anual muda preço; "Assinar agora" revela o PaymentElement na mesma página; cartão de teste `4242 4242 4242 4242` confirma e redireciona para `?status=sucesso`; após o webhook, vira "já assinante". Confirmar que o cupom ainda funciona.

- [ ] **Step 4: Commit**

```bash
git add fontend/app/assinar/page.tsx
git commit -m "feat(assinar): Direção A (comparativo + toggle anual) + checkout transparente PaymentElement"
```

---

## Task 9: Seção de billing na `/conta`

**Files:**
- Create: `fontend/app/conta/BillingSection.tsx`
- Modify: `fontend/app/conta/ContaClient.tsx`

- [ ] **Step 1: Criar `BillingSection.tsx`**

```tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiJson, apiPost, ApiError } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

type BillingStatus = {
  plano: "free" | "pro";
  ilimitado: boolean;
  is_admin: boolean;
  assinatura: { status: string; current_period_end: string | null; cancel_at_period_end: boolean } | null;
  voucher_pro_ate: string | null;
  tem_customer: boolean;
};

export default function BillingSection() {
  const [abrindo, setAbrindo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const { data: s, isPending } = useQuery<BillingStatus>({
    queryKey: qk.billing(),
    queryFn: () => apiJson<BillingStatus>("/api/billing/status"),
  });

  async function gerenciar() {
    setErro(null);
    setAbrindo(true);
    try {
      const { url } = await apiPost<{ url: string }>("/api/billing/portal");
      window.location.href = url;
    } catch (e) {
      setAbrindo(false);
      setErro(e instanceof ApiError ? e.message : "Não foi possível abrir o portal.");
    }
  }

  if (isPending || !s) return null;

  const ass = s.assinatura;
  return (
    <section className="rounded-2xl border border-border-dark bg-surface-dark p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-fg-strong">Assinatura</h2>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.ilimitado ? "bg-secondary/20 text-secondary" : "bg-border-dark text-fg-muted"}`}>
          {s.is_admin ? "Admin" : s.ilimitado ? "Pro" : "Grátis"}
        </span>
      </div>

      {ass?.current_period_end && (
        <p className="mt-3 text-sm text-fg-muted">
          {ass.cancel_at_period_end ? "Acesso até " : "Renova em "}
          {new Date(ass.current_period_end).toLocaleDateString("pt-BR")}
        </p>
      )}
      {!ass && s.voucher_pro_ate && (
        <p className="mt-3 text-sm text-fg-muted">Acesso via cupom até {new Date(s.voucher_pro_ate).toLocaleDateString("pt-BR")}</p>
      )}

      {erro && <div className="mt-4 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">{erro}</div>}

      <div className="mt-5">
        {s.tem_customer && !s.is_admin ? (
          <button onClick={gerenciar} disabled={abrindo} className="rounded-lg border border-border-dark px-4 py-2 text-sm font-semibold text-fg-strong hover:bg-page disabled:opacity-50 transition">
            {abrindo ? "Abrindo…" : "Gerenciar assinatura"}
          </button>
        ) : !s.ilimitado ? (
          <Link href="/assinar" className="inline-block rounded-lg bg-secondary px-4 py-2 text-sm font-semibold text-white hover:opacity-90 transition">
            Assinar Pro
          </Link>
        ) : null}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Renderizar em `ContaClient.tsx`**

Importar e inserir `<BillingSection />` no topo do conteúdo da página (acima de perfil). Ler [fontend/app/conta/ContaClient.tsx](../../../fontend/app/conta/ContaClient.tsx) e adicionar:

```tsx
import BillingSection from "./BillingSection";
```
e, no JSX, antes da seção de perfil:
```tsx
<BillingSection />
```

- [ ] **Step 3: Lint + smoke**

Run: `cd fontend && pnpm lint`
Abrir `http://localhost:3000/conta`: usuário grátis vê badge "Grátis" + botão "Assinar Pro"; usuário Pro vê "Renova em…" + "Gerenciar assinatura" (abre portal).

- [ ] **Step 4: Commit**

```bash
git add fontend/app/conta/BillingSection.tsx fontend/app/conta/ContaClient.tsx
git commit -m "feat(conta): seção de assinatura com portal de gerenciamento"
```

---

## Task 10: Landing `#planos` consome a fonte única

**Files:**
- Modify: `fontend/app/page.tsx` (array `PLANS` ~L76-102 e seção `#planos` ~L395-446)

- [ ] **Step 1: Substituir features hardcoded pelo módulo**

Importar no topo:
```tsx
import { BENEFICIOS_PRO, BENEFICIOS_FREE, PRECO_MENSAL_LABEL } from "@/app/lib/planos";
```
No array `PLANS`, trocar as listas de features inline pelas constantes (`BENEFICIOS_FREE` no card grátis, `BENEFICIOS_PRO` no card Pro) e o preço do Pro por `PRECO_MENSAL_LABEL`. Manter os CTAs ("Criar conta grátis" → `/cadastro`, "Assinar o Pro" → `/assinar`).

- [ ] **Step 2: Lint + conferência visual**

Run: `cd fontend && pnpm lint`
Abrir `http://localhost:3000/#planos`: as features do Pro batem com as da `/assinar` (mesma fonte).

- [ ] **Step 3: Commit**

```bash
git add fontend/app/page.tsx
git commit -m "refactor(landing): #planos usa a fonte única de planos"
```

---

## Task 11: Envs de deploy + ciclo final

**Files:**
- Modify: `build.sh`

- [ ] **Step 1: Adicionar envs do backend no build.sh**

Localizar onde `STRIPE_PRICE_ID`/`STRIPE_PRICE_LABEL` são exportadas para o serviço backend e acrescentar:
```
STRIPE_PRICE_ID_ANUAL=<price_anual do Task 2>
STRIPE_PRICE_LABEL_ANUAL=R$ 298,80/ano
STRIPE_API_VERSION=2026-05-27.dahlia
```
(usar o mesmo mecanismo de env já usado para as outras chaves Stripe).

- [ ] **Step 2: Confirmar versão da API no Dashboard**

No Stripe Dashboard → Developers → conferir a API version da conta. Ajustar `STRIPE_API_VERSION` para a vigente que suporte `ui_mode=elements` (se diferente do default do plano).

- [ ] **Step 3: Habilitar no Dashboard**

- Payment methods (Dynamic): cartão ativo.
- Customer portal: ativado (Settings → Billing → Customer portal).

- [ ] **Step 4: Lint final + deploy**

Run: `cd fontend && pnpm lint`
Run: `git push`
Run: `./build.sh`
Expected: build + push de imagens + `db_prepare` + deploy. Worktree limpo (`git status`).

- [ ] **Step 5: Smoke em produção**

Em `https://studia.witdev.com.br/assinar`: checkout de teste mensal e anual, portal pela `/conta`, cupom. Confirmar que o webhook ativa a assinatura.

---

## Self-Review

**Cobertura do spec:**
- `/assinar` Direção A + toggle anual → Task 8 ✓
- Checkout Elements + Checkout Sessions → Tasks 1, 3, 6, 8 ✓
- Cartão-only / sem `payment_method_types` → Task 3 ✓
- Plano anual R$298,80 → Tasks 2, 7, 11 ✓
- `automatic_tax` off → não enviado (Task 3) ✓
- Fulfillment por webhook → webhook mantido (Task 3 nota) ✓
- Portal → Tasks 4, 9 ✓
- Billing na `/conta` → Task 9 ✓
- Unificar features → Tasks 7, 10 ✓
- Preservar cupom + estado "já assinante" → Task 8 ✓
- `Stripe-Version` pinada → Task 1 ✓

**Placeholders:** nenhum "TBD"/"TODO"; código presente em todos os steps de código.

**Consistência de tipos:** `client_secret`/`intervalo` (backend Task 3) ↔ consumidos na Task 8; `preco_label_anual`/`tem_customer` (Task 5) ↔ usados nas Tasks 8 e 9; `BENEFICIOS_PRO`/`BENEFICIOS_FREE` (Task 7) ↔ Tasks 8 e 10. Risco conhecido: nomes exatos do `react-stripe-js` — resolvido na Task 6 antes de codar as Tasks 8/9.
