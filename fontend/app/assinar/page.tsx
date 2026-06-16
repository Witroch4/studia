"use client";

import { Suspense, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { apiJson, apiPost, ApiError } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";
import { loadStripe } from "@stripe/stripe-js";
import { CheckoutElementsProvider, PaymentElement, useCheckoutElements } from "@stripe/react-stripe-js/checkout";
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

function PagamentoTransparente({ intervalo, precoAnual, onVoltar }: { intervalo: "month" | "year"; precoAnual?: string; onVoltar: () => void; }) {
  const checkoutState = useCheckoutElements();
  const [erroPg, setErroPg] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (checkoutState.type === "loading") return <p className="text-fg-faint">Carregando pagamento…</p>;
  if (checkoutState.type === "error") return <p className="text-error">{checkoutState.error.message}</p>;
  const { checkout } = checkoutState;

  async function pagar(e: React.FormEvent) {
    e.preventDefault();
    setErroPg(null);
    setEnviando(true);
    const result = await checkout.confirm();
    if (result.type === "error") {
      setErroPg(result.error.message ?? "Não foi possível confirmar o pagamento.");
      setEnviando(false);
    }
  }

  return (
    <div className="grid gap-6 sm:grid-cols-[1fr_280px]">
      <form onSubmit={pagar} className="rounded-2xl border border-border-dark bg-surface-dark p-6">
        <button type="button" onClick={onVoltar} className="mb-4 text-xs text-secondary">← voltar aos planos</button>
        <h3 className="mb-4 text-sm font-semibold text-fg-strong">Método de pagamento</h3>
        <PaymentElement options={{ layout: { type: "tabs" } }} />
        {erroPg && <div className="mt-4 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">{erroPg}</div>}
        <button type="submit" disabled={enviando} className="mt-5 w-full rounded-lg bg-secondary py-3 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition">{enviando ? "Processando…" : "Assinar"}</button>
        <p className="mt-3 text-center text-xs text-fg-faint">🔒 Protegido pelo Stripe</p>
      </form>
      <aside className="rounded-2xl border border-border-dark bg-page p-5 text-sm">
        <div className="font-semibold text-fg-strong">studIA Pro · {intervalo === "year" ? "Anual" : "Mensal"}</div>
        <div className="mt-3 flex justify-between text-fg-muted"><span>Total hoje</span><strong className="text-fg-strong">{intervalo === "year" ? precoAnual : "R$ 29,90"}</strong></div>
        <p className="mt-3 text-xs text-fg-faint">Renovação {intervalo === "year" ? "anual" : "mensal"} até cancelar.</p>
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
      // Se veio do checkout de sucesso e ainda não é pro/ilimitado, continua polling.
      if (statusParam !== "sucesso") return false;
      const data = q.state.data;
      if (!data) return 4000; // ainda carregando — tenta logo
      return data.ilimitado ? false : 4000;
    },
  });

  const stripePromise = useMemo(
    () => (status?.publishable_key ? loadStripe(status.publishable_key) : null),
    [status?.publishable_key],
  );

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
      // Revalida billing (vira "pro"/ilimitado) e o contador de limite.
      await queryClient.invalidateQueries({ queryKey: qk.billing() });
      await queryClient.invalidateQueries({ queryKey: qk.limite() });
    } catch (e) {
      setErroCupom(e instanceof ApiError ? e.message : "Não foi possível resgatar o cupom.");
    } finally {
      setResgatando(false);
    }
  }

  const ilimitado = status?.ilimitado;

  return (
    <main className="mx-auto w-full max-w-2xl px-5 py-10">
      <div className="flex items-center gap-2 mb-2">
        <span className="material-symbols-outlined text-secondary">workspace_premium</span>
        <h1 className="text-2xl font-bold text-fg-strong">studIA Pro</h1>
      </div>
      <p className="text-fg-muted mb-8">Resolva sem limites e desbloqueie tudo da plataforma.</p>

      {statusParam === "sucesso" && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
          <span className="material-symbols-outlined text-[18px]">check_circle</span>
          <span>Pagamento confirmado! Ativando sua assinatura… (pode levar alguns segundos)</span>
        </div>
      )}
      {statusParam === "cancelado" && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          <span className="material-symbols-outlined text-[18px]">info</span>
          <span>Checkout cancelado. Você pode assinar quando quiser.</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-fg-faint">
          <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
          Carregando…
        </div>
      ) : ilimitado ? (
        <div className="rounded-2xl border border-secondary/30 bg-secondary/5 p-8 text-center">
          <span className="material-symbols-outlined text-secondary text-5xl">verified</span>
          <h2 className="mt-3 text-xl font-bold text-fg-strong">Você já tem acesso ilimitado</h2>
          <p className="mt-2 text-sm text-fg-muted">
            {status?.is_admin
              ? "Conta de administrador — sem limite de questões."
              : "Assinatura ativa. Aproveite os estudos sem limites!"}
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
        </div>
      ) : (
        <>
          {!clientSecret ? (
            <>
              <div className="mb-6 flex justify-center">
                <div className="inline-flex rounded-full border border-border-dark bg-page p-1 text-sm">
                  <button onClick={() => setIntervalo("month")} className={`rounded-full px-4 py-1.5 ${intervalo === "month" ? "bg-primary text-on-primary font-semibold" : "text-fg-muted"}`}>Mensal</button>
                  <button onClick={() => setIntervalo("year")} className={`rounded-full px-4 py-1.5 ${intervalo === "year" ? "bg-primary text-on-primary font-semibold" : "text-fg-muted"}`}>Anual <span className="ml-1 rounded-full bg-secondary/20 px-1.5 text-[10px] text-secondary">{ECONOMIA_ANUAL}</span></button>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-border-dark bg-surface-dark p-6">
                  <div className="text-xs font-semibold text-fg-faint">SEU PLANO</div>
                  <div className="mt-1 text-sm font-semibold text-fg-muted">Grátis</div>
                  <div className="mt-2 text-3xl font-extrabold text-fg-strong">R$0</div>
                  <ul className="mt-5 space-y-2.5">
                    {[...BENEFICIOS_FREE].map((b) => (
                      <li key={b} className="flex items-center gap-2 text-sm text-fg-muted"><span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>{b}</li>
                    ))}
                  </ul>
                  <div className="mt-6 rounded-lg border border-border-dark py-2.5 text-center text-sm text-fg-faint">Plano atual</div>
                </div>
                <div className="relative rounded-2xl border-2 border-secondary bg-secondary/5 p-6 shadow-xl">
                  <span className="absolute -top-2.5 right-5 rounded-full bg-secondary px-2.5 py-0.5 text-[10px] font-bold text-white">RECOMENDADO</span>
                  <div className="mt-1 text-sm font-semibold text-secondary">Pro</div>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-3xl font-extrabold text-fg-strong">{intervalo === "year" ? PRECO_ANUAL_EQUIV_MES : (status?.preco_label?.split("/")[0] ?? "R$ 29,90")}</span>
                    <span className="text-fg-faint">/mês</span>
                  </div>
                  {intervalo === "year" && (<p className="mt-1 text-xs text-fg-faint">{status?.preco_label_anual} cobrado anualmente · {ECONOMIA_ANUAL}</p>)}
                  {status?.limite && !status.limite.ilimitado && (<p className="mt-2 text-xs text-fg-muted">Hoje: {status.limite.usado}/{status.limite.limite} questões grátis.</p>)}
                  <ul className="mt-5 space-y-2.5">
                    {[...BENEFICIOS_PRO].map((b) => (
                      <li key={b} className="flex items-center gap-2 text-sm text-fg"><span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>{b}</li>
                    ))}
                  </ul>
                  {erro && (<div className="mt-4 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">{erro}</div>)}
                  <button onClick={assinar} disabled={checkingOut || !status?.stripe_configurado} className="mt-6 w-full rounded-lg bg-secondary py-3 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition">{checkingOut ? "Carregando…" : "Assinar agora"}</button>
                  {!status?.stripe_configurado && (
                    <p className="mt-3 text-center text-xs text-warning/80">
                      Pagamentos ainda não configurados neste ambiente.
                    </p>
                  )}
                  <p className="mt-3 text-center text-xs text-fg-faint">Pagamento seguro via Stripe · cancele quando quiser</p>
                </div>
              </div>

              {/* Resgate de cupom — libera PRO sem pagamento */}
              <div className="mt-7 rounded-2xl border border-border-dark bg-surface-dark p-6">
                <label htmlFor="cupom" className="text-xs font-medium text-fg-muted flex items-center gap-1">
                  <span className="material-symbols-outlined text-[16px] text-secondary">redeem</span>
                  Tem um cupom?
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
          ) : (
            stripePromise && (
              <CheckoutElementsProvider stripe={stripePromise} options={{ clientSecret, elementsOptions: { appearance: { theme: "night", variables: { colorPrimary: "#06b6d4" } } } }}>
                <PagamentoTransparente intervalo={intervalo} precoAnual={status?.preco_label_anual} onVoltar={() => setClientSecret(null)} />
              </CheckoutElementsProvider>
            )
          )}
        </>
      )}
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
