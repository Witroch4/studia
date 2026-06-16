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
  const [editarDias, setEditarDias] = useState(30);
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
              {data.usuario.banned && <div className="text-error text-xs">conta banida</div>}
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
              {data.stripe_erro && <div className="text-error">erro: {data.stripe_erro}</div>}
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
              <div className="text-fg-strong text-sm font-medium">Editar tempo (definir validade)</div>
              <p className="text-xs text-fg-muted">Revoga tudo e define o PRO para valer por N dias a partir de agora. <strong>0 = revogar já.</strong> Não depende do Stripe.</p>
              <div className="flex gap-2 items-end">
                <label className="text-xs text-fg-muted flex-1">
                  Dias a partir de agora
                  <input
                    type="number" min={0} max={3650} value={editarDias}
                    onChange={(e) => setEditarDias(Math.max(0, Number(e.target.value) || 0))}
                    className="mt-1 w-full rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong"
                  />
                </label>
                <button
                  disabled={busy}
                  onClick={() => {
                    const msg = editarDias === 0
                      ? "Revogar o PRO deste usuário AGORA?"
                      : `Definir PRO para ${editarDias} dias a partir de agora? (revoga o vigente)`;
                    if (!window.confirm(msg)) return;
                    acao(() => apiPost(`/api/admin/billing/usuarios/${uid}/editar-tempo`, { dias: editarDias }), "Tempo atualizado.");
                  }}
                  className="bg-primary hover:opacity-90 text-on-primary px-4 py-2 rounded text-sm font-semibold disabled:opacity-40"
                >
                  Aplicar
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
                className="w-full bg-error hover:opacity-90 text-white px-4 py-2 rounded text-sm font-semibold disabled:opacity-40"
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
            {erro && <p className="text-sm text-error">{erro}</p>}
          </>
        )}
      </aside>
    </div>
  );
}
