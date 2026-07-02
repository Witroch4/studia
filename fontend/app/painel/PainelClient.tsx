"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { StatCard } from "@/app/components/ds";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

interface Disciplina {
  materia_id: number;
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

interface UltimoCaderno {
  caderno_id: number;
  nome: string;
  pasta: string | null;
  ultimo_acesso: string | null; // ISO
}

interface Dashboard {
  total_horas_segundos: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  por_disciplina: Disciplina[];
  atividade_recente: Atividade[];
  streak_dias: number;
  ultimas_pastas: UltimoCaderno[];
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

// Datetimes naive do backend são UTC (containers em UTC); anexa "Z" se faltar.
function tempoRelativo(iso: string): string {
  const norm = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const diff = Date.now() - new Date(norm).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h}h`;
  const d = Math.floor(h / 24);
  if (d === 1) return "ontem";
  if (d < 30) return `há ${d} dias`;
  const meses = Math.floor(d / 30);
  return meses === 1 ? "há 1 mês" : `há ${meses} meses`;
}

function pastaLabel(pasta: string | null): string {
  return pasta && pasta.trim() ? pasta : "Sem classificação";
}

function ultimosDias(n: number): string[] {
  const dias: string[] = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    dias.push(d.toISOString().slice(0, 10));
  }
  return dias;
}

export default function PainelClient() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: qk.dashboard(),
    queryFn: () => apiJson<Dashboard>("/api/q/dashboard", { cache: "no-store" }),
    retry: false,
  });

  const isDeslogado =
    isError && (error as { status?: number })?.status === 401;

  return (
    <>
      <header className="hidden md:flex sticky top-0 z-40 bg-page/80 backdrop-blur-md border-b border-border px-8 py-4 justify-between items-center">
        <h1 className="text-2xl font-bold text-fg-strong">Dashboard</h1>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
          <div className="text-3xl font-bold text-fg-strong">Visão Geral</div>
          <Link
            href="/q/filtrar"
            className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-cyan-600 text-white rounded-lg shadow-lg shadow-cyan-500/30 transition-all font-medium"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Resolver Questões
          </Link>
        </div>

        {isPending && <p className="text-fg-muted">Carregando seu painel…</p>}

        {isDeslogado && (
          <div className="bg-surface p-8 rounded-xl border border-border text-center">
            <p className="text-fg-muted">
              Sua sessão expirou.{" "}
              <Link href="/login" className="text-primary hover:underline">Entrar novamente</Link>.
            </p>
          </div>
        )}

        {isError && !isDeslogado && (
          <div className="bg-surface p-8 rounded-xl border border-border text-center text-accent-error">
            Não foi possível carregar o painel. Tente recarregar a página.
          </div>
        )}

        {data && (
          data.resolvidas === 0 ? (
            <EstadoVazio />
          ) : (
            <PainelDados data={data} />
          )
        )}
      </main>
    </>
  );
}

function EstadoVazio() {
  return (
    <div className="bg-surface p-10 rounded-xl border border-border flex flex-col items-center text-center gap-4">
      <span className="material-symbols-outlined text-5xl text-primary/40">rocket_launch</span>
      <h2 className="text-xl font-bold text-fg-strong">Comece a estudar</h2>
      <p className="text-fg-muted max-w-md">
        Você ainda não resolveu nenhuma questão. Assim que começar, seu progresso —
        horas, precisão, disciplinas e constância — aparece aqui automaticamente.
      </p>
      <div className="flex gap-3 mt-2">
        <Link
          href="/q/filtrar"
          className="px-4 py-2 bg-primary hover:bg-cyan-600 text-white rounded-lg font-medium transition-all"
        >
          Montar um caderno
        </Link>
        <Link
          href="/q/guias"
          className="px-4 py-2 bg-surface-2 border border-border-strong hover:bg-surface text-fg rounded-lg font-medium transition-all"
        >
          Explorar guias
        </Link>
      </div>
    </div>
  );
}

function PainelDados({ data }: { data: Dashboard }) {
  const router = useRouter();
  const ativos = new Set(data.atividade_recente.filter((a) => a.resolvidas > 0).map((a) => a.data));
  const dias = ultimosDias(14);

  return (
    <>
      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <StatCard
          title="Total de Horas"
          icon="schedule"
          iconColor="primary"
          progress={Math.min(100, Math.round((data.total_horas_segundos / 3600 / 40) * 100))}
        >
          <span className="text-4xl font-bold text-fg-strong">
            {fmtDuracao(data.total_horas_segundos)}
          </span>
        </StatCard>

        <StatCard title="Precisão Técnica" icon="precision_manufacturing" iconColor="secondary" progress={Math.round(data.taxa)}>
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

      {/* Streak */}
      <div className="bg-surface p-6 rounded-xl shadow-sm border border-border mb-8">
        <div className="flex justify-between items-end mb-4">
          <div>
            <h3 className="text-xs font-semibold text-fg-muted uppercase tracking-wider">Constância nos Estudos</h3>
            <p className="text-fg mt-1">
              {data.streak_dias > 0 ? (
                <>
                  Você está há <span className="font-bold text-primary">{data.streak_dias} dia{data.streak_dias === 1 ? "" : "s"}</span> estudando sem parar!
                </>
              ) : (
                <>Estude hoje para começar uma sequência 🔥</>
              )}
            </p>
          </div>
        </div>
        <div className="flex gap-2 overflow-x-auto pb-2">
          {dias.map((d) => {
            const ok = ativos.has(d);
            return (
              <div
                key={d}
                title={d}
                className={`shrink-0 w-8 h-8 rounded flex items-center justify-center ${
                  ok
                    ? "bg-primary/20 border border-primary/50 text-primary"
                    : "bg-surface-2 border border-border"
                }`}
              >
                {ok && <span className="material-symbols-outlined text-sm">check</span>}
              </div>
            );
          })}
        </div>
      </div>

      {/* Últimos cadernos acessados */}
      {data.ultimas_pastas.length > 0 && (
        <div className="bg-surface p-6 rounded-xl shadow-sm border border-border mb-8">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-xs font-semibold text-fg-muted uppercase tracking-wider">
              Últimos cadernos acessados
            </h3>
            <Link href="/q/cadernos" className="text-xs text-primary hover:underline">
              Ver todas
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.ultimas_pastas.map((c) => (
              <Link
                key={c.caderno_id}
                href={`/q/caderno/${c.caderno_id}`}
                className="group flex items-center gap-3 p-3 rounded-lg bg-surface-2/40 border border-border hover:border-primary/50 hover:bg-surface-2 transition-colors"
              >
                <span className="material-symbols-outlined text-primary shrink-0">menu_book</span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-fg-strong truncate group-hover:text-primary">
                    {c.nome}
                  </div>
                  <div className="text-xs text-fg-faint truncate">
                    {pastaLabel(c.pasta)}
                    {c.ultimo_acesso ? ` · ${tempoRelativo(c.ultimo_acesso)}` : ""}
                  </div>
                </div>
                <span className="material-symbols-outlined text-fg-faint text-base shrink-0 group-hover:text-primary">
                  chevron_right
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Disciplinas */}
      <div className="bg-surface p-6 rounded-xl shadow-sm border border-border">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xs font-semibold text-fg-muted uppercase tracking-wider">Painel de Disciplinas</h3>
        </div>
        {data.por_disciplina.length === 0 ? (
          <p className="text-sm text-fg-faint italic">
            Suas questões ainda não têm disciplina classificada.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-fg-muted uppercase bg-surface-2/50">
                <tr>
                  <th className="px-4 py-3 rounded-l-lg">Disciplinas</th>
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
                {data.por_disciplina.map((d, i) => (
                  <tr
                    key={d.nome}
                    onClick={() => router.push(`/painel/disciplina/${d.materia_id}`)}
                    className={`group cursor-pointer hover:bg-surface-2/30 transition-colors ${i % 2 === 1 ? "bg-surface-2/10" : ""}`}
                  >
                    <td className="px-4 py-4 font-medium">
                      <Link
                        href={`/painel/disciplina/${d.materia_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="flex items-center gap-1 text-primary group-hover:underline"
                      >
                        {d.nome}
                        <span className="material-symbols-outlined text-base text-fg-faint group-hover:text-primary">
                          chevron_right
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-4 text-center text-fg">{fmtDuracao(d.tempo_segundos)}</td>
                    <td className="px-4 py-4 text-center text-accent-success font-medium">{d.acertos}</td>
                    <td className="px-4 py-4 text-center text-accent-error font-medium">{d.erros}</td>
                    <td className="px-4 py-4 text-center text-fg">{d.total}</td>
                    <td className="px-4 py-4 text-center">
                      <span className={`${pctColor(d.pct)} px-2 py-1 rounded text-xs font-bold`}>{Math.round(d.pct)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
