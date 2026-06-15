"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { apiJson, apiPost, ApiError } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";

type Voucher = {
  id: number;
  codigo: string;
  dias: number;
  status: "disponivel" | "usado";
  resgatado_por_uid: string | null;
  resgatado_por_email: string | null;
  resgatado_em: string | null;
  pro_ate: string | null;
  created_at: string | null;
};

type ListaVouchers = {
  total: number;
  usados: number;
  disponiveis: number;
  vouchers: Voucher[];
};

function fmtData(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export default function VouchersAdminPage() {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const queryClient = useQueryClient();

  // Form de geração
  const [dias, setDias] = useState(365);
  const [quantidade, setQuantidade] = useState(1);
  const [codigo, setCodigo] = useState("");
  const [gerando, setGerando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [gerados, setGerados] = useState<string[]>([]);
  const [copiado, setCopiado] = useState<string | null>(null);

  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => setIsAdmin(false));
  }, []);

  const { data, isPending } = useQuery<ListaVouchers>({
    queryKey: qk.vouchers(),
    queryFn: () => apiJson<ListaVouchers>("/api/vouchers"),
    enabled: isAdmin === true,
  });

  async function gerar() {
    setErro(null);
    setGerando(true);
    setGerados([]);
    try {
      const body: { dias: number; quantidade?: number; codigo?: string } = { dias };
      if (codigo.trim()) body.codigo = codigo.trim();
      else body.quantidade = quantidade;
      const res = await apiPost<{ criados: Voucher[] }>("/api/vouchers", body);
      setGerados(res.criados.map((v) => v.codigo));
      setCodigo("");
      await queryClient.invalidateQueries({ queryKey: qk.vouchers() });
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Não foi possível gerar os vouchers.");
    } finally {
      setGerando(false);
    }
  }

  async function copiar(texto: string, label: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(label);
      setTimeout(() => setCopiado(null), 1500);
    } catch {}
  }

  if (isAdmin === null) {
    return <div className="p-8 text-fg-muted">Carregando…</div>;
  }
  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-page text-fg flex items-center justify-center px-6">
        <div className="max-w-md text-center space-y-3">
          <span className="material-symbols-outlined text-fg-faint text-5xl">lock</span>
          <h1 className="text-xl font-semibold">Área restrita</h1>
          <p className="text-sm text-fg-faint">A gestão de vouchers é exclusiva para administradores.</p>
          <div className="flex justify-center gap-2 pt-2">
            <Link href="/painel" className="text-sm bg-primary hover:bg-primary-600 text-on-primary px-4 py-2 rounded font-semibold">
              Voltar ao início
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <header className="hidden md:flex sticky top-0 z-30 bg-page/80 backdrop-blur-md border-b border-border px-8 py-4 justify-between items-center">
        <h1 className="text-2xl font-bold text-fg-strong flex items-center gap-2">
          <span className="material-symbols-outlined text-secondary">redeem</span>
          Vouchers PRO
        </h1>
        {data && (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-fg-muted">{data.total} total</span>
            <span className="text-accent-success">{data.usados} usados</span>
            <span className="text-primary">{data.disponiveis} disponíveis</span>
          </div>
        )}
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full space-y-8">
        {/* Geração */}
        <section className="bg-surface border border-border rounded-xl p-6">
          <h2 className="text-sm font-semibold text-fg-strong mb-4 flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-secondary">add_circle</span>
            Gerar vouchers
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 items-end">
            <label className="text-xs text-fg-muted">
              Dias de PRO
              <input
                type="number"
                min={1}
                max={3650}
                value={dias}
                onChange={(e) => setDias(Math.max(1, Number(e.target.value) || 0))}
                className="mt-1 w-full rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong"
              />
            </label>
            <label className="text-xs text-fg-muted">
              Quantidade
              <input
                type="number"
                min={1}
                max={200}
                value={quantidade}
                disabled={!!codigo.trim()}
                onChange={(e) => setQuantidade(Math.max(1, Number(e.target.value) || 0))}
                className="mt-1 w-full rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong disabled:opacity-40"
              />
            </label>
            <label className="text-xs text-fg-muted sm:col-span-1">
              Código custom (opcional)
              <input
                type="text"
                value={codigo}
                placeholder="ex: BLACKFRIDAY"
                onChange={(e) => setCodigo(e.target.value.toUpperCase())}
                className="mt-1 w-full rounded-lg bg-page border border-border px-3 py-2 text-sm text-fg-strong font-mono uppercase"
              />
            </label>
            <button
              onClick={gerar}
              disabled={gerando}
              className="flex items-center justify-center gap-2 rounded-lg bg-secondary py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition"
            >
              {gerando && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
              {gerando ? "Gerando…" : "Gerar"}
            </button>
          </div>
          <p className="mt-2 text-xs text-fg-faint">
            Com código custom, gera um único voucher. Sem ele, gera <strong>{quantidade}</strong> código(s) aleatório(s).
          </p>

          {erro && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-accent-error/40 bg-accent-error/10 px-3 py-2 text-sm text-accent-error">
              <span className="material-symbols-outlined text-[18px]">error</span>
              <span>{erro}</span>
            </div>
          )}

          {gerados.length > 0 && (
            <div className="mt-4 rounded-lg border border-accent-success/40 bg-accent-success/10 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-accent-success flex items-center gap-1">
                  <span className="material-symbols-outlined text-[16px]">check_circle</span>
                  {gerados.length} voucher(s) gerado(s)
                </span>
                <button
                  onClick={() => copiar(gerados.join("\n"), "todos")}
                  className="text-xs text-fg-muted hover:text-fg-strong flex items-center gap-1"
                >
                  <span className="material-symbols-outlined text-[14px]">content_copy</span>
                  {copiado === "todos" ? "Copiado!" : "Copiar todos"}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {gerados.map((c) => (
                  <button
                    key={c}
                    onClick={() => copiar(c, c)}
                    title="Copiar"
                    className="font-mono text-sm bg-page border border-border rounded px-2 py-1 text-fg-strong hover:border-primary transition"
                  >
                    {copiado === c ? "Copiado!" : c}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Controle / lista */}
        <section className="bg-surface border border-border rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-fg-strong flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px] text-primary">fact_check</span>
              Controle de resgates
            </h2>
          </div>
          {isPending ? (
            <div className="p-6 space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-page rounded-lg animate-pulse" />
              ))}
            </div>
          ) : !data || data.vouchers.length === 0 ? (
            <p className="px-5 py-8 text-sm text-fg-faint text-center">Nenhum voucher gerado ainda.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-fg-faint border-b border-border">
                    <th className="px-4 py-2 font-medium">Código</th>
                    <th className="px-4 py-2 font-medium">Dias</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Conta</th>
                    <th className="px-4 py-2 font-medium">Resgatado em</th>
                    <th className="px-4 py-2 font-medium">PRO até</th>
                    <th className="px-4 py-2 font-medium">Criado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.vouchers.map((v) => (
                    <tr key={v.id} className="hover:bg-page/50">
                      <td className="px-4 py-2">
                        <button
                          onClick={() => copiar(v.codigo, `row-${v.id}`)}
                          title="Copiar"
                          className="font-mono text-fg-strong hover:text-primary transition"
                        >
                          {copiado === `row-${v.id}` ? "Copiado!" : v.codigo}
                        </button>
                      </td>
                      <td className="px-4 py-2 text-fg-muted">{v.dias}</td>
                      <td className="px-4 py-2">
                        {v.status === "usado" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-accent-success/15 text-accent-success">
                            <span className="material-symbols-outlined text-[12px]">check_circle</span>
                            Usado
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-primary/15 text-primary">
                            <span className="material-symbols-outlined text-[12px]">schedule</span>
                            Disponível
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-fg-muted">{v.resgatado_por_email || "—"}</td>
                      <td className="px-4 py-2 text-fg-faint">{fmtData(v.resgatado_em)}</td>
                      <td className="px-4 py-2 text-fg-faint">{v.pro_ate ? new Date(v.pro_ate).toLocaleDateString("pt-BR") : "—"}</td>
                      <td className="px-4 py-2 text-fg-faint">{fmtData(v.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </>
  );
}
