"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

interface GuiaCard {
  id: number;
  tc_guia_id: number;
  nome: string;
  banca: string | null;
  status: string;
  tc_pasta_id: number | null;
  cadernos_total: number;
  questoes_esperadas: number;
  questoes_coletadas: number;
  cadernos_materializados: number;
  cadernos_salvos: number;
  coleta_completa: boolean;
  pct: number;
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
  const [guias, setGuias] = useState<GuiaCard[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [busca, setBusca] = useState("");

  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => setIsAdmin(false));
  }, []);

  const carregar = useCallback(async (silent = false) => {
    if (!silent) setCarregando(true);
    try {
      const r = await fetch(`${API}/api/q/guias`, { cache: "no-store", credentials: "include" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setGuias(Array.isArray(data.guias) ? data.guias : []);
      setErro(null);
    } catch (e) {
      setErro((e as Error).message || "Falha ao carregar guias.");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
    const t = window.setInterval(() => void carregar(true), 15_000);
    return () => window.clearInterval(t);
  }, [carregar]);

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
                onClick={() => void carregar()}
                disabled={carregando}
                className="text-xs bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-3 py-2 rounded whitespace-nowrap"
              >
                {carregando ? "Atualizando…" : "Atualizar"}
              </button>
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
              Nenhum guia encontrado para “{busca.trim()}”.
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
                    <span
                      className={`text-[10px] uppercase font-semibold px-2 py-1 rounded border whitespace-nowrap self-start ${sit.classe}`}
                    >
                      {sit.label}
                    </span>
                    <div className="min-w-0">
                      <div className="font-semibold text-fg-strong leading-snug">{g.nome}</div>
                      <div className="text-xs text-fg-faint mt-1">
                        {g.banca ? `Banca: ${g.banca} · ` : ""}
                        {g.cadernos_total} cadernos
                      </div>
                    </div>
                  </div>

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
