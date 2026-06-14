"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StatCard } from "@/app/components/ds";
import { apiFetch } from "@/lib/api";

interface Disciplina {
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

interface Dashboard {
  total_horas_segundos: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  por_disciplina: Disciplina[];
  atividade_recente: Atividade[];
  streak_dias: number;
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
  const [data, setData] = useState<Dashboard | null>(null);
  const [estado, setEstado] = useState<"loading" | "ok" | "erro" | "deslogado">("loading");

  useEffect(() => {
    let cancel = false;
    apiFetch("/api/q/dashboard", { cache: "no-store" })
      .then((r) => {
        if (r.status === 401) {
          if (!cancel) setEstado("deslogado");
          return null;
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: Dashboard | null) => {
        if (cancel || d === null) return;
        setData(d);
        setEstado("ok");
      })
      .catch(() => {
        if (!cancel) setEstado("erro");
      });
    return () => {
      cancel = true;
    };
  }, []);

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

        {estado === "loading" && <p className="text-fg-muted">Carregando seu painel…</p>}

        {estado === "deslogado" && (
          <div className="bg-surface p-8 rounded-xl border border-border text-center">
            <p className="text-fg-muted">
              Sua sessão expirou.{" "}
              <Link href="/login" className="text-primary hover:underline">Entrar novamente</Link>.
            </p>
          </div>
        )}

        {estado === "erro" && (
          <div className="bg-surface p-8 rounded-xl border border-border text-center text-accent-error">
            Não foi possível carregar o painel. Tente recarregar a página.
          </div>
        )}

        {estado === "ok" && data && (
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
                  <tr key={d.nome} className={`hover:bg-surface-2/30 transition-colors ${i % 2 === 1 ? "bg-surface-2/10" : ""}`}>
                    <td className="px-4 py-4 font-medium text-primary">{d.nome}</td>
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
