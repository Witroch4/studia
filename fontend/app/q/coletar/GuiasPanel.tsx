"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

interface GuiaCard {
  id: number;
  nome: string;
  banca: string | null;
  status: string;
  cadernos_total: number;
  questoes_esperadas: number;
  questoes_coletadas: number;
  cadernos_materializados: number;
  pct: number;
}

interface BuscaGuia {
  slug: string;
  url: string;
  ano: number | null;
  orgao: string | null;
  banca: string | null;
  data_prova: string | null;
  guia_id: number | null;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente",
  saving: "Salvando",
  collecting: "Coletando",
  done: "Concluído",
  error: "Erro",
};

function statusBadge(s: string): string {
  if (s === "done") return "bg-green-900/40 text-green-300 border-green-700";
  if (s === "collecting") return "bg-cyan-900/40 text-cyan-300 border-cyan-700";
  if (s === "error") return "bg-red-900/40 text-red-300 border-red-700";
  return "bg-surface-2 text-fg border-border";
}

/**
 * Painel de Guias embutido na página Coleta TC — concentra num só lugar a
 * coleta de guias (cadernos+questões) e o acompanhamento. A coleta de cada
 * caderno do guia reusa a mesma fila TaskIQ exibida abaixo em "Jobs ativos".
 */
export default function GuiasPanel() {
  const [guias, setGuias] = useState<GuiaCard[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const [url, setUrl] = useState("");
  const [iniciarColeta, setIniciarColeta] = useState(true);
  const [importando, setImportando] = useState(false);
  const [importandoSlug, setImportandoSlug] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [termo, setTermo] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [resultados, setResultados] = useState<BuscaGuia[]>([]);

  const carregar = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/q/guias`, { cache: "no-store", credentials: "include" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setGuias(Array.isArray(data.guias) ? data.guias : []);
      setErro(null);
    } catch (e) {
      setErro((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void carregar();
    const t = window.setInterval(() => void carregar(), 15_000);
    return () => window.clearInterval(t);
  }, [carregar]);

  async function importar(targetUrl: string, slug?: string) {
    if (!targetUrl.trim()) {
      setMsg("Cole a URL base do guia (ex.: https://www.tecconcursos.com.br/guias/oab-2026).");
      return;
    }
    if (slug) setImportandoSlug(slug);
    else setImportando(true);
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/q/guias/importar`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl.trim(), iniciar_coleta: iniciarColeta }),
      });
      const data = await r.json();
      if (!r.ok) setMsg(data.detail || data.message || `HTTP ${r.status}`);
      else {
        setMsg(`✓ ${data.nome} — ${data.cadernos} cadernos${iniciarColeta ? `, ${data.enqueued} enfileirados` : ""}.`);
        if (!slug) setUrl("");
        void carregar();
        if (termo) void buscar();
      }
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setImportando(false);
      setImportandoSlug(null);
    }
  }

  async function buscar() {
    if (!termo.trim()) return;
    setBuscando(true);
    try {
      const r = await fetch(`${API}/api/q/guias/buscar-tc?termo=${encodeURIComponent(termo.trim())}`, {
        cache: "no-store",
        credentials: "include",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResultados(Array.isArray(data.guias) ? data.guias : []);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBuscando(false);
    }
  }

  return (
    <section className="border border-border rounded-lg bg-page/70 p-4 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-fg-strong flex items-center gap-2">
          <span className="material-symbols-outlined text-cyan-400 text-[18px]">menu_book</span>
          Guias de estudo
        </h2>
        <p className="text-xs text-fg-faint mt-1">
          Importe um guia inteiro do TC pela URL base. Cada caderro do guia é coletado
          pela mesma fila abaixo, e vira um caderno de estudo por matéria.
        </p>
      </div>

      {/* Importar por URL */}
      <div className="flex flex-col md:flex-row gap-2">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.tecconcursos.com.br/guias/oab-2026"
          className="flex-1 px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-cyan-500 font-mono"
          disabled={importando}
        />
        <button
          onClick={() => void importar(url)}
          disabled={importando}
          className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 px-4 py-2 rounded text-sm font-semibold whitespace-nowrap"
        >
          {importando ? "Importando…" : "Importar guia"}
        </button>
      </div>
      <label className="flex items-center gap-2 text-xs text-fg-muted cursor-pointer">
        <input type="checkbox" checked={iniciarColeta} onChange={(e) => setIniciarColeta(e.target.checked)} disabled={importando} />
        Iniciar a coleta das questões logo após importar
      </label>

      {/* Buscar guias no TC */}
      <div className="flex flex-col md:flex-row gap-2">
        <input
          type="text"
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void buscar()}
          placeholder="Buscar guias no TC (ex.: oab, sefaz, trt)"
          className="flex-1 px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-cyan-500"
          disabled={buscando}
        />
        <button
          onClick={() => void buscar()}
          disabled={buscando || !termo.trim()}
          className="bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-4 py-2 rounded text-sm font-semibold whitespace-nowrap"
        >
          {buscando ? "Buscando…" : "Buscar"}
        </button>
      </div>

      {resultados.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {resultados.map((g) => (
            <div key={g.slug} className="rounded border border-border bg-black/30 p-2 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm text-fg truncate">{g.orgao} {g.ano}</div>
                <div className="text-xs text-fg-faint truncate">
                  {g.banca}{g.data_prova ? ` · prova ${g.data_prova.slice(0, 10)}` : ""}
                </div>
              </div>
              {g.guia_id ? (
                <Link href={`/q/guias/${g.guia_id}`} className="text-xs bg-green-900/40 text-green-300 border border-green-700 px-2 py-1 rounded whitespace-nowrap">
                  Importado →
                </Link>
              ) : (
                <button
                  onClick={() => void importar(g.url, g.slug)}
                  disabled={importandoSlug === g.slug}
                  className="text-xs bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 px-2 py-1 rounded font-semibold whitespace-nowrap"
                >
                  {importandoSlug === g.slug ? "…" : "Importar"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {msg && <div className="text-xs text-cyan-300">{msg}</div>}
      {erro && <div className="text-xs text-red-400">Falha ao listar guias: {erro}</div>}

      {/* Guias importados */}
      {guias.length > 0 && (
        <div className="space-y-2 pt-1">
          <div className="text-xs text-fg-faint uppercase tracking-wide">Guias importados</div>
          {guias.map((g) => (
            <Link
              key={g.id}
              href={`/q/guias/${g.id}`}
              className="block rounded border border-border bg-black/20 hover:border-cyan-700 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium text-fg-strong truncate">{g.nome}</div>
                <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${statusBadge(g.status)}`}>
                  {STATUS_LABEL[g.status] || g.status}
                </span>
              </div>
              <div className="mt-1 text-xs text-fg-muted">
                {g.questoes_coletadas.toLocaleString("pt-BR")}/{g.questoes_esperadas.toLocaleString("pt-BR")} questões ·{" "}
                {g.cadernos_materializados}/{g.cadernos_total} cadernos prontos
              </div>
              <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden mt-2">
                <div className="h-full bg-cyan-500 transition-all" style={{ width: `${Math.min(100, g.pct)}%` }} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
