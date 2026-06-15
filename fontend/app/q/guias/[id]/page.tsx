"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { apiFetch, apiJson } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";

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
  salvo: boolean;
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
      return "bg-success/15 text-success border-success/40";
    case "collected":
      return "bg-primary/15 text-primary border-primary/40";
    case "collecting":
      return "bg-warning/15 text-warning border-warning/40";
    case "blocked":
      return "bg-error/15 text-error border-error/40";
    default:
      return "bg-surface-2 text-fg-muted border-border";
  }
}

export default function GuiaDetalhePage() {
  const params = useParams();
  const guiaId = params.id as string;
  const queryClient = useQueryClient();

  const [acao, setAcao] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [salvando, setSalvando] = useState<number | null>(null);
  const [salvandoMateria, setSalvandoMateria] = useState<number | "todas" | null>(null);
  const [editandoNome, setEditandoNome] = useState(false);
  const [nomeRascunho, setNomeRascunho] = useState("");
  const [renomeando, setRenomeando] = useState(false);

  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => setIsAdmin(false));
  }, []);

  // Poll while collection or materialization is still active.
  const {
    data: guia,
    isPending: carregando,
    error,
    refetch,
  } = useQuery<GuiaDetalhe>({
    queryKey: qk.guia(guiaId),
    queryFn: () => apiJson<GuiaDetalhe>(`/api/q/guias/${guiaId}`),
    refetchInterval: (q) => {
      const g = q.state.data;
      if (!g) return false;
      // Poll while collection is incomplete or any caderno is still collecting/blocked.
      const hasActiveCollection = !g.coleta_completa ||
        g.cadernos.some((c) => c.status === "collecting" || c.status === "blocked" || c.status === "pending");
      return hasActiveCollection ? 15000 : false;
    },
  });

  const erro = error ? (error as Error).message : null;

  // Salvar/dessalvar uma matéria nas "Minhas Pastas" do usuário (por usuário).
  async function salvarMateria(c: CadernoDetalhe) {
    setSalvandoMateria(c.tc_caderno_id);
    setMsg(null);
    try {
      const r = c.salvo
        ? await apiFetch(`/api/q/guias/${guiaId}/salvar?tc_caderno_id=${c.tc_caderno_id}`, {
            method: "DELETE",
          })
        : await apiFetch(`/api/q/guias/${guiaId}/salvar`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tc_caderno_id: c.tc_caderno_id }),
          });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      await queryClient.invalidateQueries({ queryKey: qk.guia(guiaId) });
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setSalvandoMateria(null);
    }
  }

  async function salvarTodasMaterias(remover: boolean) {
    setSalvandoMateria("todas");
    setMsg(null);
    try {
      const r = remover
        ? await apiFetch(`/api/q/guias/${guiaId}/salvar`, { method: "DELETE" })
        : await apiFetch(`/api/q/guias/${guiaId}/salvar`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      await queryClient.invalidateQueries({ queryKey: qk.guia(guiaId) });
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setSalvandoMateria(null);
    }
  }

  async function salvarCaderno(tcCadernoId: number) {
    setSalvando(tcCadernoId);
    setMsg(null);
    try {
      const r = await apiFetch(`/api/q/guias/${guiaId}/materializar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tc_caderno_id: tcCadernoId }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      if (!data.total) throw new Error("Caderno ainda não terminou de coletar.");
      await queryClient.invalidateQueries({ queryKey: qk.guia(guiaId) });
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setSalvando(null);
    }
  }

  async function materializar() {
    setAcao("materializar");
    setMsg(null);
    try {
      const r = await apiFetch(`/api/q/guias/${guiaId}/materializar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      const pulados = data.pulados_incompletos
        ? ` (${data.pulados_incompletos} incompletos ainda coletando)`
        : "";
      setMsg(`${data.total} caderno(s) materializado(s) para estudo${pulados}.`);
      await queryClient.invalidateQueries({ queryKey: qk.guia(guiaId) });
      await queryClient.invalidateQueries({ queryKey: qk.guias() });
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setAcao(null);
    }
  }

  async function salvarNome() {
    const novo = nomeRascunho.trim();
    if (!novo || novo === guia?.nome) {
      setEditandoNome(false);
      return;
    }
    setRenomeando(true);
    setMsg(null);
    try {
      const r = await apiFetch(`/api/q/guias/${guiaId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome: novo }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      await queryClient.invalidateQueries({ queryKey: qk.guia(guiaId) });
      await queryClient.invalidateQueries({ queryKey: qk.guias() });
      setEditandoNome(false);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setRenomeando(false);
    }
  }

  async function retomarColeta() {
    setAcao("coletar");
    setMsg(null);
    try {
      const r = await apiFetch(`/api/q/guias/${guiaId}/coletar`, { method: "POST" });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      setMsg(`${data.enqueued} caderno(s) reenfileirados para coleta.`);
      await queryClient.invalidateQueries({ queryKey: qk.guia(guiaId) });
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
    return <div className="p-8 text-error">Erro: {erro}</div>;
  }
  if (!guia) return null;

  const prontos = guia.cadernos.filter((c) => c.status === "materialized").length;
  // Matérias prontas no catálogo (têm caderno) e quantas o usuário já salvou.
  const materializadas = guia.cadernos.filter((c) => c.caderno_id);
  const salvas = materializadas.filter((c) => c.salvo).length;
  const todasSalvas = materializadas.length > 0 && salvas === materializadas.length;

  return (
    <div className="min-h-screen bg-bg-dark text-text-dark">
      <header className="border-b border-border-dark px-6 py-5">
        <Link href="/q/guias" className="text-xs text-fg-faint hover:text-primary">
          ← Guias de Estudos
        </Link>
        {editandoNome ? (
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <input
              autoFocus
              value={nomeRascunho}
              onChange={(e) => setNomeRascunho(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void salvarNome();
                if (e.key === "Escape") setEditandoNome(false);
              }}
              disabled={renomeando}
              className="flex-1 min-w-65 text-2xl font-semibold bg-surface-dark border border-border-dark rounded px-3 py-1.5 text-fg-strong focus:outline-none focus:border-primary disabled:opacity-60"
            />
            <button
              onClick={() => void salvarNome()}
              disabled={renomeando}
              className="text-sm bg-primary hover:bg-primary-600 disabled:bg-surface-2 text-on-primary px-3 py-2 rounded font-semibold"
            >
              {renomeando ? "Salvando…" : "Salvar"}
            </button>
            <button
              onClick={() => setEditandoNome(false)}
              disabled={renomeando}
              className="text-sm bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-3 py-2 rounded"
            >
              Cancelar
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2 mt-2">
            <h1 className="text-2xl font-semibold">{guia.nome}</h1>
            {isAdmin && (
              <button
                onClick={() => {
                  setNomeRascunho(guia.nome);
                  setEditandoNome(true);
                }}
                title="Editar nome do guia"
                className="text-fg-faint hover:text-primary p-1 rounded"
              >
                <span className="material-symbols-outlined text-[20px]">edit</span>
              </button>
            )}
          </div>
        )}
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
        {/* Barra de progresso global + ações — área de administração */}
        {isAdmin && (
          <section className="rounded-xl border border-border-dark bg-surface-dark p-5">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-fg font-medium">Progresso geral</span>
              <span className="text-fg-muted">{prontos}/{guia.cadernos.length} prontos para estudo</span>
            </div>
            {guia.coleta_completa && prontos < guia.cadernos.length && (
              <div className="text-xs text-success mb-2">
                ✓ Coleta concluída — clique em <strong>Salvar todos os cadernos</strong> para liberar o estudo.
              </div>
            )}
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
              <button
                onClick={() => void retomarColeta()}
                disabled={acao !== null}
                className="text-sm bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-4 py-2 rounded font-semibold"
              >
                {acao === "coletar" ? "Reenfileirando…" : "Retomar coleta"}
              </button>
              <button
                onClick={() => void refetch()}
                className="text-sm bg-surface-2 hover:bg-fg-strong/6 px-4 py-2 rounded"
              >
                Atualizar
              </button>
            </div>
            {msg && <div className="mt-3 text-sm text-primary">{msg}</div>}
          </section>
        )}

        {/* Salvar nas Minhas Pastas — por usuário (todo aluno logado) */}
        {materializadas.length > 0 && (
          <section className="rounded-xl border border-border-dark bg-surface-dark p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="text-sm flex items-center gap-1.5">
              <span className="material-symbols-outlined text-primary text-[18px]">
                {salvas > 0 ? "bookmark_added" : "bookmark"}
              </span>
              <span>
                <strong className="text-fg-strong">{salvas}</strong>
                <span className="text-fg-muted"> de {materializadas.length} matérias salvas nas suas pastas</span>
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => void salvarTodasMaterias(false)}
                disabled={salvandoMateria !== null || todasSalvas}
                className="text-sm bg-primary hover:bg-primary-600 disabled:bg-surface-2 disabled:text-fg-faint px-4 py-2 rounded font-semibold text-on-primary"
              >
                {salvandoMateria === "todas" ? "Salvando…" : todasSalvas ? "Todas salvas ✓" : "Salvar todas as matérias"}
              </button>
              {salvas > 0 && (
                <button
                  onClick={() => void salvarTodasMaterias(true)}
                  disabled={salvandoMateria !== null}
                  className="text-sm bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-3 py-2 rounded"
                >
                  Remover todas
                </button>
              )}
            </div>
          </section>
        )}

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
                  {isAdmin ? (
                    <span
                      className={`text-[10px] uppercase font-semibold px-2 py-1 rounded border ${statusChip(
                        c.status
                      )}`}
                    >
                      {STATUS_LABEL[c.status] || c.status}
                    </span>
                  ) : (
                    <span
                      className={`text-[10px] uppercase font-semibold px-2 py-1 rounded border ${
                        c.caderno_id
                          ? "bg-success/15 text-success border-success/40"
                          : "bg-surface-2 text-fg-muted border-border"
                      }`}
                    >
                      {c.caderno_id ? "Pronto p/ estudo" : "Em breve"}
                    </span>
                  )}
                  {c.caderno_id ? (
                    <>
                      <button
                        onClick={() => void salvarMateria(c)}
                        disabled={salvandoMateria !== null}
                        title={c.salvo ? "Remover das Minhas Pastas" : "Salvar nas Minhas Pastas"}
                        className={`text-xs px-3 py-2 rounded font-semibold whitespace-nowrap inline-flex items-center gap-1 border disabled:opacity-50 ${
                          c.salvo
                            ? "bg-success/15 text-success border-success/40 hover:bg-success/20"
                            : "bg-primary/10 text-primary border-primary/40 hover:bg-primary/20"
                        }`}
                      >
                        <span className={`material-symbols-outlined text-[14px] ${salvandoMateria === c.tc_caderno_id ? "animate-spin" : ""}`}>
                          {salvandoMateria === c.tc_caderno_id
                            ? "progress_activity"
                            : c.salvo
                              ? "bookmark_added"
                              : "bookmark_add"}
                        </span>
                        {c.salvo ? "Salvo" : "Salvar"}
                      </button>
                      <Link
                        href={`/q/caderno/${c.caderno_id}`}
                        className="text-xs bg-primary hover:bg-primary-600 text-on-primary px-3 py-2 rounded font-semibold whitespace-nowrap"
                      >
                        Estudar →
                      </Link>
                    </>
                  ) : isAdmin && (c.status === "collected" || c.job_status === "done") ? (
                    <button
                      onClick={() => void salvarCaderno(c.tc_caderno_id)}
                      disabled={salvando === c.tc_caderno_id}
                      className="text-xs bg-primary/15 hover:bg-primary/20 text-primary border border-primary/40 px-3 py-2 rounded font-semibold whitespace-nowrap disabled:opacity-50 inline-flex items-center gap-1"
                    >
                      <span className={`material-symbols-outlined text-[14px] ${salvando === c.tc_caderno_id ? "animate-spin" : ""}`}>
                        {salvando === c.tc_caderno_id ? "progress_activity" : "bookmark_add"}
                      </span>
                      Salvar
                    </button>
                  ) : isAdmin ? (
                    <span className="text-xs text-fg-faint w-18 text-center">coletando…</span>
                  ) : (
                    <span className="text-xs text-fg-faint w-18 text-center">—</span>
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
