"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { apiJson, apiFetch } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";

interface GuiaCard {
  id: number;
  tc_guia_id: number | null;
  nome: string;
  banca: string | null;
  status: string;
  tc_pasta_id: number | null;
  pro_only: boolean;
  bloqueado: boolean;
  cadernos_total: number;
  questoes_esperadas: number;
  questoes_coletadas: number;
  cadernos_materializados: number;
  cadernos_salvos: number;
  coleta_completa: boolean;
  pct: number;
}

interface GuiasResponse {
  guias: GuiaCard[];
}

type Situacao = { label: string; classe: string };

function situacaoGuia(g: GuiaCard, isAdmin: boolean): Situacao {
  // Não-admin: só estados de estudo, nunca termos de coleta.
  if (!isAdmin) {
    return g.cadernos_materializados > 0
      ? { label: "Pronto p/ estudar", classe: "bg-success/15 text-success border-success/40" }
      : { label: "Em breve", classe: "bg-surface-2 text-fg-muted border-border" };
  }
  if (g.cadernos_total > 0 && g.cadernos_materializados >= g.cadernos_total) {
    return { label: "Pronto p/ estudar", classe: "bg-success/15 text-success border-success/40" };
  }
  if (g.coleta_completa) {
    return { label: "Pronto p/ montar", classe: "bg-primary/15 text-primary border-primary/40" };
  }
  return { label: `Coletando ${g.pct.toFixed(0)}%`, classe: "bg-warning/15 text-warning border-warning/40" };
}

export default function GuiasPage() {
  const queryClient = useQueryClient();
  const [isAdmin, setIsAdmin] = useState(false);
  const [busca, setBusca] = useState("");
  const [togglandoPro, setTogglandoPro] = useState<number | null>(null);

  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => setIsAdmin(false));
  }, []);

  // Poll while any guia is still being collected or not yet fully materialized.
  const {
    data,
    isPending: carregando,
    error,
    refetch,
  } = useQuery<GuiasResponse>({
    queryKey: qk.guias(),
    queryFn: () => apiJson<GuiasResponse>("/api/q/guias"),
    refetchInterval: (q) => {
      const guias = q.state.data?.guias ?? [];
      const hasActive = guias.some((g) => !g.coleta_completa && g.status !== "done" && g.status !== "error");
      return hasActive ? 15000 : false;
    },
  });

  const guias: GuiaCard[] = data?.guias ?? [];
  const erro = error ? (error as Error).message || "Falha ao carregar guias." : null;

  async function togglePro(g: GuiaCard, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setTogglandoPro(g.id);
    try {
      const r = await apiFetch(`/api/q/guias/${g.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pro_only: !g.pro_only }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      await queryClient.invalidateQueries({ queryKey: qk.guias() });
    } catch {
      // silencioso — o estado volta no próximo refetch
    } finally {
      setTogglandoPro(null);
    }
  }

  const termo = busca.trim().toLowerCase();
  const guiasFiltrados = termo
    ? guias.filter(
        (g) =>
          g.nome.toLowerCase().includes(termo) ||
          (g.banca || "").toLowerCase().includes(termo)
      )
    : guias;

  return (
    <div className="min-h-screen bg-page text-fg">
      <header className="border-b border-border px-6 py-5">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-3xl">menu_book</span>
          Guias de Estudos
        </h1>
        <p className="text-sm text-fg-faint mt-1">
          Escolha um guia e monte os cadernos por matéria para estudar — cada matéria
          vira um caderno de questões na ordem ideal de estudo.
        </p>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        <section>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
            <h2 className="text-lg font-semibold text-fg-strong">Guias disponíveis</h2>
            <div className="flex items-center gap-2">
              <div className="relative flex-1 sm:w-72">
                <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-faint text-[18px] pointer-events-none">
                  search
                </span>
                <input
                  type="text"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  placeholder="Buscar por guia ou banca…"
                  className="w-full pl-9 pr-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
                />
              </div>
              <button
                onClick={() => void refetch()}
                disabled={carregando}
                className="text-xs bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-3 py-2 rounded whitespace-nowrap"
              >
                {carregando ? "Atualizando…" : "Atualizar"}
              </button>
              {isAdmin && (
                <Link
                  href="/q/admin/pastas"
                  className="text-xs bg-primary hover:bg-primary-600 text-on-primary px-3 py-2 rounded font-semibold whitespace-nowrap inline-flex items-center gap-1"
                >
                  <span className="material-symbols-outlined text-[16px]">add</span>
                  Criar guia
                </Link>
              )}
            </div>
          </div>

          {erro && (
            <div className="bg-error/10 border border-error/40 rounded p-3 text-sm mb-4">
              <strong className="text-error">Falha:</strong> {erro}
            </div>
          )}

          {!erro && guias.length === 0 && !carregando && (
            <div className="text-sm text-fg-faint border border-dashed border-border rounded-lg p-8 text-center">
              Nenhum guia disponível ainda.
            </div>
          )}

          {!erro && guias.length > 0 && guiasFiltrados.length === 0 && (
            <div className="text-sm text-fg-faint border border-dashed border-border rounded-lg p-8 text-center">
              Nenhum guia encontrado para &quot;{busca.trim()}&quot;.
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {guiasFiltrados.map((g) => {
              const sit = situacaoGuia(g, isAdmin);
              return (
                <Link
                  key={g.id}
                  href={`/q/guias/${g.id}`}
                  className="rounded-xl border border-border bg-surface hover:border-primary transition-colors p-5 flex flex-col gap-3"
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`text-[10px] uppercase font-semibold px-2 py-1 rounded border whitespace-nowrap ${sit.classe}`}
                      >
                        {sit.label}
                      </span>
                      {g.pro_only && (
                        <span className="text-[10px] uppercase font-semibold px-2 py-1 rounded border whitespace-nowrap bg-warning/15 text-warning border-warning/40 inline-flex items-center gap-1">
                          <span className="material-symbols-outlined text-[12px]">workspace_premium</span>
                          PRO
                        </span>
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="font-semibold text-fg-strong leading-snug">{g.nome}</div>
                      <div className="text-xs text-fg-faint mt-1">
                        {g.banca ? `Banca: ${g.banca} · ` : ""}
                        {g.cadernos_total} cadernos
                      </div>
                    </div>
                  </div>

                  {isAdmin && (
                    <div
                      onClick={(e) => void togglePro(g, e)}
                      className="flex items-center justify-between gap-2 text-xs rounded-lg border border-border bg-surface-2 px-3 py-2 cursor-pointer hover:border-warning/50"
                    >
                      <span className="flex items-center gap-1.5 text-fg-muted">
                        <span className="material-symbols-outlined text-warning text-[16px]">workspace_premium</span>
                        Exclusivo PRO
                      </span>
                      <span
                        role="switch"
                        aria-checked={g.pro_only}
                        className={`relative h-5 w-9 rounded-full transition-colors shrink-0 ${g.pro_only ? "bg-primary" : "bg-surface border border-border"} ${togglandoPro === g.id ? "opacity-60" : ""}`}
                      >
                        <span className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform ${g.pro_only ? "translate-x-4" : ""}`} />
                      </span>
                    </div>
                  )}

                  {isAdmin ? (
                    <div>
                      <div className="flex items-center justify-between text-xs text-fg-muted mb-1">
                        <span>
                          {g.questoes_coletadas.toLocaleString("pt-BR")} /{" "}
                          {g.questoes_esperadas.toLocaleString("pt-BR")} questões
                        </span>
                        <span>{g.pct.toFixed(1)}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
                        <div
                          className="h-full bg-primary transition-all"
                          style={{ width: `${Math.min(100, g.pct)}%` }}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-fg font-medium">
                      {g.questoes_coletadas.toLocaleString("pt-BR")} questões
                    </div>
                  )}

                  <div className="text-xs text-fg-faint">
                    {g.cadernos_materializados}/{g.cadernos_total} cadernos prontos para estudo
                  </div>
                  {g.cadernos_materializados > 0 && (
                    g.cadernos_salvos > 0 ? (
                      <div className="text-xs text-success flex items-center gap-1">
                        <span className="material-symbols-outlined text-[14px]">bookmark_added</span>
                        {g.cadernos_salvos}/{g.cadernos_materializados} matérias salvas nas suas pastas
                      </div>
                    ) : (
                      <div className="text-xs text-fg-faint flex items-center gap-1">
                        <span className="material-symbols-outlined text-[14px]">bookmark_add</span>
                        Salve matérias para montar suas pastas
                      </div>
                    )
                  )}
                </Link>
              );
            })}
          </div>
        </section>
      </main>
    </div>
  );
}
