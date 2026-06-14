"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { apiFetch } from "@/lib/api";

type Job = {
  id: number;
  disciplina: string;
  numero: number;
  titulo: string;
  status: string;
  modelo_usado: string | null;
  erro_msg: string | null;
  created_at: string | null;
  updated_at: string | null;
};

type BatchJob = {
  name: string;
  display_name: string | null;
  state: string;
  create_time: string;
};

const STATUS_CONFIG: Record<string, { bg: string; text: string; icon: string; label: string }> = {
  PENDENTE: { bg: "bg-amber-500/15", text: "text-warning", icon: "schedule", label: "Na Fila" },
  PROCESSANDO: { bg: "bg-primary/15", text: "text-primary", icon: "sync", label: "Processando" },
  CONCLUIDO: { bg: "bg-accent-success/15", text: "text-accent-success", icon: "check_circle", label: "Concluído" },
  ERRO: { bg: "bg-accent-error/15", text: "text-accent-error", icon: "error", label: "Erro" },
};

const BATCH_STATE_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  JOB_STATE_PENDING: { bg: "bg-amber-500/15", text: "text-warning", label: "Pendente" },
  JOB_STATE_RUNNING: { bg: "bg-primary/15", text: "text-primary", label: "Rodando" },
  JOB_STATE_SUCCEEDED: { bg: "bg-accent-success/15", text: "text-accent-success", label: "Concluído" },
  JOB_STATE_FAILED: { bg: "bg-accent-error/15", text: "text-accent-error", label: "Falhou" },
  JOB_STATE_CANCELLED: { bg: "bg-fg-muted/15", text: "text-fg-muted", label: "Cancelado" },
  JOB_STATE_EXPIRED: { bg: "bg-warning/15", text: "text-warning", label: "Expirado (48h)" },
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}min atrás`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h atrás`;
  return `${Math.floor(hrs / 24)}d atrás`;
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [batchJobs, setBatchJobs] = useState<BatchJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [showBatch, setShowBatch] = useState(false);
  const [cancelling, setCancelling] = useState<string | null>(null);
  // Painel de Jobs IA é área de administração (processamento Gemini Batch).
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => setIsAdmin(false));
  }, []);

  const activeJobs = useMemo(
    () => jobs.filter((j) => j.status === "PROCESSANDO" || j.status === "PENDENTE"),
    [jobs]
  );
  const completedJobs = useMemo(() => jobs.filter((j) => j.status === "CONCLUIDO"), [jobs]);
  const errorJobs = useMemo(() => jobs.filter((j) => j.status === "ERRO"), [jobs]);

  const fetchJobs = useCallback(() => {
    apiFetch("/api/jobs")
      .then((r) => r.json())
      .then((data) => setJobs(Array.isArray(data) ? data : []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const fetchBatchJobs = useCallback(() => {
    apiFetch("/api/batch-jobs")
      .then((r) => r.json())
      .then((data) => setBatchJobs(Array.isArray(data) ? data : []))
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!isAdmin) return; // só admin consulta jobs (backend também exige admin)
    fetchJobs();
    // Polling adaptativo: 10s se há jobs ativos, 30s se não
    const interval = setInterval(fetchJobs, activeJobs.length > 0 ? 10000 : 30000);
    return () => clearInterval(interval);
  }, [isAdmin, activeJobs.length, fetchJobs]);

  useEffect(() => {
    if (showBatch && isAdmin) fetchBatchJobs();
  }, [showBatch, isAdmin, fetchBatchJobs]);

  const handleCancel = async (jobName: string) => {
    setCancelling(jobName);
    try {
      const res = await apiFetch(`/api/batch-jobs/${jobName}/cancel`, { method: "POST" });
      if (res.ok) {
        fetchBatchJobs();
        fetchJobs();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setCancelling(null);
    }
  };

  const hasActiveBatch = batchJobs.some(
    (b) => b.state === "JOB_STATE_RUNNING" || b.state === "JOB_STATE_PENDING"
  );

  // Guard de admin: não-admin não acessa o painel de jobs (nem por URL direta).
  if (isAdmin === null) {
    return <div className="p-8 text-fg-muted">Carregando…</div>;
  }
  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-page text-fg flex items-center justify-center px-6">
        <div className="max-w-md text-center space-y-3">
          <span className="material-symbols-outlined text-fg-faint text-5xl">lock</span>
          <h1 className="text-xl font-semibold">Área restrita</h1>
          <p className="text-sm text-fg-faint">
            O painel de Jobs de IA é exclusivo para administradores.
          </p>
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
          <span className="material-symbols-outlined text-primary">monitoring</span>
          Painel de Jobs
        </h1>
        <div className="flex items-center gap-4">
          <button
            onClick={() => { setShowBatch(!showBatch); }}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              showBatch
                ? "bg-primary/15 text-primary border border-primary/30"
                : "bg-surface border border-border text-fg-muted hover:text-fg-strong"
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">cloud</span>
            Batch Jobs Gemini
          </button>
          <div className="flex items-center gap-2 text-xs text-fg-faint">
            <div className="h-2 w-2 rounded-full bg-accent-success animate-pulse" />
            Auto-refresh {activeJobs.length > 0 ? "10s" : "30s"}
          </div>
        </div>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        {/* Stats bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatBadge label="Total" count={jobs.length} icon="list" color="text-fg-muted" />
          <StatBadge label="Ativos" count={activeJobs.length} icon="sync" color="text-primary" pulse={activeJobs.length > 0} />
          <StatBadge label="Concluídos" count={completedJobs.length} icon="check_circle" color="text-accent-success" />
          <StatBadge label="Erros" count={errorJobs.length} icon="error" color="text-accent-error" />
        </div>

        {/* Batch Jobs Gemini (expandível) */}
        {showBatch && (
          <div className="mb-8 bg-surface border border-border rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-border">
              <h2 className="text-sm font-semibold text-fg-strong flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[18px]">cloud</span>
                Batch Jobs na API Gemini
              </h2>
              <button
                onClick={fetchBatchJobs}
                className="text-xs text-fg-muted hover:text-fg-strong flex items-center gap-1 transition-colors"
              >
                <span className="material-symbols-outlined text-[14px]">refresh</span>
                Atualizar
              </button>
            </div>
            {batchJobs.length === 0 ? (
              <p className="px-5 py-4 text-sm text-fg-faint">Nenhum batch job encontrado.</p>
            ) : (
              <div className="divide-y divide-border">
                {batchJobs.map((bj) => {
                  const st = BATCH_STATE_CONFIG[bj.state] || BATCH_STATE_CONFIG.JOB_STATE_PENDING;
                  const isActive = bj.state === "JOB_STATE_RUNNING" || bj.state === "JOB_STATE_PENDING";
                  return (
                    <div key={bj.name} className="px-5 py-3 flex items-center gap-4">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-mono text-fg-muted truncate">{bj.name}</p>
                        {bj.display_name && (
                          <p className="text-xs text-fg-faint">{bj.display_name}</p>
                        )}
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${st.bg} ${st.text}`}>
                        {st.label}
                      </span>
                      {bj.create_time && (
                        <span className="text-[10px] text-fg-faint shrink-0">
                          {timeAgo(bj.create_time)}
                        </span>
                      )}
                      {isActive && (
                        <button
                          onClick={() => handleCancel(bj.name)}
                          disabled={cancelling === bj.name}
                          className="flex items-center gap-1 px-2 py-1 bg-accent-error/15 text-accent-error rounded-md text-[10px] font-medium hover:bg-accent-error/25 transition-colors disabled:opacity-50 shrink-0"
                        >
                          <span className="material-symbols-outlined text-[12px]">
                            {cancelling === bj.name ? "hourglass_empty" : "cancel"}
                          </span>
                          {cancelling === bj.name ? "..." : "Cancelar"}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-surface rounded-xl border border-border p-5 h-20 animate-pulse" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="bg-surface border border-dashed border-border rounded-xl p-12 text-center">
            <span className="material-symbols-outlined text-5xl text-fg-faint mb-4 block">inbox</span>
            <h3 className="text-lg font-bold text-fg-strong mb-2">Nenhum job ainda</h3>
            <p className="text-sm text-fg-muted mb-6">
              Faça upload de um PDF em uma disciplina para iniciar o processamento.
            </p>
            <Link
              href="/disciplinas"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg font-medium transition-all"
            >
              <span className="material-symbols-outlined text-sm">library_books</span>
              Ir para Disciplinas
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Jobs ativos primeiro */}
            {activeJobs.length > 0 && (
              <div className="mb-6">
                <h2 className="text-xs font-semibold text-fg-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                  Em Processamento ({activeJobs.length})
                </h2>
                <div className="space-y-2">
                  {activeJobs.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </div>
              </div>
            )}

            {/* Erros */}
            {errorJobs.length > 0 && (
              <div className="mb-6">
                <h2 className="text-xs font-semibold text-accent-error uppercase tracking-wider mb-3">
                  Erros ({errorJobs.length})
                </h2>
                <div className="space-y-2">
                  {errorJobs.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </div>
              </div>
            )}

            {/* Concluídos */}
            {completedJobs.length > 0 && (
              <div>
                <h2 className="text-xs font-semibold text-fg-muted uppercase tracking-wider mb-3">
                  Concluídos ({completedJobs.length})
                </h2>
                <div className="space-y-2">
                  {completedJobs.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </>
  );
}

function StatBadge({ label, count, icon, color, pulse }: {
  label: string; count: number; icon: string; color: string; pulse?: boolean;
}) {
  return (
    <div className="bg-surface border border-border rounded-xl p-4 flex items-center gap-3">
      <span className={`material-symbols-outlined text-[24px] ${color} ${pulse ? "animate-spin" : ""}`}>
        {icon}
      </span>
      <div>
        <p className="text-2xl font-bold text-fg-strong">{count}</p>
        <p className="text-xs text-fg-faint">{label}</p>
      </div>
    </div>
  );
}

function JobRow({ job }: { job: Job }) {
  const st = STATUS_CONFIG[job.status] || STATUS_CONFIG.PENDENTE;
  const isProcessing = job.status === "PROCESSANDO";

  return (
    <div className={`bg-surface border border-border rounded-xl p-4 flex items-center gap-4 transition-all ${
      isProcessing ? "border-primary/30 shadow-sm shadow-cyan-500/10" : ""
    }`}>
      {/* Status icon */}
      <div className={`h-10 w-10 rounded-lg ${st.bg} flex items-center justify-center shrink-0`}>
        <span className={`material-symbols-outlined text-[20px] ${st.text} ${isProcessing ? "animate-spin" : ""}`}>
          {st.icon}
        </span>
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-sm font-semibold text-fg-strong truncate">
            Aula {String(job.numero).padStart(2, "0")} — {job.titulo}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-fg-faint">{job.disciplina}</span>
          {job.modelo_usado && (
            <span className="text-fg-faint flex items-center gap-1">
              <span className="material-symbols-outlined text-[11px]">smart_toy</span>
              {job.modelo_usado}
            </span>
          )}
          {job.updated_at && (
            <span className="text-fg-faint">{timeAgo(job.updated_at)}</span>
          )}
        </div>
        {job.erro_msg && (
          <p className="text-xs text-accent-error mt-1 truncate">{job.erro_msg}</p>
        )}
      </div>

      {/* Status badge */}
      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${st.bg} ${st.text} shrink-0`}>
        {st.label}
      </span>

      {/* Actions */}
      {job.status === "CONCLUIDO" && (
        <Link
          href={`/disciplinas/${encodeURIComponent(job.disciplina.toLowerCase().replace(/\s+/g, "-"))}/aulas/${job.id}`}
          className="text-primary hover:text-primary/70 transition-colors shrink-0"
          title="Ver aula"
        >
          <span className="material-symbols-outlined">open_in_new</span>
        </Link>
      )}
    </div>
  );
}
