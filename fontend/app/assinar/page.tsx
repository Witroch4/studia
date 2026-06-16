"use client";

import { Suspense, useState, useMemo } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiJson, apiPost, ApiError } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";
import { loadStripe } from "@stripe/stripe-js";
import { CheckoutElementsProvider, ExpressCheckoutElement, PaymentElement, useCheckoutElements } from "@stripe/react-stripe-js/checkout";
import { BENEFICIOS_PRO, BENEFICIOS_FREE, PRECO_ANUAL_EQUIV_MES, ECONOMIA_ANUAL } from "@/app/lib/planos";

type BillingStatus = {
  plano: "free" | "pro";
  is_admin: boolean;
  ilimitado: boolean;
  assinatura: {
    status: string;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    price_id: string | null;
  } | null;
  limite: {
    ilimitado: boolean;
    usado: number;
    limite: number;
    restantes: number | null;
    motivo: string;
  };
  voucher_pro_ate: string | null;
  publishable_key: string;
  preco_label: string;
  preco_label_anual: string;
  tem_customer: boolean;
  stripe_configurado: boolean;
};

/** Selo oficial — marca do Stripe (mark + wordmark na cor da marca, #635BFF). */
function PoweredByStripe() {
  return (
    <div className="flex items-center justify-center gap-1.5 text-fg-faint">
      <span className="text-[11px]">Powered by</span>
      <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" fill="#635BFF">
        <path d="M13.976 9.15c-2.172-.806-3.356-1.426-3.356-2.409 0-.831.683-1.305 1.901-1.305 2.227 0 4.515.858 6.09 1.631l.89-5.494C18.252.975 15.697 0 12.165 0 9.667 0 7.589.654 6.104 1.872 4.56 3.147 3.757 4.992 3.757 7.218c0 4.039 2.467 5.76 6.476 7.219 2.585.92 3.445 1.574 3.445 2.583 0 .98-.84 1.545-2.354 1.545-1.875 0-4.965-.921-6.99-2.109l-.9 5.555C5.175 22.99 8.385 24 11.714 24c2.641 0 4.843-.624 6.328-1.813 1.664-1.305 2.525-3.236 2.525-5.732 0-4.128-2.524-5.851-6.594-7.305z" />
      </svg>
      <span className="text-[12px] font-bold tracking-tight" style={{ color: "#635BFF" }}>Stripe</span>
    </div>
  );
}

function PagamentoTransparente({ intervalo, valorHoje, onVoltar }: { intervalo: "month" | "year"; valorHoje: string; onVoltar: () => void; }) {
  const checkoutState = useCheckoutElements();
  const [erroPg, setErroPg] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [walletsReady, setWalletsReady] = useState(false);

  if (checkoutState.type === "loading") {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-fg-faint">
        <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
        Preparando o pagamento seguro…
      </div>
    );
  }
  if (checkoutState.type === "error") {
    return (
      <div className="rounded-2xl border border-error/40 bg-error/10 px-4 py-6 text-center text-sm text-error">
        Não foi possível abrir o pagamento. Volte e tente novamente.
        <button type="button" onClick={onVoltar} className="mt-3 block w-full text-secondary">← Voltar aos planos</button>
      </div>
    );
  }
  const { checkout } = checkoutState;

  async function pagar(e: React.FormEvent) {
    e.preventDefault();
    setErroPg(null);
    setEnviando(true);
    const result = await checkout.confirm();
    if (result.type === "error") {
      setErroPg(result.error.message ?? "Não foi possível confirmar o pagamento. Confira os dados do cartão.");
      setEnviando(false);
    }
    // Em caso de sucesso o Stripe redireciona para o return_url.
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_300px]">
      <form onSubmit={pagar} className="rounded-2xl border border-border-dark bg-surface-dark p-6 sm:p-7">
        <button type="button" onClick={onVoltar} className="mb-5 inline-flex items-center gap-1 text-xs font-medium text-fg-muted hover:text-fg-strong transition">
          <span className="material-symbols-outlined text-[16px]">arrow_back</span> Voltar aos planos
        </button>
        <h2 className="mb-4 text-lg font-bold text-fg-strong">Pagamento</h2>

        {/* Fileira expressa de carteiras (Apple Pay / Google Pay). Some quando
            nenhuma carteira está disponível no dispositivo — sem UI vazia. */}
        <ExpressCheckoutElement
          onReady={(e) => setWalletsReady(Boolean(e.availablePaymentMethods))}
          onConfirm={async () => {
            setErroPg(null);
            const r = await checkout.confirm();
            if (r.type === "error") setErroPg(r.error.message ?? "Não foi possível confirmar o pagamento.");
          }}
        />
        {walletsReady && (
          <div className="my-4 flex items-center gap-3 text-[11px] uppercase tracking-wide text-fg-faint">
            <span className="h-px flex-1 bg-border-dark" /> ou com cartão <span className="h-px flex-1 bg-border-dark" />
          </div>
        )}

        <PaymentElement options={{ layout: { type: "tabs" }, wallets: { applePay: "auto", googlePay: "auto", link: "auto" } }} />
        {erroPg && (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">
            <span className="material-symbols-outlined text-[18px]">error</span>
            <span>{erroPg}</span>
          </div>
        )}
        <button type="submit" disabled={enviando} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-secondary py-3.5 text-sm font-semibold text-white shadow-[0_8px_24px_rgba(139,92,246,0.30)] hover:opacity-90 disabled:opacity-50 transition">
          {enviando && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
          {enviando ? "Processando…" : `Pagar ${valorHoje} e assinar`}
        </button>
        <p className="mt-3 text-center text-[11px] text-fg-faint">Cobrança segura · cancele quando quiser</p>
        <div className="mt-4 border-t border-border-dark pt-4">
          <PoweredByStripe />
        </div>
      </form>

      <aside className="h-fit rounded-2xl border border-border-dark bg-page p-6 text-sm">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-fg-faint">Resumo do pedido</div>
        <div className="mt-3 flex items-center gap-2">
          <span className="material-symbols-outlined text-secondary text-[20px]">workspace_premium</span>
          <span className="font-semibold text-fg-strong">studIA Pro</span>
        </div>
        <div className="mt-4 flex justify-between text-fg-muted">
          <span>Assinatura {intervalo === "year" ? "anual" : "mensal"}</span>
          <span className="text-fg-strong">{valorHoje}</span>
        </div>
        <div className="mt-3 flex justify-between border-t border-border-dark pt-3">
          <span className="font-semibold text-fg-strong">Total hoje</span>
          <span className="text-lg font-extrabold text-fg-strong">{valorHoje}</span>
        </div>
        <p className="mt-4 text-xs text-fg-faint">
          Renova automaticamente {intervalo === "year" ? "a cada ano" : "todo mês"} até você cancelar. Gerencie ou cancele quando quiser na sua conta.
        </p>
        <ul className="mt-5 space-y-2 border-t border-border-dark pt-4">
          {[...BENEFICIOS_PRO].slice(0, 4).map((b) => (
            <li key={b} className="flex items-start gap-2 text-xs text-fg-muted">
              <span className="material-symbols-outlined text-primary text-[16px]">check_circle</span>{b}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

function AssinarInner() {
  const params = useSearchParams();
  const statusParam = params.get("status"); // sucesso | cancelado

  const [checkingOut, setCheckingOut] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const [cupom, setCupom] = useState("");
  const [resgatando, setResgatando] = useState(false);
  const [erroCupom, setErroCupom] = useState<string | null>(null);

  const [intervalo, setIntervalo] = useState<"month" | "year">("month");
  const [clientSecret, setClientSecret] = useState<string | null>(null);

  // Após voltar do checkout (sucesso), o webhook pode demorar 1-2s — repolla
  // até plano virar "pro" (máx ~20s com intervalo de 4s), então para.
  const {
    data: status,
    isPending: loading,
  } = useQuery<BillingStatus>({
    queryKey: qk.billing(),
    queryFn: () => apiJson<BillingStatus>("/api/billing/status"),
    refetchInterval: (q) => {
      if (statusParam !== "sucesso") return false;
      const data = q.state.data;
      if (!data) return 4000;
      return data.ilimitado ? false : 4000;
    },
  });

  const stripePromise = useMemo(
    () => (status?.publishable_key ? loadStripe(status.publishable_key) : null),
    [status?.publishable_key],
  );

  const precoMensal = status?.preco_label?.split("/")[0] ?? "R$ 29,90";
  const precoAnual = status?.preco_label_anual?.split("/")[0] ?? "R$ 298,80";
  const valorHoje = intervalo === "year" ? precoAnual : precoMensal;

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

  async function resgatarCupom() {
    if (!cupom.trim()) return;
    setErroCupom(null);
    setResgatando(true);
    try {
      await apiPost("/api/vouchers/resgatar", { codigo: cupom.trim() });
      setCupom("");
      await queryClient.invalidateQueries({ queryKey: qk.billing() });
      await queryClient.invalidateQueries({ queryKey: qk.limite() });
    } catch (e) {
      setErroCupom(e instanceof ApiError ? e.message : "Não foi possível resgatar o cupom.");
    } finally {
      setResgatando(false);
    }
  }

  const ilimitado = status?.ilimitado;
  const noPagamento = Boolean(clientSecret) && !ilimitado;

  return (
    <main className="min-h-screen bg-page">
      {/* Cabeçalho enxuto — marca + fio gradiente (assinatura visual do studIA) */}
      <header className="sticky top-0 z-10 border-b border-border-dark bg-page/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-5 py-3.5">
          <Link href="/" className="flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary">workspace_premium</span>
            <span className="text-base font-bold tracking-tight text-fg-strong">studIA</span>
            <span className="rounded-md bg-secondary/15 px-1.5 py-0.5 text-[10px] font-bold text-secondary">PRO</span>
          </Link>
          <Link href="/" className="text-xs text-fg-muted hover:text-fg-strong transition">Fechar</Link>
        </div>
        <div className="h-px w-full bg-linear-to-r from-primary/60 via-secondary/60 to-transparent" />
      </header>

      <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:py-14">
        {statusParam === "sucesso" && (
          <div className="mb-6 flex items-start gap-2 rounded-xl border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
            <span className="material-symbols-outlined text-[18px]">check_circle</span>
            <span>Pagamento confirmado. Ativando sua assinatura — leva só alguns segundos.</span>
          </div>
        )}
        {statusParam === "cancelado" && (
          <div className="mb-6 flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
            <span className="material-symbols-outlined text-[18px]">info</span>
            <span>Pagamento não concluído. Seus dados não foram cobrados — você pode assinar quando quiser.</span>
          </div>
        )}

        {/* Título da etapa */}
        {!noPagamento && !loading && (
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-extrabold tracking-tight text-fg-strong sm:text-3xl">
              {ilimitado ? "Sua assinatura" : "Estude sem limites"}
            </h1>
            {!ilimitado && (
              <p className="mx-auto mt-2 max-w-md text-sm text-fg-muted">
                Resolva questões ilimitadas, acompanhe suas estatísticas e use a IA do studIA sem barreiras.
              </p>
            )}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-20 text-fg-faint">
            <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
            Carregando…
          </div>
        ) : ilimitado ? (
          <div className="mx-auto max-w-md rounded-2xl border border-secondary/30 bg-secondary/5 p-8 text-center">
            <span className="material-symbols-outlined text-secondary text-5xl">verified</span>
            <h2 className="mt-3 text-xl font-bold text-fg-strong">Tudo certo — acesso ilimitado ativo</h2>
            <p className="mt-2 text-sm text-fg-muted">
              {status?.is_admin
                ? "Conta de administrador — sem limite de questões."
                : "Sua assinatura está ativa. Bons estudos!"}
            </p>
            {status?.assinatura?.current_period_end && (
              <p className="mt-4 text-xs text-fg-faint">
                {status.assinatura.cancel_at_period_end ? "Acesso até " : "Renova em "}
                {new Date(status.assinatura.current_period_end).toLocaleDateString("pt-BR")}
              </p>
            )}
            {!status?.assinatura && status?.voucher_pro_ate && (
              <p className="mt-4 text-xs text-fg-faint">
                Acesso via cupom até {new Date(status.voucher_pro_ate).toLocaleDateString("pt-BR")}
              </p>
            )}
            <Link href="/conta" className="mt-6 inline-block rounded-lg border border-border-dark px-4 py-2 text-sm font-semibold text-fg-strong hover:bg-page transition">
              Gerenciar na minha conta
            </Link>
          </div>
        ) : noPagamento ? (
          stripePromise && clientSecret && (
            <CheckoutElementsProvider
              stripe={stripePromise}
              options={{ clientSecret, elementsOptions: { appearance: { theme: "night", labels: "floating", variables: { colorPrimary: "#06b6d4", borderRadius: "10px" } } } }}
            >
              <PagamentoTransparente intervalo={intervalo} valorHoje={valorHoje} onVoltar={() => setClientSecret(null)} />
            </CheckoutElementsProvider>
          )
        ) : (
          <>
            {/* Toggle Mensal/Anual */}
            <div className="mb-7 flex justify-center">
              <div className="inline-flex rounded-full border border-border-dark bg-surface-dark p-1 text-sm">
                <button onClick={() => setIntervalo("month")} className={`rounded-full px-5 py-1.5 transition ${intervalo === "month" ? "bg-primary text-on-primary font-semibold" : "text-fg-muted hover:text-fg-strong"}`}>Mensal</button>
                <button onClick={() => setIntervalo("year")} className={`flex items-center gap-1.5 rounded-full px-5 py-1.5 transition ${intervalo === "year" ? "bg-primary text-on-primary font-semibold" : "text-fg-muted hover:text-fg-strong"}`}>
                  Anual <span className={`rounded-full px-1.5 text-[10px] font-bold ${intervalo === "year" ? "bg-on-primary/20 text-on-primary" : "bg-secondary/20 text-secondary"}`}>{ECONOMIA_ANUAL}</span>
                </button>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {/* Grátis */}
              <div className="rounded-2xl border border-border-dark bg-surface-dark p-6">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-fg-faint">Seu plano</div>
                <div className="mt-1 text-sm font-semibold text-fg-muted">Grátis</div>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold text-fg-strong">R$ 0</span>
                  <span className="text-fg-faint">/sempre</span>
                </div>
                <ul className="mt-5 space-y-2.5">
                  {[...BENEFICIOS_FREE].map((b) => (
                    <li key={b} className="flex items-center gap-2 text-sm text-fg-muted"><span className="material-symbols-outlined text-fg-faint text-[18px]">check</span>{b}</li>
                  ))}
                </ul>
                <div className="mt-6 rounded-lg border border-border-dark py-2.5 text-center text-sm text-fg-faint">Plano atual</div>
              </div>

              {/* Pro */}
              <div className="relative rounded-2xl border-2 border-secondary bg-secondary/5 p-6 shadow-[0_12px_40px_rgba(139,92,246,0.18)]">
                <span className="absolute -top-2.5 right-5 rounded-full bg-secondary px-2.5 py-0.5 text-[10px] font-bold text-white">Recomendado</span>
                <div className="mt-1 text-sm font-semibold text-secondary">Pro</div>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold text-fg-strong">{intervalo === "year" ? PRECO_ANUAL_EQUIV_MES : precoMensal}</span>
                  <span className="text-fg-faint">/mês</span>
                </div>
                {intervalo === "year"
                  ? <p className="mt-1 text-xs text-secondary">{precoAnual} cobrado uma vez por ano · {ECONOMIA_ANUAL}</p>
                  : <p className="mt-1 text-xs text-fg-faint">Cobrado mensalmente</p>}
                {status?.limite && !status.limite.ilimitado && (
                  <p className="mt-2 text-xs text-fg-muted">Você usou {status.limite.usado} de {status.limite.limite} questões grátis hoje.</p>
                )}
                <ul className="mt-5 space-y-2.5">
                  {[...BENEFICIOS_PRO].map((b) => (
                    <li key={b} className="flex items-center gap-2 text-sm text-fg"><span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>{b}</li>
                  ))}
                </ul>
                {erro && (<div className="mt-4 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">{erro}</div>)}
                <button onClick={assinar} disabled={checkingOut || !status?.stripe_configurado} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-secondary py-3 text-sm font-semibold text-white shadow-[0_8px_24px_rgba(139,92,246,0.30)] hover:opacity-90 disabled:opacity-50 transition">
                  {checkingOut && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
                  {checkingOut ? "Abrindo pagamento…" : "Continuar para o pagamento"}
                </button>
                {!status?.stripe_configurado && (
                  <p className="mt-3 text-center text-xs text-warning/80">Pagamentos ainda não configurados neste ambiente.</p>
                )}
                <div className="mt-4"><PoweredByStripe /></div>
              </div>
            </div>

            {/* Resgate de cupom — libera Pro sem pagamento */}
            <div className="mx-auto mt-6 max-w-md rounded-2xl border border-border-dark bg-surface-dark p-6">
              <label htmlFor="cupom" className="flex items-center gap-1 text-xs font-medium text-fg-muted">
                <span className="material-symbols-outlined text-[16px] text-secondary">redeem</span>
                Tem um cupom de acesso?
              </label>
              <div className="mt-2 flex gap-2">
                <input
                  id="cupom"
                  type="text"
                  value={cupom}
                  placeholder="PRO-XXXX-XXXX"
                  onChange={(e) => setCupom(e.target.value.toUpperCase())}
                  onKeyDown={(e) => { if (e.key === "Enter") void resgatarCupom(); }}
                  className="flex-1 rounded-lg bg-page border border-border-dark px-3 py-2 text-sm text-fg-strong font-mono uppercase placeholder:font-sans placeholder:normal-case"
                />
                <button
                  onClick={resgatarCupom}
                  disabled={resgatando || !cupom.trim()}
                  className="flex items-center justify-center gap-1 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50 transition"
                >
                  {resgatando && <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>}
                  {resgatando ? "…" : "Aplicar"}
                </button>
              </div>
              {erroCupom && (
                <div className="mt-2 flex items-start gap-2 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                  <span className="material-symbols-outlined text-[16px]">error</span>
                  <span>{erroCupom}</span>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

export default function AssinarPage() {
  return (
    <Suspense fallback={null}>
      <AssinarInner />
    </Suspense>
  );
}
