"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { DonutChart, Skeleton } from "@/app/components/ds";

// ════════════════════════════ Tipos ════════════════════════════

interface Resumo {
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  tentativas: number;
  tempo_total_segundos: number;
  tempo_medio_segundos: number;
  cadernos: number;
  cadernos_ativos: number;
  favoritas: number;
}

interface DiaAtividade { data: string; resolvidas: number; acertos: number }

interface Grupo { nome: string; resolvidas: number; acertos: number; erros: number; taxa: number }

interface CadernoStats {
  id: number;
  nome: string;
  pasta: string | null;
  total: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  tempo_segundos: number;
  ultima_atividade: string | null;
}

interface EstatisticasGerais {
  resumo: Resumo;
  por_dia: DiaAtividade[];
  por_materia: Grupo[];
  por_banca: Grupo[];
  cadernos: CadernoStats[];
}

const nf = (n: number) => n.toLocaleString("pt-BR");

function formatTempo(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}min`;
  const sec = Math.floor(s % 60);
  return m > 0 ? `${m}min ${String(sec).padStart(2, "0")}s` : `${sec}s`;
}

function formatDataCurta(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

// ════════════════════════════ Ritmo (barras por dia) ════════════════════════════

function RitmoBarras({ dias }: { dias: DiaAtividade[] }) {
  if (dias.length === 0) {
    return (
      <p className="flex h-32 items-center justify-center text-sm text-fg-faint">
        Sem atividade nos últimos 30 dias.
      </p>
    );
  }
  const max = Math.max(...dias.map((d) => d.resolvidas), 1);
  return (
    <div>
      <div className="flex h-32 items-end gap-1" role="img"
        aria-label={`Resoluções por dia, últimos ${dias.length} dias com atividade.`}>
        {dias.map((d) => {
          const hPct = (d.resolvidas / max) * 100;
          const acertoPct = d.resolvidas ? (d.acertos / d.resolvidas) * 100 : 0;
          return (
            <div
              key={d.data}
              className="group relative flex-1 self-stretch flex flex-col justify-end"
              title={`${formatDataCurta(d.data)} — ${d.resolvidas} resoluções (${d.acertos} acertos)`}
            >
              <div className="flex w-full flex-col overflow-hidden rounded-t-sm transition group-hover:opacity-80" style={{ height: `${hPct}%` }}>
                <div className="w-full bg-error/80" style={{ height: `${100 - acertoPct}%` }} />
                <div className="w-full bg-success" style={{ height: `${acertoPct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-fg-faint tabular-nums">
        <span>{formatDataCurta(dias[0].data)}</span>
        <span>{formatDataCurta(dias[dias.length - 1].data)}</span>
      </div>
    </div>
  );
}

// ════════════════════════════ Grupos (matéria/banca) ════════════════════════════

function GrupoBloco({ titulo, grupos }: { titulo: string; grupos: Grupo[] }) {
  const max = Math.max(...grupos.map((g) => g.resolvidas), 1);
  return (
    <section className="rounded-xl border border-border/60 bg-surface p-5">
      <h3 className="mb-3 text-sm font-semibold text-fg">{titulo}</h3>
      {grupos.length === 0 && <p className="py-4 text-center text-sm text-fg-faint">Sem dados ainda.</p>}
      <ul className="space-y-2.5">
        {grupos.map((g) => {
          const pctAcerto = g.resolvidas ? (g.acertos / g.resolvidas) * 100 : 0;
          return (
            <li key={g.nome} className="text-xs">
              <div className="mb-0.5 flex items-center justify-between gap-2">
                <span className="truncate text-fg">{g.nome}</span>
                <span className="shrink-0 whitespace-nowrap tabular-nums text-fg-faint">
                  {nf(g.resolvidas)} ·{" "}
                  <span className={`font-semibold ${g.taxa >= 70 ? "text-success" : g.taxa >= 50 ? "text-warning" : "text-error"}`}>
                    {g.taxa}%
                  </span>
                </span>
              </div>
              <div aria-hidden className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                <div className="flex h-full" style={{ width: `${(g.resolvidas / max) * 100}%` }}>
                  <div className="h-full bg-success" style={{ width: `${pctAcerto}%` }} />
                  <div className="h-full bg-error" style={{ width: `${100 - pctAcerto}%` }} />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ════════════════════════════ KPI ════════════════════════════

function Kpi({ label, valor, sub }: { label: string; valor: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-surface-2/40 px-4 py-3">
      <div className="text-lg font-bold tabular-nums text-fg-strong">{valor}</div>
      <div className="mt-0.5 text-[11px] text-fg-muted">{label}</div>
      {sub && <div className="text-[10px] text-fg-faint">{sub}</div>}
    </div>
  );
}

// ════════════════════════════ Skeleton (formato final) ════════════════════════════

function GeraisSkeleton() {
  return (
    <main className="mx-auto max-w-6xl space-y-5 px-6 py-8">
      <div>
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-2 h-4 w-80" />
      </div>
      <section className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <div className="flex items-center justify-center rounded-xl border border-border/60 bg-surface p-5">
          <Skeleton className="h-44 w-44 rounded-full" />
        </div>
        <div className="rounded-xl border border-border/60 bg-surface p-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
          </div>
          <Skeleton className="mt-5 h-32" />
        </div>
      </section>
      <Skeleton className="h-64 rounded-xl" />
      <div className="grid gap-5 lg:grid-cols-2">
        <Skeleton className="h-56 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
      </div>
    </main>
  );
}

// ════════════════════════════ Página ════════════════════════════

export default function EstatisticasGeraisPage() {
  const { data, isPending, isError } = useQuery<EstatisticasGerais>({
    queryKey: qk.estatisticasGerais(),
    queryFn: () => apiJson("/api/q/estatisticas-gerais"),
    staleTime: 60_000,
  });

  if (isPending || (!data && !isError)) return <GeraisSkeleton />;

  if (isError || !data) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-16 text-center text-sm text-fg-muted">
        Não foi possível carregar suas estatísticas. Recarregue a página para tentar de novo.
      </main>
    );
  }

  const r = data.resumo;

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-6 py-8">
      <header>
        <h1 className="text-2xl font-bold text-fg-strong">Estatísticas</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Seu desempenho geral em todos os cadernos — cada questão conta uma vez (a última resposta vale).
        </p>
      </header>

      {r.resolvidas === 0 ? (
        <section className="rounded-xl border border-border/60 bg-surface px-6 py-16 text-center">
          <span className="material-symbols-outlined text-5xl text-primary">query_stats</span>
          <h2 className="mt-3 text-lg font-bold text-fg-strong">Nenhuma questão resolvida ainda</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-fg-muted">
            Resolva questões em qualquer caderno e o seu desempenho geral aparece aqui: acertos, ritmo diário, matérias e bancas.
          </p>
          <Link
            href="/q/cadernos"
            className="mt-6 inline-block rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-black transition hover:opacity-90"
          >
            Ir para meus cadernos
          </Link>
        </section>
      ) : (
        <>
          {/* ─── Herói: donut global + KPIs + ritmo ─── */}
          <section className="grid gap-5 lg:grid-cols-[360px_1fr]">
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border/60 bg-surface p-5">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Desempenho geral</h4>
              <DonutChart
                segs={[
                  { label: "Acertos", valor: r.acertos, cor: "var(--success)" },
                  { label: "Erros", valor: r.erros, cor: "var(--error)" },
                ]}
                centroGrande={`${Math.round(r.taxa)}%`}
                centroPequeno="de acerto"
                ariaLabel={`Desempenho geral: ${r.acertos} acertos e ${r.erros} erros em ${r.resolvidas} questões.`}
              />
            </div>

            <div className="rounded-xl border border-border/60 bg-surface p-5">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Kpi label="Questões resolvidas" valor={nf(r.resolvidas)} sub={`${nf(r.tentativas)} tentativas`} />
                <Kpi label="Tempo total de estudo" valor={formatTempo(r.tempo_total_segundos)} />
                <Kpi label="Tempo médio por questão" valor={r.tempo_medio_segundos > 0 ? formatTempo(r.tempo_medio_segundos) : "—"} />
                <Kpi label="Cadernos com atividade" valor={`${nf(r.cadernos_ativos)}`} sub={`de ${nf(r.cadernos)} cadernos`} />
                <Kpi label="Acertos" valor={nf(r.acertos)} />
                <Kpi label="Favoritas" valor={nf(r.favoritas)} />
              </div>
              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Ritmo — resoluções por dia</h4>
                  <span className="flex items-center gap-3 text-[10px] text-fg-faint">
                    <span className="flex items-center gap-1"><span aria-hidden className="h-2 w-2 rounded-[2px] bg-success" /> acertos</span>
                    <span className="flex items-center gap-1"><span aria-hidden className="h-2 w-2 rounded-[2px] bg-error/80" /> erros</span>
                  </span>
                </div>
                <RitmoBarras dias={data.por_dia} />
              </div>
            </div>
          </section>

          {/* ─── Todos os cadernos ─── */}
          <section className="rounded-xl border border-border/60 bg-surface">
            <header className="border-b border-border/60 px-5 py-3.5">
              <h3 className="text-sm font-semibold text-fg">Seus cadernos</h3>
            </header>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-fg-faint">
                  <tr className="border-b border-border/40">
                    <th className="px-5 py-2 text-left font-medium">Caderno</th>
                    <th className="px-3 py-2 text-left font-medium">Progresso</th>
                    <th className="px-3 py-2 text-right font-medium">Acerto</th>
                    <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">Tempo</th>
                    <th className="hidden px-3 py-2 text-right font-medium md:table-cell">Última atividade</th>
                    <th className="px-5 py-2 text-right font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {data.cadernos.map((c) => {
                    const progresso = c.total ? Math.round((c.resolvidas / c.total) * 100) : 0;
                    return (
                      <tr key={c.id} className="border-b border-border/40 last:border-0 hover:bg-surface-2/40">
                        <td className="max-w-60 px-5 py-2.5">
                          <Link href={`/q/caderno/${c.id}`} className="block truncate font-medium text-fg hover:text-primary">
                            {c.nome}
                          </Link>
                          {c.pasta && <span className="text-[10px] text-fg-faint">{c.pasta}</span>}
                        </td>
                        <td className="min-w-36 px-3 py-2.5">
                          <div className="flex items-center gap-2">
                            <div aria-hidden className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2">
                              <div className="h-full bg-primary" style={{ width: `${progresso}%` }} />
                            </div>
                            <span className="whitespace-nowrap tabular-nums text-fg-faint">
                              {nf(c.resolvidas)}/{nf(c.total)}
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          {c.resolvidas > 0 ? (
                            <span className={`font-semibold tabular-nums ${c.taxa >= 70 ? "text-success" : c.taxa >= 50 ? "text-warning" : "text-error"}`}>
                              {c.taxa}%
                            </span>
                          ) : (
                            <span className="text-fg-faint">—</span>
                          )}
                        </td>
                        <td className="hidden px-3 py-2.5 text-right tabular-nums text-fg-muted sm:table-cell">
                          {c.tempo_segundos > 0 ? formatTempo(c.tempo_segundos) : "—"}
                        </td>
                        <td className="hidden px-3 py-2.5 text-right text-fg-faint md:table-cell">
                          {c.ultima_atividade
                            ? new Date(c.ultima_atividade).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })
                            : "—"}
                        </td>
                        <td className="whitespace-nowrap px-5 py-2.5 text-right">
                          <Link href={`/q/caderno/${c.id}`} className="text-primary hover:underline">Abrir</Link>
                          <span aria-hidden className="mx-1.5 text-fg-faint">·</span>
                          <Link href={`/q/caderno/${c.id}?tab=estatisticas`} className="text-primary hover:underline">Estatísticas</Link>
                        </td>
                      </tr>
                    );
                  })}
                  {data.cadernos.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-8 text-center text-fg-faint">
                        Você ainda não tem cadernos. <Link href="/q/cadernos" className="text-primary hover:underline">Criar o primeiro</Link>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* ─── Por matéria e por banca ─── */}
          <div className="grid gap-5 lg:grid-cols-2">
            <GrupoBloco titulo="Desempenho por matéria" grupos={data.por_materia} />
            <GrupoBloco titulo="Desempenho por banca" grupos={data.por_banca} />
          </div>
        </>
      )}
    </main>
  );
}
