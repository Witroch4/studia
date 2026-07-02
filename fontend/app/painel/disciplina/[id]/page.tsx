"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { StatCard, Skeleton } from "@/app/components/ds";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

interface AssuntoStats {
  nome: string;
  tempo_segundos: number;
  acertos: number;
  erros: number;
  total: number;
  pct: number;
}

interface Atividade {
  data: string; // YYYY-MM-DD
  resolvidas: number;
  acertos: number;
}

interface DisciplinaStats {
  materia_id: number;
  nome: string;
  tempo_segundos: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  por_assunto: AssuntoStats[];
  atividade_recente: Atividade[];
}

function fmtDuracao(seg: number): string {
  const h = Math.floor(seg / 3600);
  const m = Math.floor((seg % 3600) / 60);
  return `${h}h${String(m).padStart(2, "0")}min`;
}

function pctColor(pct: number) {
  if (pct >= 80) return "bg-accent-success/20 text-accent-success";
  if (pct >= 70) return "bg-secondary/20 text-secondary";
  return "bg-accent-error/20 text-accent-error";
}

function fmtDia(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

export default function DisciplinaStatsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const { data, isPending, isError, error } = useQuery({
    queryKey: qk.dashboardDisciplina(id),
    queryFn: () =>
      apiJson<DisciplinaStats>(`/api/q/dashboard/disciplina/${id}`, { cache: "no-store" }),
    retry: false,
  });

  const status = (error as { status?: number })?.status;
  const isDeslogado = isError && status === 401;
  const naoEncontrada = isError && status === 404;

  return (
    <>
      <header className="hidden md:flex sticky top-0 z-40 bg-page/80 backdrop-blur-md border-b border-border px-8 py-4 justify-between items-center">
        <h1 className="text-2xl font-bold text-fg-strong">Estatísticas da Matéria</h1>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        <div className="mb-6">
          <Link
            href="/painel"
            className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-primary transition-colors"
          >
            <span className="material-symbols-outlined text-base">arrow_back</span>
            Voltar ao painel
          </Link>
        </div>

        {isPending && <DisciplinaSkeleton />}

        {isDeslogado && (
          <div className="bg-surface p-8 rounded-xl border border-border text-center">
            <p className="text-fg-muted">
              Sua sessão expirou.{" "}
              <Link href="/login" className="text-primary hover:underline">Entrar novamente</Link>.
            </p>
          </div>
        )}

        {naoEncontrada && (
          <div className="bg-surface p-8 rounded-xl border border-border text-center">
            <p className="text-fg-muted">
              Matéria não encontrada.{" "}
              <Link href="/painel" className="text-primary hover:underline">Voltar ao painel</Link>.
            </p>
          </div>
        )}

        {isError && !isDeslogado && !naoEncontrada && (
          <div className="bg-surface p-8 rounded-xl border border-border text-center text-accent-error">
            Não foi possível carregar as estatísticas. Tente recarregar a página.
          </div>
        )}

        {data && <DisciplinaDados data={data} />}
      </main>
    </>
  );
}

/** Reserva o espaço final (título + 3 cards + tabela) — regra "dados não pulam". */
function DisciplinaSkeleton() {
  return (
    <>
      <Skeleton className="h-9 w-80 max-w-full mb-8" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
      <div className="bg-surface p-6 rounded-xl shadow-sm border border-border">
        <Skeleton className="h-4 w-48 mb-6" />
        <div className="space-y-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      </div>
    </>
  );
}

function DisciplinaDados({ data }: { data: DisciplinaStats }) {
  return (
    <>
      <div className="text-3xl font-bold text-fg-strong mb-8">{data.nome}</div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <StatCard
          title="Tempo de Estudo"
          icon="schedule"
          iconColor="primary"
          progress={Math.min(100, Math.round((data.tempo_segundos / 3600 / 40) * 100))}
        >
          <span className="text-4xl font-bold text-fg-strong">
            {fmtDuracao(data.tempo_segundos)}
          </span>
        </StatCard>

        <StatCard title="Precisão" icon="precision_manufacturing" iconColor="secondary" progress={Math.round(data.taxa)}>
          <div className="flex items-end justify-between w-full">
            <div>
              <span className="text-sm text-accent-success font-medium">{data.acertos} Acertos</span>
              <div className="text-xs text-accent-error font-medium">{data.erros} Erros</div>
            </div>
            <span className="text-4xl font-bold text-fg-strong">{Math.round(data.taxa)}%</span>
          </div>
        </StatCard>

        <StatCard title="Questões Resolvidas" icon="task_alt" iconColor="success" progress={100}>
          <span className="text-4xl font-bold text-fg-strong">
            {data.resolvidas.toLocaleString("pt-BR")}
          </span>
        </StatCard>
      </div>

      {/* Por assunto */}
      <div className="bg-surface p-6 rounded-xl shadow-sm border border-border mb-8">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xs font-semibold text-fg-muted uppercase tracking-wider">
            Desempenho por Assunto
          </h3>
        </div>
        {data.por_assunto.length === 0 ? (
          <p className="text-sm text-fg-faint italic">
            As questões resolvidas nesta matéria ainda não têm assunto classificado.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-fg-muted uppercase bg-surface-2/50">
                <tr>
                  <th className="px-4 py-3 rounded-l-lg">Assunto</th>
                  <th className="px-4 py-3 text-center">Tempo</th>
                  <th className="px-4 py-3 text-center text-accent-success">
                    <span className="material-symbols-outlined text-base align-middle">check</span>
                  </th>
                  <th className="px-4 py-3 text-center text-accent-error">
                    <span className="material-symbols-outlined text-base align-middle">close</span>
                  </th>
                  <th className="px-4 py-3 text-center">Total</th>
                  <th className="px-4 py-3 text-center rounded-r-lg">%</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.por_assunto.map((a, i) => (
                  <tr key={a.nome} className={`hover:bg-surface-2/30 transition-colors ${i % 2 === 1 ? "bg-surface-2/10" : ""}`}>
                    <td className="px-4 py-4 font-medium text-fg-strong">{a.nome}</td>
                    <td className="px-4 py-4 text-center text-fg">{fmtDuracao(a.tempo_segundos)}</td>
                    <td className="px-4 py-4 text-center text-accent-success font-medium">{a.acertos}</td>
                    <td className="px-4 py-4 text-center text-accent-error font-medium">{a.erros}</td>
                    <td className="px-4 py-4 text-center text-fg">{a.total}</td>
                    <td className="px-4 py-4 text-center">
                      <span className={`${pctColor(a.pct)} px-2 py-1 rounded text-xs font-bold`}>{Math.round(a.pct)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Atividade recente na matéria */}
      {data.atividade_recente.length > 0 && (
        <div className="bg-surface p-6 rounded-xl shadow-sm border border-border">
          <h3 className="text-xs font-semibold text-fg-muted uppercase tracking-wider mb-4">
            Atividade Recente
          </h3>
          <div className="flex gap-2 overflow-x-auto pb-2">
            {data.atividade_recente.slice(-14).map((a) => {
              const pct = a.resolvidas ? Math.round((a.acertos / a.resolvidas) * 100) : 0;
              return (
                <div
                  key={a.data}
                  title={`${fmtDia(a.data)}: ${a.resolvidas} resolvidas, ${a.acertos} acertos (${pct}%)`}
                  className="shrink-0 w-14 rounded-lg bg-surface-2/40 border border-border p-2 text-center"
                >
                  <div className="text-[10px] text-fg-faint">{fmtDia(a.data)}</div>
                  <div className="text-sm font-bold text-fg-strong">{a.resolvidas}</div>
                  <div className={`text-[10px] font-bold ${pct >= 70 ? "text-accent-success" : "text-accent-error"}`}>
                    {pct}%
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
