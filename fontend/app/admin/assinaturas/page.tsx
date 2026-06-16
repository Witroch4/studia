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
          <p className="text-xs text-error">Stripe não configurado — cancelar/sincronizar e MRR ao vivo indisponíveis.</p>
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
