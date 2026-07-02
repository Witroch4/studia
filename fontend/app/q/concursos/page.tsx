"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { authClient } from "@/lib/auth-client";
import { apiFetch, apiUrl } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { BrandLoader, Skeleton } from "../../components/ds";

// ─── Tipos ───────────────────────────────────────────────

interface FiltroItem {
  key: string;
  name: string;
}

interface FiltrosResponse {
  bancas: FiltroItem[];
  profissoes: FiltroItem[];
}

type TipoFiltro = "BANCA" | "PROFISSAO";

interface FiltroSelecionado {
  id: number;
  tipo: TipoFiltro;
  nome: string;
}

interface ConcursoArquivo {
  id: number;
  tipo: string;
  nome_arquivo: string;
  content_type: string | null;
  tamanho_bytes: number | null;
}

interface Concurso {
  id: number;
  concurso_id_externo: number;
  nome_completo: string;
  url_concurso: string;
  banca_nome: string | null;
  orgao_sigla: string | null;
  orgao_nome: string | null;
  edital_nome: string | null;
  ano: number | null;
  data_aplicacao: string | null;
  escolaridade: string | null;
  arquivos: ConcursoArquivo[];
}

interface ConcursosResponse {
  items: Concurso[];
  total: number;
}

interface JobFiltroRef {
  id: number;
  tipo: string;
}

interface ConcursoJob {
  job_id: number;
  status: string;
  paused: boolean;
  filtros: JobFiltroRef[] | null;
  discovery: string | null;
  total_units: number;
  done_units: number;
  failed_units: number;
  blocked_units: number;
  atualizado_em: string | null;
}

interface ConcursoJobsResponse {
  jobs: ConcursoJob[];
}

// ─── Helpers ─────────────────────────────────────────────

const TIPO_ARQUIVO_LABEL: Record<string, string> = {
  EDITAL: "Edital",
  PROVA_OBJETIVA: "Prova objetiva",
  PROVA_DISCURSIVA: "Prova discursiva",
  GABARITO: "Gabarito",
};

function labelArquivo(tipo: string): string {
  if (TIPO_ARQUIVO_LABEL[tipo]) return TIPO_ARQUIVO_LABEL[tipo];
  return tipo
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (letra) => letra.toUpperCase());
}

function formatarData(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR");
}

function statusTexto(status: string): string {
  switch (status) {
    case "done":
      return "Concluído";
    case "failed":
      return "Falhou";
    case "running":
      return "Rodando";
    case "queued":
      return "Na fila";
    case "pending":
      return "Pendente";
    default:
      return status;
  }
}

function discoveryEmAndamento(discovery: string | null): boolean {
  return discovery === "running" || discovery === "pending";
}

function jobEstaAtivo(job: ConcursoJob): boolean {
  if (discoveryEmAndamento(job.discovery)) return true;
  return job.status === "running" || job.status === "queued" || job.status === "pending";
}

async function parseApiError(r: Response, fallback: string): Promise<string> {
  const data = await r.json().catch(() => null);
  return data?.detail || data?.message || fallback;
}

// ─── Página ──────────────────────────────────────────────

export default function ConcursosPage() {
  // Área de administração — mesma guarda de /q/coletar.
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

  // ── Bloco 1: filtros para nova coleta ───────────────────
  const {
    data: filtrosData,
    isPending: filtrosPending,
    isError: filtrosIsError,
    refetch: refetchFiltros,
  } = useQuery<FiltrosResponse>({
    queryKey: qk.tcConcursoFiltros(),
    enabled: isAdmin === true,
    queryFn: async () => {
      const r = await apiFetch("/api/q/concursos/filtros", { cache: "no-store" });
      if (!r.ok) throw new Error(await parseApiError(r, `HTTP ${r.status}`));
      return (await r.json()) as FiltrosResponse;
    },
    staleTime: 5 * 60 * 1000,
  });

  const bancaPorId = useMemo(() => {
    const m = new Map<number, string>();
    filtrosData?.bancas.forEach((b) => m.set(Number(b.key), b.name));
    return m;
  }, [filtrosData]);

  const profissaoPorId = useMemo(() => {
    const m = new Map<number, string>();
    filtrosData?.profissoes.forEach((p) => m.set(Number(p.key), p.name));
    return m;
  }, [filtrosData]);

  const [buscaBanca, setBuscaBanca] = useState("");
  const [buscaProfissao, setBuscaProfissao] = useState("");
  const [selecionados, setSelecionados] = useState<FiltroSelecionado[]>([]);

  const bancasFiltradas = useMemo(() => {
    if (!filtrosData) return [];
    const termo = buscaBanca.trim().toLowerCase();
    const lista = termo
      ? filtrosData.bancas.filter((b) => b.name.toLowerCase().includes(termo))
      : filtrosData.bancas;
    return lista.slice(0, 50);
  }, [filtrosData, buscaBanca]);

  const profissoesFiltradas = useMemo(() => {
    if (!filtrosData) return [];
    const termo = buscaProfissao.trim().toLowerCase();
    const lista = termo
      ? filtrosData.profissoes.filter((p) => p.name.toLowerCase().includes(termo))
      : filtrosData.profissoes;
    return lista.slice(0, 50);
  }, [filtrosData, buscaProfissao]);

  function estaSelecionado(tipo: TipoFiltro, key: string): boolean {
    return selecionados.some((f) => f.tipo === tipo && f.id === Number(key));
  }

  function alternarFiltro(tipo: TipoFiltro, item: FiltroItem) {
    const id = Number(item.key);
    setSelecionados((prev) => {
      const existe = prev.some((f) => f.tipo === tipo && f.id === id);
      if (existe) return prev.filter((f) => !(f.tipo === tipo && f.id === id));
      return [...prev, { id, tipo, nome: item.name }];
    });
  }

  function removerFiltro(tipo: TipoFiltro, id: number) {
    setSelecionados((prev) => prev.filter((f) => !(f.tipo === tipo && f.id === id)));
  }

  const coletarMutation = useMutation<
    { job_id: number; status: string },
    Error,
    void
  >({
    mutationFn: async () => {
      const r = await apiFetch("/api/q/concursos/coletar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filtros: selecionados.map((f) => ({ id: f.id, tipo: f.tipo })),
        }),
      });
      if (!r.ok) throw new Error(await parseApiError(r, `HTTP ${r.status}`));
      return r.json();
    },
    onSuccess: () => {
      toast.success("Coleta de concursos iniciada — acompanhe abaixo.");
      setSelecionados([]);
      queryClient.invalidateQueries({ queryKey: qk.tcConcursoJobs() });
    },
    onError: (e) => {
      toast.error(`Não foi possível iniciar a coleta: ${e.message}`);
    },
  });

  // ── Bloco 2: jobs ────────────────────────────────────────
  const {
    data: jobsData,
    isPending: jobsPending,
    isError: jobsIsError,
    refetch: refetchJobs,
  } = useQuery<ConcursoJobsResponse>({
    queryKey: qk.tcConcursoJobs(),
    enabled: isAdmin === true,
    queryFn: async () => {
      const r = await apiFetch("/api/q/concursos/jobs", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()) as ConcursoJobsResponse;
    },
    refetchInterval: (q) => {
      const jobs = q.state.data?.jobs ?? [];
      return jobs.some(jobEstaAtivo) ? 15000 : false;
    },
  });

  const jobs = jobsData?.jobs ?? [];
  const temJobAtivo = jobs.some(jobEstaAtivo);

  // ── Bloco 3: listagem ────────────────────────────────────
  const [buscaInput, setBuscaInput] = useState("");
  const [busca, setBusca] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => {
      setBusca(buscaInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [buscaInput]);

  const {
    data: listaData,
    isPending: listaPending,
    isError: listaIsError,
    isFetching: listaFetching,
    refetch: refetchLista,
  } = useQuery<ConcursosResponse>({
    queryKey: qk.tcConcursos(busca, page),
    enabled: isAdmin === true,
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: "50" });
      if (busca) params.set("busca", busca);
      const r = await apiFetch(`/api/q/concursos?${params.toString()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()) as ConcursosResponse;
    },
    placeholderData: keepPreviousData,
  });

  const concursos = listaData?.items ?? [];
  const total = listaData?.total ?? 0;
  const totalPaginas = Math.max(1, Math.ceil(total / 50));

  // ── Guarda de admin ──────────────────────────────────────
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
          <span className="material-symbols-outlined text-primary">domain</span> Concursos
        </h1>
        <p className="text-xs text-fg-faint mt-1">
          Colete concursos por banca ou formação na fonte externa e acompanhe editais,
          provas e gabaritos coletados.
        </p>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Bloco 1: Nova coleta */}
        <section className="border border-border rounded-lg bg-page/70 p-4 space-y-4">
          <h2 className="text-sm font-semibold text-fg-strong flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[18px]">travel_explore</span>
            Nova coleta
          </h2>

          {filtrosPending && (
            <BrandLoader label="Consultando filtros na fonte externa…" />
          )}

          {!filtrosPending && filtrosIsError && (
            <div className="rounded border border-error/40 bg-error/10 px-3 py-3 text-sm text-error flex items-center justify-between gap-3">
              <span>Falha ao carregar bancas/formações.</span>
              <button
                onClick={() => void refetchFiltros()}
                className="text-xs bg-surface-2 hover:bg-fg-strong/6 px-3 py-1.5 rounded font-medium text-fg"
              >
                Tentar de novo
              </button>
            </div>
          )}

          {!filtrosPending && !filtrosIsError && filtrosData && (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <ComboFiltro
                  titulo="Banca"
                  placeholder="Filtrar bancas…"
                  busca={buscaBanca}
                  onBuscaChange={setBuscaBanca}
                  itens={bancasFiltradas}
                  totalDisponivel={filtrosData.bancas.length}
                  isSelecionado={(key) => estaSelecionado("BANCA", key)}
                  onToggle={(item) => alternarFiltro("BANCA", item)}
                />
                <ComboFiltro
                  titulo="Formação"
                  placeholder="Filtrar formações…"
                  busca={buscaProfissao}
                  onBuscaChange={setBuscaProfissao}
                  itens={profissoesFiltradas}
                  totalDisponivel={filtrosData.profissoes.length}
                  isSelecionado={(key) => estaSelecionado("PROFISSAO", key)}
                  onToggle={(item) => alternarFiltro("PROFISSAO", item)}
                />
              </div>

              {selecionados.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {selecionados.map((f) => (
                    <span
                      key={`${f.tipo}-${f.id}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-1 text-xs text-primary"
                    >
                      <span className="text-[10px] uppercase text-primary/70">
                        {f.tipo === "BANCA" ? "Banca" : "Formação"}
                      </span>
                      {f.nome}
                      <button
                        type="button"
                        onClick={() => removerFiltro(f.tipo, f.id)}
                        aria-label={`Remover ${f.nome}`}
                        className="text-primary/70 hover:text-primary"
                      >
                        <span className="material-symbols-outlined text-[14px] align-middle">close</span>
                      </button>
                    </span>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => coletarMutation.mutate()}
                  disabled={selecionados.length === 0 || coletarMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded bg-primary px-4 py-2 text-sm font-semibold text-on-primary transition hover:bg-primary-600 disabled:bg-surface-2 disabled:text-fg-faint"
                >
                  <span className={`material-symbols-outlined text-[16px] ${coletarMutation.isPending ? "animate-spin" : ""}`}>
                    {coletarMutation.isPending ? "progress_activity" : "cloud_download"}
                  </span>
                  Coletar
                </button>
                {selecionados.length === 0 && (
                  <span className="text-xs text-fg-faint">Selecione ao menos uma banca ou formação.</span>
                )}
              </div>
            </>
          )}
        </section>

        {/* Bloco 2: Jobs */}
        <section className="border border-border rounded-lg bg-page/70 p-4 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-fg-strong">Coletas em andamento</h2>
              <p className="text-xs text-fg-faint mt-1">
                Atualização automática enquanto houver coleta ativa.
              </p>
            </div>
            <button
              onClick={() => void refetchJobs()}
              disabled={jobsPending}
              className="text-xs bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-3 py-2 rounded"
            >
              {jobsPending ? "Atualizando…" : "Atualizar"}
            </button>
          </div>

          {jobsPending && (
            <div className="space-y-2">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          )}

          {!jobsPending && jobsIsError && (
            <div className="rounded border border-error/40 bg-error/10 px-3 py-3 text-sm text-error">
              Falha ao carregar as coletas.
            </div>
          )}

          {!jobsPending && !jobsIsError && jobs.length === 0 && (
            <div className="text-sm text-fg-muted">Nenhuma coleta ativa no momento.</div>
          )}

          {!jobsPending && !jobsIsError && jobs.length > 0 && (
            <div className="space-y-3">
              {jobs.map((job) => (
                <JobCard
                  key={job.job_id}
                  job={job}
                  bancaPorId={bancaPorId}
                  profissaoPorId={profissaoPorId}
                />
              ))}
            </div>
          )}
        </section>

        {/* Bloco 3: Listagem */}
        <section className="border border-border rounded-lg bg-page/70 p-4 space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-fg-strong">Concursos coletados</h2>
              {(total > 0 || !temJobAtivo) && !listaPending && !listaIsError && (
                <p className="text-xs text-fg-faint mt-1">
                  {total.toLocaleString("pt-BR")} concurso(s) encontrado(s)
                </p>
              )}
            </div>
            <input
              type="text"
              value={buscaInput}
              onChange={(e) => setBuscaInput(e.target.value)}
              placeholder="Buscar por nome, órgão ou banca…"
              className="h-9 w-full md:w-72 rounded border border-border bg-surface-2 px-3 text-sm text-fg focus:border-primary focus:outline-none"
            />
          </div>

          <div className={`overflow-x-auto rounded border border-border transition-opacity ${listaFetching && !listaPending ? "opacity-70" : ""}`}>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-2/70 text-left text-[11px] font-semibold uppercase text-fg-faint">
                  <th className="px-3 py-2">Concurso</th>
                  <th className="px-3 py-2">Banca</th>
                  <th className="px-3 py-2">Ano</th>
                  <th className="px-3 py-2">Aplicação</th>
                  <th className="px-3 py-2">Arquivos</th>
                  <th className="px-3 py-2 text-right">Link</th>
                </tr>
              </thead>
              <tbody>
                {listaPending &&
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i} className="border-b border-border last:border-b-0">
                      <td className="px-3 py-3">
                        <Skeleton className="h-4 w-56" />
                        <Skeleton className="h-3 w-36 mt-1.5" />
                      </td>
                      <td className="px-3 py-3"><Skeleton className="h-4 w-24" /></td>
                      <td className="px-3 py-3"><Skeleton className="h-4 w-10" /></td>
                      <td className="px-3 py-3"><Skeleton className="h-4 w-20" /></td>
                      <td className="px-3 py-3"><Skeleton className="h-6 w-32" /></td>
                      <td className="px-3 py-3"><Skeleton className="h-4 w-6 ml-auto" /></td>
                    </tr>
                  ))}

                {!listaPending && listaIsError && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-sm text-error">
                      Falha ao carregar concursos.{" "}
                      <button
                        onClick={() => void refetchLista()}
                        className="underline hover:text-error/80"
                      >
                        Tentar de novo
                      </button>
                    </td>
                  </tr>
                )}

                {!listaPending && !listaIsError && concursos.length === 0 && temJobAtivo && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8">
                      <BrandLoader size={32} label="Coleta em andamento — aguardando os primeiros resultados…" />
                    </td>
                  </tr>
                )}

                {!listaPending && !listaIsError && concursos.length === 0 && !temJobAtivo && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-sm text-fg-muted">
                      Nenhum concurso coletado ainda. Use &quot;Nova coleta&quot; acima.
                    </td>
                  </tr>
                )}

                {!listaPending &&
                  !listaIsError &&
                  concursos.map((c) => (
                    <tr key={c.id} className="border-b border-border last:border-b-0 align-top">
                      <td className="px-3 py-3">
                        <div className="text-sm font-medium text-fg">{c.nome_completo}</div>
                        {c.orgao_nome && (
                          <div className="text-xs text-fg-faint mt-0.5">{c.orgao_nome}</div>
                        )}
                      </td>
                      <td className="px-3 py-3 text-fg-muted">{c.banca_nome || "—"}</td>
                      <td className="px-3 py-3 text-fg-muted">{c.ano ?? "—"}</td>
                      <td className="px-3 py-3 text-fg-muted">{formatarData(c.data_aplicacao)}</td>
                      <td className="px-3 py-3">
                        {c.arquivos.length === 0 ? (
                          <span className="text-xs text-fg-faint">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1.5">
                            {c.arquivos.map((a) => (
                              <a
                                key={a.id}
                                href={apiUrl(`/api/q/concursos/arquivo/${a.id}`)}
                                download={a.nome_arquivo}
                                className="inline-flex items-center gap-1 rounded border border-border bg-surface-2 px-2 py-1 text-[11px] font-medium text-fg hover:bg-fg-strong/6"
                              >
                                <span className="material-symbols-outlined text-[13px]">description</span>
                                {labelArquivo(a.tipo)}
                              </a>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right">
                        <a
                          href={`https://www.tecconcursos.com.br/concursos/${c.url_concurso}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="Abrir concurso na fonte externa"
                          className="inline-flex items-center justify-center text-fg-muted hover:text-primary"
                        >
                          <span className="material-symbols-outlined text-[16px]">open_in_new</span>
                        </a>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          {!listaPending && !listaIsError && total > 0 && (
            <div className="flex items-center justify-between text-xs text-fg-muted">
              <span>
                Página {page} de {totalPaginas}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="rounded border border-border bg-surface-2 px-3 py-1.5 font-medium text-fg disabled:opacity-40"
                >
                  Anterior
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPaginas, p + 1))}
                  disabled={page >= totalPaginas}
                  className="rounded border border-border bg-surface-2 px-3 py-1.5 font-medium text-fg disabled:opacity-40"
                >
                  Próxima
                </button>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

// ─── Subcomponentes ──────────────────────────────────────

function ComboFiltro({
  titulo,
  placeholder,
  busca,
  onBuscaChange,
  itens,
  totalDisponivel,
  isSelecionado,
  onToggle,
}: {
  titulo: string;
  placeholder: string;
  busca: string;
  onBuscaChange: (v: string) => void;
  itens: FiltroItem[];
  totalDisponivel: number;
  isSelecionado: (key: string) => boolean;
  onToggle: (item: FiltroItem) => void;
}) {
  return (
    <div>
      <span className="mb-1 block text-xs font-semibold text-fg-muted">
        {titulo} <span className="text-fg-faint">({totalDisponivel})</span>
      </span>
      <input
        type="text"
        value={busca}
        onChange={(e) => onBuscaChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded border border-border bg-surface-2 px-3 text-sm text-fg focus:border-primary focus:outline-none"
      />
      <div className="mt-2 max-h-48 overflow-y-auto rounded border border-border">
        {itens.length === 0 ? (
          <div className="px-3 py-3 text-xs text-fg-faint">Nenhum resultado para a busca.</div>
        ) : (
          itens.map((item) => {
            const selecionado = isSelecionado(item.key);
            return (
              <button
                type="button"
                key={item.key}
                onClick={() => onToggle(item)}
                className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs transition ${
                  selecionado
                    ? "bg-primary/15 text-primary"
                    : "text-fg hover:bg-fg-strong/6"
                }`}
              >
                <span className="truncate">{item.name}</span>
                {selecionado && <span className="material-symbols-outlined text-[14px]">check</span>}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function JobCard({
  job,
  bancaPorId,
  profissaoPorId,
}: {
  job: ConcursoJob;
  bancaPorId: Map<number, string>;
  profissaoPorId: Map<number, string>;
}) {
  const progresso =
    job.total_units > 0 ? Math.max(0, Math.min(100, (job.done_units / job.total_units) * 100)) : 0;
  const emDescoberta = discoveryEmAndamento(job.discovery);
  const filtrosLegiveis = (job.filtros ?? []).map((f) => {
    const nome =
      f.tipo === "BANCA" ? bancaPorId.get(f.id) : profissaoPorId.get(f.id);
    const rotulo = f.tipo === "BANCA" ? "Banca" : "Formação";
    return nome ? `${rotulo}: ${nome}` : `${rotulo} #${f.id}`;
  });

  return (
    <div className="rounded-lg border border-border bg-black/20 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-sm font-semibold text-fg-strong">
            Job #{job.job_id}
            {job.paused && (
              <span className="ml-1.5 inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/15 px-2 py-0.5 text-[10px] font-bold uppercase text-warning">
                <span className="material-symbols-outlined text-[12px]">pause</span> Pausado
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-fg-muted">Status: {statusTexto(job.status)}</div>
          {filtrosLegiveis.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {filtrosLegiveis.map((f, i) => (
                <span
                  key={i}
                  className="rounded-full border border-border bg-surface-2 px-2 py-0.5 text-[11px] text-fg-muted"
                >
                  {f}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs md:min-w-45">
          <div className="rounded bg-page px-3 py-2">
            <div className="text-lg font-semibold text-success">{job.done_units}</div>
            <div className="text-fg-faint">Done</div>
          </div>
          <div className="rounded bg-page px-3 py-2">
            <div className="text-lg font-semibold text-warning">{job.blocked_units}</div>
            <div className="text-fg-faint">Blocked</div>
          </div>
          <div className="rounded bg-page px-3 py-2">
            <div className="text-lg font-semibold text-error">{job.failed_units}</div>
            <div className="text-fg-faint">Falhas</div>
          </div>
        </div>
      </div>

      <div className="mt-4">
        {emDescoberta ? (
          <BrandLoader
            size={22}
            className="items-start gap-1 py-1 text-left"
            label="Descobrindo concursos…"
          />
        ) : (
          <>
            <div className="mb-1 flex items-center justify-between text-xs text-fg-muted">
              <span>Progresso</span>
              <span>
                {job.done_units}/{job.total_units}
              </span>
            </div>
            <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
              <div className="h-full bg-cyan-500 transition-all" style={{ width: `${progresso}%` }} />
            </div>
          </>
        )}
      </div>

      <div className="mt-3 text-xs text-fg-faint">
        Última atualização: {job.atualizado_em ? new Date(job.atualizado_em).toLocaleString("pt-BR") : "—"}
      </div>
    </div>
  );
}
