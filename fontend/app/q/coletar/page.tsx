"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

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
  status: string;
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
      const r = await fetch(`${API}/api/q/coletar/jobs`, { cache: "no-store" });
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
      const r = await fetch(`${API}/api/q/coletar`, {
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

  return (
    <div className="min-h-screen bg-[#121212] text-gray-200">
      <header className="border-b border-gray-700 px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span>📥</span> Coletar caderno do TecConcursos
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          Cole o link de um caderno do TC. A API cria um job rápido, divide em
          faixas de 200 questões e o worker processa em fila persistente.
        </p>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <div>
          <label className="block text-sm font-semibold mb-2">
            URL ou ID do caderno
          </label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tecconcursos.com.br/questoes/cadernos/95846378"
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500 font-mono"
            disabled={carregando}
          />
          {id && (
            <div className="mt-2 text-xs text-cyan-400">
              ✓ Caderno detectado: <span className="font-mono font-semibold">#{id}</span>
              {knownTotal ? (
                <span className="text-gray-400"> · total conhecido: {knownTotal.toLocaleString("pt-BR")}</span>
              ) : null}
            </div>
          )}
        </div>

        <section className="border border-gray-800 rounded-lg bg-gray-950/70 p-4 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-100">
                Jobs ativos na fila TaskIQ
              </h2>
              <p className="text-xs text-gray-500 mt-1">
                Atualizacao automatica a cada 15s. Aqui voce ve o que ja esta rodando ou bloqueado.
              </p>
            </div>
            <button
              onClick={() => void carregarJobs()}
              disabled={carregandoJobs}
              className="text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-60 px-3 py-2 rounded"
            >
              {carregandoJobs ? "Atualizando..." : "Atualizar"}
            </button>
          </div>

          {erroJobs && (
            <div className="bg-red-950 border border-red-700 rounded p-3 text-sm">
              <strong className="text-red-400">Falha no painel:</strong> {erroJobs}
            </div>
          )}

          {!erroJobs && jobs.length === 0 && !carregandoJobs && (
            <div className="text-sm text-gray-400">
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
                      destaqueAtual ? "border-cyan-600 bg-cyan-950/20" : "border-gray-800 bg-black/20"
                    }`}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <div className="text-sm font-semibold text-gray-100">
                          Caderno #{job.caderno_id}
                          <span className="ml-2 text-cyan-400">Job #{job.job_id}</span>
                        </div>
                        <div className="mt-1 text-xs text-gray-400">
                          Status: {statusTexto(job.status)} · {job.questoes_ok_done.toLocaleString("pt-BR")} / {job.expected_total.toLocaleString("pt-BR")} questoes · {job.done_units}/{job.total_units} faixas
                        </div>
                        {primeiraFaixa && (
                          <div className="mt-2 text-xs text-amber-300">
                            Proxima faixa observada: {faixaResumo(primeiraFaixa)}
                          </div>
                        )}
                        {destaqueAtual && (
                          <div className="mt-2 text-xs text-cyan-300">
                            Esse caderno ja tem job ativo. Nao precisa cadastrar de novo.
                          </div>
                        )}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center text-xs md:min-w-[240px]">
                        <div className="rounded bg-gray-900 px-3 py-2">
                          <div className="text-lg font-semibold text-green-400">{job.done_units}</div>
                          <div className="text-gray-500">Done</div>
                        </div>
                        <div className="rounded bg-gray-900 px-3 py-2">
                          <div className="text-lg font-semibold text-yellow-400">{job.running_units + job.queued_units}</div>
                          <div className="text-gray-500">Fila/Run</div>
                        </div>
                        <div className="rounded bg-gray-900 px-3 py-2">
                          <div className="text-lg font-semibold text-red-400">{job.blocked_units}</div>
                          <div className="text-gray-500">Blocked</div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
                        <span>Progresso por questoes</span>
                        <span>{job.pct_questions_done.toFixed(2)}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-gray-800 overflow-hidden">
                        <div
                          className="h-full bg-cyan-500 transition-all"
                          style={{ width: `${progresso}%` }}
                        />
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-400">
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
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500 font-mono"
            disabled={carregando}
          />
          <div className="mt-2 text-xs text-gray-500">
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
          <span className="text-xs text-gray-500">
            (não bloqueia a tela)
          </span>
        </label>

        <button
          onClick={coletar}
          disabled={!id || carregando || Boolean(jobAtual)}
          className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:cursor-not-allowed px-6 py-3 rounded-lg font-semibold text-base"
        >
          {carregando ? "Criando job…" : jobAtual ? "Caderno ja esta em andamento" : "Iniciar coleta"}
        </button>

        {jobAtual && (
          <div className="bg-amber-950 border border-amber-700 rounded p-4 text-sm text-amber-100">
            <strong className="text-amber-300">Ja existe job ativo para #{jobAtual.caderno_id}.</strong>{" "}
            Acompanhe o card acima. O sistema vai retomar faixas bloqueadas automaticamente; nao cadastre o mesmo caderno de novo.
          </div>
        )}

        {erro && (
          <div className="bg-red-950 border border-red-700 rounded p-4 text-sm">
            <strong className="text-red-400">Erro:</strong> {erro}
          </div>
        )}

        {resultado && (
          <div className="bg-green-950 border border-green-700 rounded-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-green-300">
              Job aceito — caderno #{resultado.caderno_id}
            </h2>
            <p className="text-sm text-gray-300">
              {resultado.message}
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-cyan-400">
                  #{resultado.job_id}
                </div>
                <div className="text-xs text-gray-400">Job</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-green-400">
                  {resultado.total_units}
                </div>
                <div className="text-xs text-gray-400">Faixas</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-yellow-400">
                  {resultado.enqueued_units}
                </div>
                <div className="text-xs text-gray-400">Enfileirada agora</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-violet-400">
                  {statusTexto(resultado.status)}
                </div>
                <div className="text-xs text-gray-400">Status</div>
              </div>
            </div>

            <div className="text-xs text-gray-400 border-t border-green-800 pt-3 space-y-1">
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
                className="text-xs bg-gray-700 hover:bg-gray-600 px-3 py-2 rounded"
              >
                Coletar outro caderno
              </button>
            </div>
          </div>
        )}

        <div className="text-xs text-gray-500 border-t border-gray-800 pt-4">
          <strong className="text-gray-400">Como a dedup funciona:</strong>
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
