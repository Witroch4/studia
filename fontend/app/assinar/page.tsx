"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiJson, apiPost, ApiError } from "@/lib/api";

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
  publishable_key: string;
  preco_label: string;
  stripe_configurado: boolean;
};

const BENEFICIOS = [
  "Questões ilimitadas por dia",
  "Estatísticas e comentários do TC em cada questão",
  "Cadernos e filtros sem limite",
  "Acesso a todo o histórico de resoluções",
];

function AssinarInner() {
  const params = useSearchParams();
  const statusParam = params.get("status"); // sucesso | cancelado

  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkingOut, setCheckingOut] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const data = await apiJson<BillingStatus>("/api/billing/status");
      setStatus(data);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar status da assinatura.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // Após voltar do checkout (sucesso), o webhook pode demorar 1-2s — repolla.
  useEffect(() => {
    if (statusParam !== "sucesso") return;
    let tentativas = 0;
    const t = setInterval(() => {
      tentativas += 1;
      carregar();
      if (tentativas >= 5) clearInterval(t);
    }, 2000);
    return () => clearInterval(t);
  }, [statusParam, carregar]);

  async function assinar() {
    setErro(null);
    setCheckingOut(true);
    try {
      const { url } = await apiPost<{ url: string }>("/api/billing/checkout");
      window.location.href = url;
    } catch (e) {
      setCheckingOut(false);
      setErro(e instanceof ApiError ? e.message : "Não foi possível iniciar o checkout.");
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
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-400">
          <span className="material-symbols-outlined text-[18px]">check_circle</span>
          <span>Pagamento confirmado! Ativando sua assinatura… (pode levar alguns segundos)</span>
        </div>
      )}
      {statusParam === "cancelado" && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-400">
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
        </div>
      ) : (
        <div className="rounded-2xl border border-border-dark bg-surface-dark p-8 shadow-xl">
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-extrabold text-fg-strong">{status?.preco_label?.split("/")[0] || "R$ 29,90"}</span>
            <span className="text-fg-faint">/mês</span>
          </div>
          {status?.limite && !status.limite.ilimitado && (
            <p className="mt-2 text-sm text-fg-muted">
              Hoje você usou <strong className="text-fg-strong">{status.limite.usado}</strong> de{" "}
              {status.limite.limite} questões do plano grátis.
            </p>
          )}

          <ul className="mt-6 space-y-3">
            {BENEFICIOS.map((b) => (
              <li key={b} className="flex items-center gap-3 text-sm text-fg">
                <span className="material-symbols-outlined text-primary text-[20px]">check_circle</span>
                {b}
              </li>
            ))}
          </ul>

          {erro && (
            <div className="mt-5 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
              <span className="material-symbols-outlined text-[18px]">error</span>
              <span>{erro}</span>
            </div>
          )}

          <button
            onClick={assinar}
            disabled={checkingOut || !status?.stripe_configurado}
            className="mt-7 w-full flex items-center justify-center gap-2 rounded-lg bg-secondary py-3 text-sm font-semibold text-white shadow-[0_8px_24px_rgba(139,92,246,0.30)] hover:opacity-90 disabled:opacity-50 transition"
          >
            {checkingOut && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
            {checkingOut ? "Redirecionando…" : "Assinar agora"}
          </button>
          {!status?.stripe_configurado && (
            <p className="mt-3 text-center text-xs text-yellow-500/80">
              Pagamentos ainda não configurados neste ambiente.
            </p>
          )}
          <p className="mt-3 text-center text-xs text-fg-faint">
            Pagamento seguro via Stripe · cancele quando quiser
          </p>
        </div>
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
