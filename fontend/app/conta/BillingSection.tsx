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
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.ilimitado ? "bg-secondary/20 text-secondary" : "bg-border-dark text-fg-muted"}`}>{s.is_admin ? "Admin" : s.ilimitado ? "Pro" : "Grátis"}</span>
      </div>
      {ass?.current_period_end && (<p className="mt-3 text-sm text-fg-muted">{ass.cancel_at_period_end ? "Acesso até " : "Renova em "}{new Date(ass.current_period_end).toLocaleDateString("pt-BR")}</p>)}
      {!ass && s.voucher_pro_ate && (<p className="mt-3 text-sm text-fg-muted">Acesso via cupom até {new Date(s.voucher_pro_ate).toLocaleDateString("pt-BR")}</p>)}
      {erro && <div className="mt-4 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-sm text-error">{erro}</div>}
      <div className="mt-5">
        {s.tem_customer && !s.is_admin ? (
          <button onClick={gerenciar} disabled={abrindo} className="rounded-lg border border-border-dark px-4 py-2 text-sm font-semibold text-fg-strong hover:bg-page disabled:opacity-50 transition">{abrindo ? "Abrindo…" : "Gerenciar assinatura"}</button>
        ) : !s.ilimitado ? (
          <Link href="/assinar" className="inline-block rounded-lg bg-secondary px-4 py-2 text-sm font-semibold text-white hover:opacity-90 transition">Assinar Pro</Link>
        ) : null}
      </div>
    </section>
  );
}
