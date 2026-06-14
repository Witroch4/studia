"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import GuiasPanel from "./GuiasPanel";
import { apiFetch } from "@/lib/api";

const KNOWN_TOTALS: Record<string, number> = {
  "95872872": 29774,
  "95872884": 15298,
  "95872821": 22455,
  "95872853": 11364,
};

interface Resultado {
  caderno_id: number;
  expected_total: number;
  job_id: number;
  status: string;
  total_units: number;
  enqueued_units: number;
  message: string;
}

interface FaixaAtiva {
  inicio: number;
  page_size: number;
  status: string;
  attempts: number;
  block_reason: string | null;
  blocked_until: string | null;
  leased_until: string | null;
}

interface JobAtivo {
  job_id: number;
  caderno_id: number;
  caderno_nome: string | null;
  pode_montar: boolean;
  status: string;
  paused: boolean;
  expected_total: number;
  total_units: number;
  done_units: number;
  failed_units: number;
  blocked_units: number;
  pending_units: number;
  queued_units: number;
  running_units: number;
  questoes_ok_done: number;
  pct_units_done: number;
  pct_questions_done: number;
  updated_at: string;
  blocked_ranges: FaixaAtiva[];
  running_ranges: FaixaAtiva[];
  queued_ranges: FaixaAtiva[];
}

function statusTexto(status: string): string {
  switch (status) {
    case "blocked":
      return "Em cooldown";
    case "done":
      return "Concluído";
    case "failed":
      return "Falhou";
    case "running":
      return "Rodando";
    case "queued":
      return "Na fila";
    default:
      return status;
  }
}

function formatarMomento(valor: string | null): string {
  if (!valor) return "-";
  const date = new Date(valor);
  if (Number.isNaN(date.getTime())) return valor;
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "America/Fortaleza",
  }).format(date);
}

function faixaResumo(faixa: FaixaAtiva): string {
  const fim = faixa.inicio + faixa.page_size;
  if (faixa.status === "blocked") {
    return `${faixa.inicio}-${fim} bloqueada ate ${formatarMomento(faixa.blocked_until)}`;
  }
  if (faixa.status === "running") {
    return `${faixa.inicio}-${fim} em execucao`;
  }
  return `${faixa.inicio}-${fim} na fila`;
}

function statusDescricao(resultado: Resultado): string {
  if (resultado.status === "blocked") {
    return "O TC bloqueou temporariamente uma faixa. O supervisor vai tentar de novo a faixa exata depois do cooldown, sem voltar o caderno inteiro.";
  }
  if (resultado.enqueued_units === 0) {
    return "O job já existia ou não havia faixa elegível neste momento. O supervisor segue cuidando da retomada em background.";
  }
  return "A primeira faixa foi enviada. As próximas faixas são liberadas automaticamente conforme cada unidade termina.";
}

export default function ColetarPage() {
  const [url, setUrl] = useState("");
  const [expectedTotalText, setExpectedTotalText] = useState("");
  const [relogin, setRelogin] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [carregandoJobs, setCarregandoJobs] = useState(true);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [erroJobs, setErroJobs] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobAtivo[]>([]);
  const [pausando, setPausando] = useState<number | null>(null);
  const [montando, setMontando] = useState<number | null>(null);
  // Coleta TC é área de administração. Só admin vê os termos/ações de coleta.
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
  const [nomesEdit, setNomesEdit] = useState<Record<number, string>>({});
  const [montados, setMontados] = useState<Record<number, { id: number; nome: string; total: number }>>({});
  const [recoletando, setRecoletando] = useState<number | null>(null);

  async function recoletarCaderno(job: JobAtivo) {
    if (
      !confirm(
        `Re-coletar #${job.caderno_id} para registrar a ordem das ${job.expected_total.toLocaleString("pt-BR")} questões? ` +
          `Vai reprocessar ${job.total_units} faixas no TC (pode demorar). As questões já existem; isso só registra a ordem.`
      )
    )
      return;
    setRecoletando(job.caderno_id);
    setErroJobs(null);
    try {
      const r = await apiFetch(`/api/q/coletar/${job.caderno_id}/recoletar`, {
        method: "POST",
      });
      const d = await r.json().catch(() => null);
      if (!r.ok) setErroJobs(d?.detail || `Falha ao re-coletar (HTTP ${r.status})`);
      else void carregarJobs(true);
    } catch (e) {
      setErroJobs((e as Error).message);
    } finally {
      setRecoletando(null);
    }
  }

  async function montarNaPasta(job: JobAtivo) {
    setMontando(job.caderno_id);
    setErroJobs(null);
    const nome = (nomesEdit[job.caderno_id] ?? job.caderno_nome ?? "").trim();
    try {
      const r = await apiFetch(`/api/q/coletar/${job.caderno_id}/materializar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nome ? { nome } : {}),
      });
      const d = await r.json().catch(() => null);
      if (!r.ok) {
        setErroJobs(d?.detail || `Falha ao montar (HTTP ${r.status})`);
      } else {
        setMontados((prev) => ({ ...prev, [job.caderno_id]: { id: d.id, nome: d.nome, total: d.total } }));
        void carregarJobs(true);
      }
    } catch (e) {
      setErroJobs((e as Error).message);
    } finally {
      setMontando(null);
    }
  }

  async function alternarPausa(job: JobAtivo) {
    setPausando(job.job_id);
    const acao = job.paused ? "retomar" : "pausar";
    try {
      const r = await apiFetch(`/api/q/coletar/jobs/${job.job_id}/${acao}`, {
        method: "POST",
      });
      if (!r.ok) {
        const d = await r.json().catch(() => null);
        setErroJobs(d?.detail || `Falha ao ${acao} (HTTP ${r.status})`);
      } else {
        // Atualização otimista + refresh real.
        setJobs((prev) =>
          prev.map((j) => (j.job_id === job.job_id ? { ...j, paused: !j.paused } : j))
        );
        void carregarJobs(true);
      }
    } catch (e) {
      setErroJobs((e as Error).message);
    } finally {
      setPausando(null);
    }
  }

  function extrairId(s: string): string | null {
    const t = s.trim();
    if (/^\d+$/.test(t)) return t;
    const m = t.match(/cadernos\/(\d+)/);
    return m ? m[1] : null;
  }

  const id = extrairId(url);
  const knownTotal = id ? KNOWN_TOTALS[id] : undefined;
  const expectedTotal = expectedTotalText.trim()
    ? Number(expectedTotalText)
    : knownTotal;
  const jobAtual = id ? jobs.find((job) => String(job.caderno_id) === id) : null;

  async function carregarJobs(silent = false) {
    if (!silent) {
      setCarregandoJobs(true);
    }
    try {
      const r = await apiFetch("/api/q/coletar/jobs", { cache: "no-store" });
      const text = await r.text();
      let data: { jobs?: JobAtivo[] } = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(`HTTP ${r.status}: resposta nao-JSON`);
      }
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}`);
      }
      setJobs(Array.isArray(data.jobs) ? data.jobs : []);
      setErroJobs(null);
    } catch (e: unknown) {
      const err = e as Error;
      setErroJobs(err.message || "Falha carregando jobs ativos.");
    } finally {
      if (!silent) {
        setCarregandoJobs(false);
      }
    }
  }

  useEffect(() => {
    void carregarJobs();
    const timer = window.setInterval(() => {
      void carregarJobs(true);
    }, 15_000);
    return () => window.clearInterval(timer);
  }, []);

  async function coletar() {
    if (!id) {
      setErro("URL inválida. Cole algo como https://www.tecconcursos.com.br/questoes/cadernos/12345");
      return;
    }
    if (!expectedTotal || !Number.isInteger(expectedTotal) || expectedTotal <= 0) {
      setErro("Informe o total esperado do caderno. Ex.: 29774.");
      return;
    }
    setErro(null);
    setResultado(null);
    setCarregando(true);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    try {
      const r = await apiFetch("/api/q/coletar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, relogin, expected_total: expectedTotal }),
        signal: controller.signal,
      });
      const text = await r.text();
      let data: Partial<Resultado> & { detail?: string } = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(`HTTP ${r.status}: resposta não-JSON (${text.slice(0, 160)})`);
      }
      if (!r.ok) {
        setErro(data.detail || data.message || `HTTP ${r.status}`);
      } else {
        setResultado(data as Resultado);
        void carregarJobs(true);
      }
    } catch (e: unknown) {
      const err = e as Error;
      setErro(err.name === "AbortError" ? "Timeout criando job. A tela foi liberada; tente novamente para confirmar o registro." : err.message);
    } finally {
      window.clearTimeout(timeout);
      setCarregando(false);
    }
  }

  // Guard de admin: não-admin não acessa a área de coleta (nem por URL direta).
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
            Esta seção é exclusiva para administradores. Para estudar, escolha um
            guia ou monte um caderno.
          </p>
          <div className="flex justify-center gap-2 pt-2">
            <Link href="/q/guias" className="text-sm bg-primary hover:bg-primary-600 text-on-primary px-4 py-2 rounded font-semibold">
              Ver guias
            </Link>
            <Link href="/q/filtrar" className="text-sm bg-surface-2 hover:bg-fg-strong/6 px-4 py-2 rounded font-semibold">
              Questões
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-page text-fg">
      <header className="border-b border-border px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span>📥</span> Coletar do TecConcursos
        </h1>
        <p className="text-xs text-fg-faint mt-1">
          Importe um guia inteiro ou um caderno avulso. Tudo é coletado pela mesma
          fila persistente (faixas de 200 questões) e fica visível aqui.
        </p>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <GuiasPanel />

        <div className="border-t border-border pt-6">
          <h2 className="text-sm font-semibold text-fg-strong mb-1 flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[18px]">cloud_download</span>
            Coletar caderno avulso
          </h2>
          <p className="text-xs text-fg-faint mb-3">
            Cole o link de um caderno específico do TC (fora de um guia).
          </p>
        </div>

        <div>
          <label className="block text-sm font-semibold mb-2">
            URL ou ID do caderno
          </label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tecconcursos.com.br/questoes/cadernos/95846378"
            className="w-full px-4 py-3 bg-surface-2 border border-border rounded-lg text-sm focus:outline-none focus:border-primary font-mono"
            disabled={carregando}
          />
          {id && (
            <div className="mt-2 text-xs text-primary">
              ✓ Caderno detectado: <span className="font-mono font-semibold">#{id}</span>
              {knownTotal ? (
                <span className="text-fg-muted"> · total conhecido: {knownTotal.toLocaleString("pt-BR")}</span>
              ) : null}
            </div>
          )}
        </div>

        <section className="border border-border rounded-lg bg-page/70 p-4 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-fg-strong">
                Jobs ativos na fila TaskIQ
              </h2>
              <p className="text-xs text-fg-faint mt-1">
                Atualizacao automatica a cada 15s. Aqui voce ve o que ja esta rodando ou bloqueado.
              </p>
            </div>
            <button
              onClick={() => void carregarJobs()}
              disabled={carregandoJobs}
              className="text-xs bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-3 py-2 rounded"
            >
              {carregandoJobs ? "Atualizando..." : "Atualizar"}
            </button>
          </div>

          {erroJobs && (
            <div className="bg-error/10 border border-error/40 rounded p-3 text-sm">
              <strong className="text-error">Falha no painel:</strong> {erroJobs}
            </div>
          )}

          {!erroJobs && jobs.length === 0 && !carregandoJobs && (
            <div className="text-sm text-fg-muted">
              Nenhum job ativo no momento.
            </div>
          )}

          {jobs.length > 0 && (
            <div className="space-y-3">
              {jobs.map((job) => {
                const progresso = Math.max(0, Math.min(100, job.pct_questions_done));
                const destaqueAtual = id && String(job.caderno_id) === id;
                const primeiraFaixa =
                  job.running_ranges[0] ||
                  job.blocked_ranges[0] ||
                  job.queued_ranges[0] ||
                  null;
                return (
                  <div
                    key={job.job_id}
                    className={`rounded-lg border p-4 ${
                      destaqueAtual ? "border-primary bg-primary/10" : "border-border bg-black/20"
                    }`}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <div className="text-sm font-semibold text-fg-strong">
                          {job.caderno_nome ? (
                            <span className="text-primary">{job.caderno_nome}</span>
                          ) : (
                            <>Caderno #{job.caderno_id}</>
                          )}
                          <span className="ml-2 text-primary">Job #{job.job_id}</span>
                        </div>
                        {job.caderno_nome && (
                          <div className="text-[11px] text-fg-faint">Caderno #{job.caderno_id}</div>
                        )}
                        <div className="mt-1 text-xs text-fg-muted">
                          Status: {statusTexto(job.status)}
                          {job.paused && (
                            <span className="ml-1.5 inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/15 px-2 py-0.5 text-[10px] font-bold uppercase text-warning">
                              <span className="material-symbols-outlined text-[12px]">pause</span> Pausado
                            </span>
                          )}
                          {" · "}{job.questoes_ok_done.toLocaleString("pt-BR")} / {job.expected_total.toLocaleString("pt-BR")} questoes · {job.done_units}/{job.total_units} faixas
                        </div>
                        {job.status === "done" && !job.pode_montar ? (
                          <div className="mt-2 flex flex-col gap-1">
                            <button
                              onClick={() => recoletarCaderno(job)}
                              disabled={recoletando === job.caderno_id}
                              className="inline-flex w-fit items-center gap-1 rounded border border-warning/40 bg-warning/15 px-2.5 py-1 text-xs font-medium text-warning transition hover:bg-warning/20 disabled:opacity-50"
                            >
                              <span className={`material-symbols-outlined text-[14px] ${recoletando === job.caderno_id ? "animate-spin" : ""}`}>
                                {recoletando === job.caderno_id ? "progress_activity" : "restart_alt"}
                              </span>
                              Re-coletar (registrar ordem)
                            </button>
                            <span className="text-[11px] text-fg-faint">
                              Coletado antes do registro de ordem — reprocessar habilita “Montar na pasta”.
                            </span>
                          </div>
                        ) : job.status === "done" ? (
                          montados[job.caderno_id] ? (
                            <div className="mt-2 rounded border border-success/40 bg-success/15 p-2 text-xs text-success">
                              <span className="material-symbols-outlined text-[14px] align-middle">check_circle</span>{" "}
                              Montado em <strong>Importados do TC</strong> ·{" "}
                              <a href={`/q/caderno/${montados[job.caderno_id].id}`} className="underline hover:text-success">
                                abrir “{montados[job.caderno_id].nome}” ({montados[job.caderno_id].total} questões)
                              </a>
                            </div>
                          ) : (
                            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                              <input
                                type="text"
                                value={nomesEdit[job.caderno_id] ?? job.caderno_nome ?? ""}
                                onChange={(e) =>
                                  setNomesEdit((prev) => ({ ...prev, [job.caderno_id]: e.target.value }))
                                }
                                placeholder={`Caderno ${job.caderno_id}`}
                                className="w-full sm:w-64 rounded border border-border bg-surface-2 px-2.5 py-1 text-xs focus:border-primary focus:outline-none"
                              />
                              <button
                                onClick={() => montarNaPasta(job)}
                                disabled={montando === job.caderno_id}
                                className="inline-flex items-center gap-1 rounded border border-primary/40 bg-primary/15 px-2.5 py-1 text-xs font-medium text-primary transition hover:bg-primary/20 disabled:opacity-50"
                              >
                                <span className={`material-symbols-outlined text-[14px] ${montando === job.caderno_id ? "animate-spin" : ""}`}>
                                  {montando === job.caderno_id ? "progress_activity" : "create_new_folder"}
                                </span>
                                Montar na pasta
                              </button>
                            </div>
                          )
                        ) : (
                          <div className="mt-2">
                            <button
                              onClick={() => alternarPausa(job)}
                              disabled={pausando === job.job_id}
                              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition disabled:opacity-50 ${
                                job.paused
                                  ? "border border-success/40 bg-success/15 text-success hover:bg-success/20"
                                  : "border border-border bg-surface-2 text-fg hover:bg-fg-strong/6"
                              }`}
                            >
                              <span className={`material-symbols-outlined text-[14px] ${pausando === job.job_id ? "animate-spin" : ""}`}>
                                {pausando === job.job_id ? "progress_activity" : job.paused ? "play_arrow" : "pause"}
                              </span>
                              {job.paused ? "Retomar" : "Pausar"}
                            </button>
                          </div>
                        )}
                        {primeiraFaixa && (
                          <div className="mt-2 text-xs text-warning">
                            Proxima faixa observada: {faixaResumo(primeiraFaixa)}
                          </div>
                        )}
                        {destaqueAtual && (
                          <div className="mt-2 text-xs text-primary">
                            Esse caderno ja tem job ativo. Nao precisa cadastrar de novo.
                          </div>
                        )}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center text-xs md:min-w-[240px]">
                        <div className="rounded bg-page px-3 py-2">
                          <div className="text-lg font-semibold text-success">{job.done_units}</div>
                          <div className="text-fg-faint">Done</div>
                        </div>
                        <div className="rounded bg-page px-3 py-2">
                          <div className="text-lg font-semibold text-warning">{job.running_units + job.queued_units}</div>
                          <div className="text-fg-faint">Fila/Run</div>
                        </div>
                        <div className="rounded bg-page px-3 py-2">
                          <div className="text-lg font-semibold text-error">{job.blocked_units}</div>
                          <div className="text-fg-faint">Blocked</div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="mb-1 flex items-center justify-between text-xs text-fg-muted">
                        <span>Progresso por questoes</span>
                        <span>{job.pct_questions_done.toFixed(2)}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
                        <div
                          className="h-full bg-cyan-500 transition-all"
                          style={{ width: `${progresso}%` }}
                        />
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-fg-muted">
                      <span>Pending: {job.pending_units}</span>
                      <span>Queued: {job.queued_units}</span>
                      <span>Running: {job.running_units}</span>
                      <span>Ultima atualizacao: {formatarMomento(job.updated_at)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <div>
          <label className="block text-sm font-semibold mb-2">
            Total esperado
          </label>
          <input
            type="number"
            inputMode="numeric"
            value={expectedTotalText}
            onChange={(e) => setExpectedTotalText(e.target.value)}
            placeholder={knownTotal ? `${knownTotal}` : "Ex.: 29774"}
            className="w-full px-4 py-3 bg-surface-2 border border-border rounded-lg text-sm focus:outline-none focus:border-primary font-mono"
            disabled={carregando}
          />
          <div className="mt-2 text-xs text-fg-faint">
            Para os quatro cadernos Petrobras conhecidos, o total é preenchido automaticamente.
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={relogin}
            onChange={(e) => setRelogin(e.target.checked)}
            disabled={carregando}
          />
          Refazer login Playwright no worker
          <span className="text-xs text-fg-faint">
            (não bloqueia a tela)
          </span>
        </label>

        <button
          onClick={coletar}
          disabled={!id || carregando || Boolean(jobAtual)}
          className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 disabled:cursor-not-allowed px-6 py-3 rounded-lg font-semibold text-base"
        >
          {carregando ? "Criando job…" : jobAtual ? "Caderno ja esta em andamento" : "Iniciar coleta"}
        </button>

        {jobAtual && (
          <div className="bg-warning/10 border border-warning/40 rounded p-4 text-sm text-fg">
            <strong className="text-warning">Ja existe job ativo para #{jobAtual.caderno_id}.</strong>{" "}
            Acompanhe o card acima. O sistema vai retomar faixas bloqueadas automaticamente; nao cadastre o mesmo caderno de novo.
          </div>
        )}

        {erro && (
          <div className="bg-error/10 border border-error/40 rounded p-4 text-sm">
            <strong className="text-error">Erro:</strong> {erro}
          </div>
        )}

        {resultado && (
          <div className="bg-success/10 border border-success/40 rounded-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-success">
              Job aceito — caderno #{resultado.caderno_id}
            </h2>
            <p className="text-sm text-fg">
              {resultado.message}
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-primary">
                  #{resultado.job_id}
                </div>
                <div className="text-xs text-fg-muted">Job</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-success">
                  {resultado.total_units}
                </div>
                <div className="text-xs text-fg-muted">Faixas</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-warning">
                  {resultado.enqueued_units}
                </div>
                <div className="text-xs text-fg-muted">Enfileirada agora</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-secondary">
                  {statusTexto(resultado.status)}
                </div>
                <div className="text-xs text-fg-muted">Status</div>
              </div>
            </div>

            <div className="text-xs text-fg-muted border-t border-success/30 pt-3 space-y-1">
              <div>
                <strong>Total esperado:</strong> {resultado.expected_total.toLocaleString("pt-BR")} questões.
              </div>
              <div>
                <strong>Fila:</strong> {statusDescricao(resultado)}
              </div>
              <div>
                <strong>UI:</strong> esta tela não acompanha o processamento; o job fica persistido no Postgres/NATS.
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <a
                href="/q/filtrar"
                className="text-xs bg-cyan-700 hover:bg-cyan-600 px-3 py-2 rounded"
              >
                Ver no filtro →
              </a>
              <button
                onClick={() => {
                  setResultado(null);
                  setUrl("");
                }}
                className="text-xs bg-surface-2 hover:bg-fg-strong/6 px-3 py-2 rounded"
              >
                Coletar outro caderno
              </button>
            </div>
          </div>
        )}

        <div className="text-xs text-fg-faint border-t border-border pt-4">
          <strong className="text-fg-muted">Como a dedup funciona:</strong>
          <ul className="list-disc list-inside mt-1 space-y-0.5">
            <li>Cada questão tem <code>id_externo</code> UNIQUE no Postgres</li>
            <li>Coleta usa UPSERT — re-rodar o mesmo caderno apenas atualiza</li>
            <li>O ledger Postgres controla cada faixa por <code>inicio/page_size</code></li>
            <li>Múltiplos cadernos compartilham questões? OK — armazenadas 1x</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
