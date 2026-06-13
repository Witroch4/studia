"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

interface CadernoDetalhe {
  id: number;
  tc_caderno_id: number;
  nome: string;
  total_questoes: number;
  total_capitulos: number;
  ordem: number | null;
  questoes_coletadas: number;
  pct: number;
  caderno_id: number | null;
  status: string;
  job_status: string | null;
  done_units: number | null;
  total_units: number | null;
  blocked_units: number | null;
}

interface GuiaDetalhe {
  id: number;
  tc_guia_id: number;
  nome: string;
  banca: string | null;
  status: string;
  tc_pasta_id: number | null;
  questoes_esperadas: number;
  questoes_coletadas: number;
  pct: number;
  coleta_completa: boolean;
  cadernos: CadernoDetalhe[];
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente",
  collecting: "Coletando",
  blocked: "Em cooldown",
  collected: "Coletado",
  materialized: "Pronto p/ estudo",
};

function statusChip(status: string): string {
  switch (status) {
    case "materialized":
      return "bg-green-900/40 text-green-300 border-green-700";
    case "collected":
      return "bg-cyan-900/40 text-cyan-300 border-cyan-700";
    case "collecting":
      return "bg-yellow-900/40 text-yellow-300 border-yellow-700";
    case "blocked":
      return "bg-red-900/40 text-red-300 border-red-700";
    default:
      return "bg-surface-2 text-fg-muted border-border";
  }
}

export default function GuiaDetalhePage() {
  const params = useParams();
  const guiaId = params.id as string;

  const [guia, setGuia] = useState<GuiaDetalhe | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [acao, setAcao] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [salvando, setSalvando] = useState<number | null>(null);

  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => setIsAdmin(false));
  }, []);

  async function salvarCaderno(tcCadernoId: number) {
    setSalvando(tcCadernoId);
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/q/guias/${guiaId}/materializar`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tc_caderno_id: tcCadernoId }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      if (!data.total) throw new Error("Caderno ainda não terminou de coletar.");
      void carregar(true);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setSalvando(null);
    }
  }

  const carregar = useCallback(
    async (silent = false) => {
      if (!silent) setCarregando(true);
      try {
        const r = await fetch(`${API}/api/q/guias/${guiaId}`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setGuia(await r.json());
        setErro(null);
      } catch (e) {
        setErro((e as Error).message);
      } finally {
        if (!silent) setCarregando(false);
      }
    },
    [guiaId]
  );

  useEffect(() => {
    void carregar();
    const t = window.setInterval(() => void carregar(true), 15_000);
    return () => window.clearInterval(t);
  }, [carregar]);

  async function materializar() {
    setAcao("materializar");
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/q/guias/${guiaId}/materializar`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      const pulados = data.pulados_incompletos
        ? ` (${data.pulados_incompletos} incompletos ainda coletando)`
        : "";
      setMsg(`${data.total} caderno(s) materializado(s) para estudo${pulados}.`);
      void carregar(true);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setAcao(null);
    }
  }

  async function retomarColeta() {
    setAcao("coletar");
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/q/guias/${guiaId}/coletar`, { method: "POST", credentials: "include" });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      setMsg(`${data.enqueued} caderno(s) reenfileirados para coleta.`);
      void carregar(true);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setAcao(null);
    }
  }

  if (carregando && !guia) {
    return <div className="p-8 text-fg-muted">Carregando guia…</div>;
  }
  if (erro && !guia) {
    return <div className="p-8 text-red-400">Erro: {erro}</div>;
  }
  if (!guia) return null;

  const prontos = guia.cadernos.filter((c) => c.status === "materialized").length;

  return (
    <div className="min-h-screen bg-bg-dark text-text-dark">
      <header className="border-b border-border-dark px-6 py-5">
        <Link href="/q/guias" className="text-xs text-fg-faint hover:text-primary">
          ← Guias de Estudos
        </Link>
        <h1 className="text-2xl font-semibold mt-2">{guia.nome}</h1>
        <div className="text-sm text-fg-faint mt-1 flex flex-wrap gap-x-4 gap-y-1">
          {guia.banca && <span>Banca: <strong className="text-fg">{guia.banca}</strong></span>}
          <span>{guia.cadernos.length} cadernos</span>
          <span>
            {isAdmin ? (
              <>
                {guia.questoes_coletadas.toLocaleString("pt-BR")} /{" "}
                {guia.questoes_esperadas.toLocaleString("pt-BR")} questões ({guia.pct.toFixed(1)}%)
              </>
            ) : (
              <>{guia.questoes_coletadas.toLocaleString("pt-BR")} questões</>
            )}
          </span>
          {isAdmin && guia.tc_pasta_id && (
            <a
              href={`https://www.tecconcursos.com.br/questoes/pastas/${guia.tc_pasta_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              Pasta no TC ↗
            </a>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Barra de progresso global + ações */}
        <section className="rounded-xl border border-border-dark bg-surface-dark p-5">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="text-fg font-medium">Progresso geral</span>
            <span className="text-fg-muted">{prontos}/{guia.cadernos.length} prontos para estudo</span>
          </div>
          <div className="h-3 rounded-full bg-surface-2 overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${guia.cadernos.length ? (prontos / guia.cadernos.length) * 100 : 0}%` }}
            />
          </div>
          <div className="flex flex-wrap gap-2 mt-4">
            <button
              onClick={() => void materializar()}
              disabled={acao !== null}
              className="text-sm bg-primary hover:bg-primary-600 disabled:bg-surface-2 px-4 py-2 rounded font-semibold text-on-primary"
            >
              {acao === "materializar" ? "Salvando…" : "Salvar todos os cadernos"}
            </button>
            {isAdmin && (
              <button
                onClick={() => void retomarColeta()}
                disabled={acao !== null}
                className="text-sm bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-4 py-2 rounded font-semibold"
              >
                {acao === "coletar" ? "Reenfileirando…" : "Retomar coleta"}
              </button>
            )}
            <button
              onClick={() => void carregar()}
              className="text-sm bg-surface-2 hover:bg-fg-strong/6 px-4 py-2 rounded"
            >
              Atualizar
            </button>
          </div>
          {msg && <div className="mt-3 text-sm text-cyan-300">{msg}</div>}
        </section>

        {/* Cadernos por matéria */}
        <section>
          <h2 className="text-sm font-semibold text-fg-muted uppercase tracking-wide mb-3">
            Cadernos por matéria
          </h2>
          <div className="space-y-2">
            {guia.cadernos.map((c) => (
              <div
                key={c.id}
                className="rounded-lg border border-border-dark bg-surface-dark p-4 flex flex-col md:flex-row md:items-center gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-fg-strong truncate">{c.nome}</div>
                  <div className="text-xs text-fg-faint mt-0.5">
                    {isAdmin ? (
                      <>
                        {c.questoes_coletadas.toLocaleString("pt-BR")} /{" "}
                        {c.total_questoes.toLocaleString("pt-BR")} questões
                        {c.blocked_units ? ` · ${c.blocked_units} faixa(s) em cooldown` : ""}
                      </>
                    ) : (
                      <>{c.questoes_coletadas.toLocaleString("pt-BR")} questões</>
                    )}
                    {c.total_capitulos > 0 && ` · ${c.total_capitulos} capítulos`}
                  </div>
                  {isAdmin && (
                    <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden mt-2 max-w-md">
                      <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${Math.min(100, c.pct)}%` }}
                      />
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span
                    className={`text-[10px] uppercase font-semibold px-2 py-1 rounded border ${statusChip(
                      c.status
                    )}`}
                  >
                    {STATUS_LABEL[c.status] || c.status}
                  </span>
                  {c.caderno_id ? (
                    <Link
                      href={`/q/caderno/${c.caderno_id}`}
                      className="text-xs bg-primary hover:bg-primary-600 text-on-primary px-3 py-2 rounded font-semibold whitespace-nowrap"
                    >
                      Estudar →
                    </Link>
                  ) : c.status === "collected" || c.job_status === "done" ? (
                    <button
                      onClick={() => void salvarCaderno(c.tc_caderno_id)}
                      disabled={salvando === c.tc_caderno_id}
                      className="text-xs bg-cyan-900/40 hover:bg-cyan-900/60 text-cyan-200 border border-cyan-700 px-3 py-2 rounded font-semibold whitespace-nowrap disabled:opacity-50 inline-flex items-center gap-1"
                    >
                      <span className={`material-symbols-outlined text-[14px] ${salvando === c.tc_caderno_id ? "animate-spin" : ""}`}>
                        {salvando === c.tc_caderno_id ? "progress_activity" : "bookmark_add"}
                      </span>
                      Salvar
                    </button>
                  ) : (
                    <span className="text-xs text-fg-faint w-18 text-center">coletando…</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
