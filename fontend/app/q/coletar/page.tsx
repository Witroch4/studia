"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import GuiasPanel from "./GuiasPanel";
import { apiFetch } from "@/lib/api";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";
import { BrandLoader, Skeleton } from "../../components/ds";

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

interface ColetarJobsResponse {
  jobs: JobAtivo[];
}

interface ComentarioJob {
  job_id: number;
  caderno_id: number;
  status: string;
  paused: boolean;
  total_units: number;
  done_units: number;
  failed_units: number;
  blocked_units: number;
  pending_units: number;
  queued_units: number;
  running_units: number;
  coments_total: number;
  pct_units_done: number;
  updated_at: string;
  created_at: string | null;
  questao_atual: number | null;
}

interface ComentarioEvento {
  questao_id: number;
  id_externo: number | null;
  status: string;
  coments_alunos: number;
  coments_professores: number;
  block_reason: string | null;
  last_error: string | null;
  updated_at: string | null;
}

interface ComentarioJobsResponse {
  jobs: ComentarioJob[];
}

type TcAccountTask = "caderno" | "forum_lazy" | "forum_mass";

const TC_TASK_OPTIONS: { key: TcAccountTask; label: string }[] = [
  { key: "caderno", label: "Questões" },
  { key: "forum_lazy", label: "Fórum lazy" },
  { key: "forum_mass", label: "Fórum em massa" },
];

const DEFAULT_TC_LOGIN_CAPABILITIES: Record<TcAccountTask, boolean> = {
  caderno: true,
  forum_lazy: true,
  forum_mass: true,
};

interface TcAccountStatus {
  id: string;
  email: string;
  source: "runtime" | "env" | "none" | string;
  capabilities: Record<string, boolean>;
  storage_state_exists: boolean;
  storage_state_mtime: string | null;
  storage_state_age_seconds: number | null;
  usage?: Record<string, number>;
}

interface TcAuthStatus {
  ok?: boolean;
  configured: boolean;
  email: string | null;
  source: "runtime" | "env" | "none" | string;
  storage_state_exists: boolean;
  storage_state_mtime: string | null;
  storage_state_age_seconds: number | null;
  storage_state_removed?: boolean;
  accounts?: TcAccountStatus[];
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

function useComentarioEventos(jobId: number | null, ativo: boolean) {
  return useQuery({
    queryKey: ["q", "comentario-eventos", jobId],
    enabled: jobId != null,
    refetchInterval: ativo ? 15000 : false,
    queryFn: async () => {
      const r = await apiFetch(`/api/q/coletar/comentario-jobs/${jobId}/eventos?limit=15`, { cache: "no-store" });
      if (!r.ok) throw new Error("falha");
      return (await r.json()).eventos as ComentarioEvento[];
    },
  });
}

function ritmoEta(job: ComentarioJob): string {
  if (!job.created_at || job.done_units <= 0) return "—";
  const min = (Date.now() - new Date(job.created_at).getTime()) / 60000;
  if (min <= 0) return "—";
  const qpm = job.done_units / min;
  if (qpm <= 0) return "—";
  const restantes = Math.max(0, job.total_units - job.done_units);
  const etaMin = restantes / qpm;
  const h = Math.floor(etaMin / 60), mm = Math.round(etaMin % 60);
  return `${qpm.toFixed(1)} q/min · ~${h > 0 ? `${h}h ` : ""}${mm}m restantes`;
}

function statusIcone(status: string): string {
  switch (status) {
    case "done": return "✓";
    case "running": return "▶";
    case "blocked": return "⛔";
    case "failed": return "✗";
    default: return "…";
  }
}

async function parseApiError(r: Response, fallback: string): Promise<string> {
  const data = await r.json().catch(() => null);
  return data?.detail || data?.message || fallback;
}

function ComentarioJobCard({
  job,
  pausando,
  aberto,
  onToggleDetalhes,
  onAlternarPausa,
}: {
  job: ComentarioJob;
  pausando: number | null;
  aberto: boolean;
  onToggleDetalhes: () => void;
  onAlternarPausa: () => void;
}) {
  const ativo =
    job.status === "running" ||
    job.status === "queued" ||
    job.pending_units > 0 ||
    job.running_units > 0;
  const { data: eventos, isPending: carregandoEventos } = useComentarioEventos(
    aberto ? job.job_id : null,
    ativo
  );
  const progresso = Math.max(0, Math.min(100, job.pct_units_done));

  return (
    <div className="rounded-lg border border-border bg-black/20 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-sm font-semibold text-fg-strong">
            Caderno #{job.caderno_id}
            <span className="ml-2 text-primary">Job #{job.job_id}</span>
          </div>
          <div className="mt-1 text-xs text-fg-muted">
            Status: {statusTexto(job.status)}
            {job.paused && (
              <span className="ml-1.5 inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/15 px-2 py-0.5 text-[10px] font-bold uppercase text-warning">
                <span className="material-symbols-outlined text-[12px]">pause</span> Pausado
              </span>
            )}
            {" · "}{job.done_units}/{job.total_units} questões · {job.coments_total.toLocaleString("pt-BR")} comentários coletados
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {job.status !== "done" && (
              <button
                onClick={onAlternarPausa}
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
            )}
            <button
              onClick={onToggleDetalhes}
              className="inline-flex items-center gap-1 rounded border border-border bg-surface-2 px-2.5 py-1 text-xs font-medium text-fg hover:bg-fg-strong/6"
            >
              <span className="material-symbols-outlined text-[14px]">
                {aberto ? "expand_less" : "expand_more"}
              </span>
              {aberto ? "Ocultar detalhes" : "Ver detalhes"}
            </button>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs md:min-w-45">
          <div className="rounded bg-page px-3 py-2">
            <div className="text-lg font-semibold text-success">{job.done_units}</div>
            <div className="text-fg-faint">Done</div>
          </div>
          <div className="rounded bg-page px-3 py-2">
            <div className="text-lg font-semibold text-warning">{job.running_units + job.queued_units}</div>
            <div className="text-fg-faint">Fila/Run</div>
          </div>
          <div className="rounded bg-page px-3 py-2">
            <div className="text-lg font-semibold text-error">{job.failed_units}</div>
            <div className="text-fg-faint">Falhas</div>
          </div>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between text-xs text-fg-muted">
          <span>Progresso por questões</span>
          <span>{job.pct_units_done.toFixed(2)}%</span>
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
        <span>
          Última atualização:{" "}
          {job.updated_at
            ? new Date(job.updated_at).toLocaleString("pt-BR")
            : "—"}
        </span>
      </div>

      {aberto && (
        <div className="mt-4 border-t border-border pt-4 space-y-3">
          <div className="flex flex-wrap gap-4 text-xs text-fg-muted">
            <span>
              <span className="font-medium text-fg">Questão atual:</span>{" "}
              {job.questao_atual ? `Processando Q#${job.questao_atual}` : "—"}
            </span>
            <span>
              <span className="font-medium text-fg">Ritmo/ETA:</span>{" "}
              {ritmoEta(job)}
            </span>
          </div>

          <div>
            <div className="mb-1 text-xs font-medium text-fg">Últimas questões processadas</div>
            {carregandoEventos && (
              <div className="text-xs text-fg-faint">Carregando…</div>
            )}
            {!carregandoEventos && (!eventos || eventos.length === 0) && (
              <div className="text-xs text-fg-faint">Nenhum evento registrado ainda.</div>
            )}
            {eventos && eventos.length > 0 && (
              <div className="space-y-1">
                {eventos.map((ev, i) => (
                  <div key={i} className="flex flex-wrap items-baseline gap-1 text-xs">
                    <span className="font-mono text-fg-muted">
                      {statusIcone(ev.status)}
                    </span>
                    <span className="text-fg">
                      Q#{ev.id_externo ?? ev.questao_id}
                    </span>
                    <span className="text-fg-muted">
                      +{ev.coments_alunos}/{ev.coments_professores}
                    </span>
                    <span className="text-fg-faint">
                      {ev.updated_at ? formatarMomento(ev.updated_at) : "—"}
                    </span>
                    {ev.block_reason && (
                      <span className="text-error">{ev.block_reason}</span>
                    )}
                    {ev.last_error && (
                      <span className="text-error truncate max-w-xs">{ev.last_error}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ColetarPage() {
  const [url, setUrl] = useState("");
  const [expectedTotalText, setExpectedTotalText] = useState("");
  const [relogin, setRelogin] = useState(false);
  const [tcEmail, setTcEmail] = useState("");
  const [tcSenha, setTcSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [tcLoginCapabilities, setTcLoginCapabilities] = useState<Record<TcAccountTask, boolean>>({
    ...DEFAULT_TC_LOGIN_CAPABILITIES,
  });
  const [carregando, setCarregando] = useState(false);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [erroJobs, setErroJobs] = useState<string | null>(null);
  const [pausando, setPausando] = useState<number | null>(null);
  const [montando, setMontando] = useState<number | null>(null);
  // Coleta TC é área de administração. Só admin vê os termos/ações de coleta.
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const queryClient = useQueryClient();

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
  const [detalhesAbertos, setDetalhesAbertos] = useState<Record<number, boolean>>({});

  const {
    data: tcAuth,
    isPending: carregandoTcAuth,
  } = useQuery<TcAuthStatus>({
    queryKey: qk.tcAuth(),
    enabled: isAdmin === true,
    queryFn: async () => {
      const r = await apiFetch("/api/q/coletar/tc-auth/status", { cache: "no-store" });
      if (!r.ok) throw new Error(await parseApiError(r, `HTTP ${r.status}`));
      return (await r.json()) as TcAuthStatus;
    },
  });

  const loginTc = useMutation<TcAuthStatus, Error, { accountId?: string } | void>({
    mutationFn: async (input) => {
      const email = tcEmail.trim();
      const senha = tcSenha;
      const enviandoNovaCredencial = Boolean(email || senha);
      const r = await apiFetch("/api/q/coletar/tc-auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          input?.accountId
            ? { email: null, password: null, account_id: input.accountId }
            : enviandoNovaCredencial
              ? { email, password: senha, capabilities: tcLoginCapabilities }
              : { email: null, password: null },
        ),
      });
      if (!r.ok) throw new Error(await parseApiError(r, `HTTP ${r.status}`));
      return (await r.json()) as TcAuthStatus;
    },
    onSuccess: (data) => {
      setTcSenha("");
      setTcEmail("");
      queryClient.setQueryData(qk.tcAuth(), data);
    },
  });

  const logoutTc = useMutation<TcAuthStatus, Error, string | undefined>({
    mutationFn: async (accountId) => {
      const suffix = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
      const r = await apiFetch(`/api/q/coletar/tc-auth/session${suffix}`, {
        method: "DELETE",
      });
      if (!r.ok) throw new Error(await parseApiError(r, `HTTP ${r.status}`));
      return (await r.json()) as TcAuthStatus;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(qk.tcAuth(), data);
    },
  });

  const updateTcCapability = useMutation<
    TcAuthStatus,
    Error,
    { accountId: string; task: TcAccountTask; enabled: boolean }
  >({
    mutationFn: async ({ accountId, task, enabled }) => {
      const r = await apiFetch(
        `/api/q/coletar/tc-auth/accounts/${encodeURIComponent(accountId)}/capabilities`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ capabilities: { [task]: enabled } }),
        },
      );
      if (!r.ok) throw new Error(await parseApiError(r, `HTTP ${r.status}`));
      return (await r.json()) as TcAuthStatus;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(qk.tcAuth(), data);
    },
  });

  // Polling dos jobs ativos — refetch enquanto houver algum running/queued/pending.
  const {
    data: jobsData,
    isPending: carregandoJobs,
    refetch: refetchJobs,
  } = useQuery<ColetarJobsResponse>({
    queryKey: qk.coletarJobs(),
    queryFn: async () => {
      const r = await apiFetch("/api/q/coletar/jobs", { cache: "no-store" });
      const text = await r.text();
      let data: ColetarJobsResponse = { jobs: [] };
      try {
        data = text ? JSON.parse(text) : { jobs: [] };
      } catch {
        throw new Error(`HTTP ${r.status}: resposta nao-JSON`);
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return data;
    },
    enabled: isAdmin === true,
    refetchInterval: (q) => {
      const jobs = q.state.data?.jobs ?? [];
      const hasActive = jobs.some(
        (j) => j.status === "running" || j.status === "queued" || j.pending_units > 0 || j.running_units > 0
      );
      return hasActive ? 15000 : false;
    },
  });

  const jobs: JobAtivo[] = jobsData?.jobs ?? [];

  // Polling dos jobs de comentários — refetch enquanto houver algum ativo.
  const {
    data: comentarioJobsData,
    isPending: carregandoComentarioJobs,
    refetch: refetchComentarioJobs,
  } = useQuery<ComentarioJobsResponse>({
    queryKey: qk.comentarioJobs(),
    queryFn: async () => {
      const r = await apiFetch("/api/q/coletar/comentario-jobs", { cache: "no-store" });
      const text = await r.text();
      let data: ComentarioJobsResponse = { jobs: [] };
      try {
        data = text ? JSON.parse(text) : { jobs: [] };
      } catch {
        throw new Error(`HTTP ${r.status}: resposta nao-JSON`);
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return data;
    },
    enabled: isAdmin === true,
    refetchInterval: (q) => {
      const cjobs = q.state.data?.jobs ?? [];
      const hasActive = cjobs.some(
        (j) => j.status === "running" || j.status === "queued" || j.pending_units > 0 || j.running_units > 0
      );
      return hasActive ? 15000 : false;
    },
  });

  const comentarioJobs: ComentarioJob[] = comentarioJobsData?.jobs ?? [];

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
      else await queryClient.invalidateQueries({ queryKey: qk.coletarJobs() });
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
        await queryClient.invalidateQueries({ queryKey: qk.coletarJobs() });
      }
    } catch (e) {
      setErroJobs((e as Error).message);
    } finally {
      setMontando(null);
    }
  }

  async function alternarPausa(job: Pick<JobAtivo, "job_id" | "paused">) {
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
        // Atualização otimista + invalidação real.
        queryClient.setQueryData<ColetarJobsResponse>(qk.coletarJobs(), (prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            jobs: prev.jobs.map((j) =>
              j.job_id === job.job_id ? { ...j, paused: !j.paused } : j
            ),
          };
        });
        await queryClient.invalidateQueries({ queryKey: qk.coletarJobs() });
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
  const contasTc: TcAccountStatus[] = tcAuth?.accounts?.length
    ? tcAuth.accounts
    : tcAuth?.email
      ? [
          {
            id: "legacy",
            email: tcAuth.email,
            source: tcAuth.source,
            capabilities: DEFAULT_TC_LOGIN_CAPABILITIES,
            storage_state_exists: tcAuth.storage_state_exists,
            storage_state_mtime: tcAuth.storage_state_mtime,
            storage_state_age_seconds: tcAuth.storage_state_age_seconds,
            usage: {},
          },
        ]
      : [];
  const novaCredencialTc = Boolean(tcEmail.trim() || tcSenha);
  const loginTcIncompleto = novaCredencialTc && (!tcEmail.trim() || !tcSenha);
  const loginTcAccountId = (loginTc.variables as { accountId?: string } | undefined)?.accountId;
  const podeLoginTc =
    !loginTc.isPending &&
    !loginTcIncompleto &&
    novaCredencialTc;

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
        await queryClient.invalidateQueries({ queryKey: qk.coletarJobs() });
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

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <section className="border border-border rounded-lg bg-page/70 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-fg-strong">
                <span className="material-symbols-outlined text-primary text-[18px]">key</span>
                Contas TC
              </h2>
              <div className="mt-2 min-h-6 text-xs text-fg-faint">
                {carregandoTcAuth ? (
                  <Skeleton className="h-5 w-64" />
                ) : (
                  <span>
                    {contasTc.length ? `${contasTc.length} conta(s) configurada(s)` : "nenhuma conta configurada"}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 overflow-hidden rounded border border-border">
            <div className="hidden grid-cols-[minmax(180px,1fr)_repeat(3,minmax(110px,auto))_auto] gap-2 border-b border-border bg-surface-2/70 px-3 py-2 text-[11px] font-semibold uppercase text-fg-faint md:grid">
              <span>Conta</span>
              {TC_TASK_OPTIONS.map((option) => (
                <span key={option.key}>{option.label}</span>
              ))}
              <span className="text-right">Ações</span>
            </div>

            {carregandoTcAuth ? (
              <div className="space-y-2 p-3">
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
              </div>
            ) : contasTc.length === 0 ? (
              <div className="px-3 py-4 text-sm text-fg-faint">
                Adicione uma conta para liberar coleta de questões e fóruns.
              </div>
            ) : (
              contasTc.map((conta) => {
                const relogandoConta = loginTc.isPending && loginTcAccountId === conta.id;
                const deslogandoConta = logoutTc.isPending && logoutTc.variables === conta.id;
                return (
                  <div
                    key={conta.id}
                    className="grid gap-3 border-b border-border px-3 py-3 last:border-b-0 md:grid-cols-[minmax(180px,1fr)_repeat(3,minmax(110px,auto))_auto] md:items-center"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-fg">{conta.email}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-fg-faint">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-semibold ${
                            conta.storage_state_exists
                              ? "border-success/40 bg-success/15 text-success"
                              : "border-warning/40 bg-warning/15 text-warning"
                          }`}
                        >
                          <span className="material-symbols-outlined text-[13px]">
                            {conta.storage_state_exists ? "verified_user" : "lock_open"}
                          </span>
                          {conta.storage_state_exists ? "Sessão ativa" : "Sessão ausente"}
                        </span>
                        <span>{conta.source === "runtime" ? "UI" : conta.source}</span>
                        {conta.storage_state_mtime && (
                          <span>login: {formatarMomento(conta.storage_state_mtime)}</span>
                        )}
                      </div>
                    </div>

                    {TC_TASK_OPTIONS.map((option) => (
                      <label
                        key={option.key}
                        className="inline-flex items-center justify-between gap-2 text-xs text-fg md:justify-start"
                      >
                        <span className="md:hidden">{option.label}</span>
                        <span className="inline-flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={conta.capabilities?.[option.key] !== false}
                            disabled={
                              conta.id === "legacy" ||
                              updateTcCapability.isPending ||
                              carregandoTcAuth
                            }
                            onChange={(e) =>
                              updateTcCapability.mutate({
                                accountId: conta.id,
                                task: option.key,
                                enabled: e.currentTarget.checked,
                              })
                            }
                            className="h-4 w-4 rounded border-border accent-primary"
                          />
                          <span className="font-mono text-[11px] text-fg-faint">
                            {conta.usage?.[option.key] ?? 0}
                          </span>
                        </span>
                      </label>
                    ))}

                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => loginTc.mutate({ accountId: conta.id })}
                        disabled={
                          conta.id === "legacy" ||
                          loginTc.isPending ||
                          logoutTc.isPending ||
                          carregandoTcAuth
                        }
                        className="inline-flex h-8 items-center justify-center gap-1 rounded border border-border bg-surface-2 px-2 text-xs font-medium text-fg transition hover:bg-fg-strong/6 disabled:opacity-50"
                      >
                        <span className={`material-symbols-outlined text-[14px] ${relogandoConta ? "animate-spin" : ""}`}>
                          {relogandoConta ? "progress_activity" : "sync"}
                        </span>
                        Refazer
                      </button>
                      <button
                        type="button"
                        onClick={() => logoutTc.mutate(conta.id)}
                        disabled={
                          conta.id === "legacy" ||
                          logoutTc.isPending ||
                          loginTc.isPending ||
                          carregandoTcAuth ||
                          !conta.storage_state_exists
                        }
                        className="inline-flex h-8 items-center justify-center gap-1 rounded border border-border bg-surface-2 px-2 text-xs font-medium text-fg transition hover:bg-fg-strong/6 disabled:opacity-50"
                      >
                        <span className={`material-symbols-outlined text-[14px] ${deslogandoConta ? "animate-spin" : ""}`}>
                          {deslogandoConta ? "progress_activity" : "logout"}
                        </span>
                        Sair
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-fg-muted">Email</span>
              <input
                type="email"
                autoComplete="username"
                autoCapitalize="none"
                value={tcEmail}
                onChange={(e) => setTcEmail(e.target.value)}
                placeholder={tcAuth?.email || "email do TecConcursos"}
                className="h-10 w-full rounded border border-border bg-surface-2 px-3 text-sm text-fg focus:border-primary focus:outline-none"
                disabled={loginTc.isPending}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-fg-muted">Senha</span>
              <div className="flex h-10 rounded border border-border bg-surface-2 focus-within:border-primary">
                <input
                  type={mostrarSenha ? "text" : "password"}
                  autoComplete="current-password"
                  value={tcSenha}
                  onChange={(e) => setTcSenha(e.target.value)}
                  placeholder="senha do TC"
                  className="min-w-0 flex-1 bg-transparent px-3 text-sm text-fg focus:outline-none"
                  disabled={loginTc.isPending}
                />
                <button
                  type="button"
                  onClick={() => setMostrarSenha((v) => !v)}
                  className="grid w-10 place-items-center text-fg-muted hover:text-fg"
                  aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
                >
                  <span className="material-symbols-outlined text-[18px]">
                    {mostrarSenha ? "visibility_off" : "visibility"}
                  </span>
                </button>
              </div>
            </label>
            <button
              type="button"
              onClick={() => loginTc.mutate()}
              disabled={!podeLoginTc}
              className="mt-5 inline-flex h-10 items-center justify-center gap-1 rounded bg-primary px-4 text-sm font-semibold text-on-primary transition hover:bg-primary-600 disabled:bg-surface-2 disabled:text-fg-faint"
            >
              <span className={`material-symbols-outlined text-[16px] ${loginTc.isPending ? "animate-spin" : ""}`}>
                {loginTc.isPending ? "progress_activity" : "login"}
              </span>
              Entrar e salvar
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold text-fg-faint">Permissões da conta</span>
            {TC_TASK_OPTIONS.map((option) => (
              <label key={option.key} className="inline-flex items-center gap-2 text-xs text-fg-muted">
                <input
                  type="checkbox"
                  checked={tcLoginCapabilities[option.key]}
                  onChange={(e) =>
                    setTcLoginCapabilities((atual) => ({
                      ...atual,
                      [option.key]: e.currentTarget.checked,
                    }))
                  }
                  className="h-4 w-4 rounded border-border accent-primary"
                  disabled={loginTc.isPending}
                />
                {option.label}
              </label>
            ))}
          </div>

          <div className="mt-3 min-h-20">
            {loginTc.isPending && (
              <BrandLoader
                size={24}
                className="items-start gap-1 py-1 text-left"
                label="Entrando no TC…"
              />
            )}
            {!loginTc.isPending && loginTc.error && (
              <div className="rounded border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                {loginTc.error.message}
              </div>
            )}
            {!loginTc.isPending && logoutTc.error && (
              <div className="rounded border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                {logoutTc.error.message}
              </div>
            )}
            {!loginTc.isPending && updateTcCapability.error && (
              <div className="rounded border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                {updateTcCapability.error.message}
              </div>
            )}
            {!loginTc.isPending && loginTc.data?.ok && (
              <div className="rounded border border-success/40 bg-success/10 px-3 py-2 text-xs text-success">
                Login TC validado.
              </div>
            )}
            {!loginTc.isPending && logoutTc.data?.ok && !logoutTc.error && (
              <div className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
                Sessão TC removida.
              </div>
            )}
            {!loginTc.isPending && loginTcIncompleto && (
              <div className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
                Preencha email e senha para atualizar a credencial.
              </div>
            )}
          </div>
        </section>

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
                Atualizacao automatica enquanto ha jobs ativos. Aqui voce ve o que ja esta rodando ou bloqueado.
              </p>
            </div>
            <button
              onClick={() => void refetchJobs()}
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
                              Coletado antes do registro de ordem — reprocessar habilita &quot;Montar na pasta&quot;.
                            </span>
                          </div>
                        ) : job.status === "done" ? (
                          montados[job.caderno_id] ? (
                            <div className="mt-2 rounded border border-success/40 bg-success/15 p-2 text-xs text-success">
                              <span className="material-symbols-outlined text-[14px] align-middle">check_circle</span>{" "}
                              Montado em <strong>Importados do TC</strong> ·{" "}
                              <a href={`/q/caderno/${montados[job.caderno_id].id}`} className="underline hover:text-success">
                                abrir &quot;{montados[job.caderno_id].nome}&quot; ({montados[job.caderno_id].total} questões)
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

        {/* Seção: Coleta de comentários */}
        <section className="border border-border rounded-lg bg-page/70 p-4 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-fg-strong">
                Coleta de comentários
              </h2>
              <p className="text-xs text-fg-faint mt-1">
                Jobs de importação de comentários iniciados pela página Minhas Pastas. Atualiza automaticamente enquanto há jobs ativos.
              </p>
            </div>
            <button
              onClick={() => void refetchComentarioJobs()}
              disabled={carregandoComentarioJobs}
              className="text-xs bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-3 py-2 rounded"
            >
              {carregandoComentarioJobs ? "Atualizando..." : "Atualizar"}
            </button>
          </div>

          {comentarioJobs.length === 0 && !carregandoComentarioJobs && (
            <div className="text-sm text-fg-muted">
              Nenhum job de comentários ativo no momento.
            </div>
          )}

          {comentarioJobs.length > 0 && (
            <div className="space-y-3">
              {comentarioJobs.map((job) => (
                <ComentarioJobCard
                  key={job.job_id}
                  job={job}
                  pausando={pausando}
                  aberto={!!detalhesAbertos[job.job_id]}
                  onToggleDetalhes={() =>
                    setDetalhesAbertos((prev) => ({
                      ...prev,
                      [job.job_id]: !prev[job.job_id],
                    }))
                  }
                  onAlternarPausa={() => alternarPausa(job)}
                />
              ))}
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
