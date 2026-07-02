"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { diasRestantes } from "@/lib/utils";
import { Skeleton } from "../../components/ds";

// ─── Tipos ───────────────────────────────────────────────

type MapaResumo = {
  id: number;
  concurso_id: number;
  concurso_nome: string;
  orgao_sigla: string | null;
  banca_nome: string | null;
  cargo_nome: string;
  data_prova: string | null; // ISO (YYYY-MM-DD) ou null
  total_itens: number;
  itens_dominados: number;
  caderno_ids: number[];
  criado_em: string | null;
};

// ─── Helpers ─────────────────────────────────────────────

function textoCountdown(dias: number | null): string {
  if (dias === null) return "Data da prova não informada";
  if (dias < 0) return "Prova realizada";
  if (dias === 0) return "A prova é hoje!";
  if (dias === 1) return "1 dia até a prova";
  return `${dias} dias até a prova`;
}

// ─── Página ──────────────────────────────────────────────

export default function MapaListaPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: qk.mapas(),
    queryFn: async (): Promise<{ mapas: MapaResumo[] }> => {
      const r = await apiFetch("/api/q/mapas", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
  });

  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-fg-strong flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">map</span>
              Mapa da Aprovação
            </h1>
            <p className="text-sm text-fg-muted mt-1">
              Do edital à prova: cargos, matérias, prazos e questões da banca em um só plano.
            </p>
          </div>
          <Link
            href="/q/mapa/novo"
            className="shrink-0 px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-semibold hover:bg-primary-600 transition"
          >
            + Criar Mapa
          </Link>
        </header>

        {isPending && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-36 rounded-xl" />
            <Skeleton className="h-36 rounded-xl" />
            <Skeleton className="h-36 rounded-xl" />
            <Skeleton className="h-36 rounded-xl" />
          </div>
        )}

        {isError && (
          <div className="rounded-xl border border-error/40 bg-error/10 px-4 py-3 text-sm text-error">
            Não foi possível carregar seus mapas. Recarregue a página.
          </div>
        )}

        {data && data.mapas.length === 0 && (
          <div className="rounded-xl border border-border bg-surface p-10 text-center space-y-3">
            <span className="material-symbols-outlined text-fg-faint text-5xl">map</span>
            <p className="text-fg-muted">
              Você ainda não tem nenhum Mapa. Escolha um concurso e deixe a IA ler o edital para você.
            </p>
            <Link href="/q/mapa/novo" className="inline-block text-primary font-medium hover:underline">
              Criar meu primeiro Mapa →
            </Link>
          </div>
        )}

        {data && data.mapas.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {data.mapas.map((m) => {
              const dias = diasRestantes(m.data_prova);
              const pct = m.total_itens
                ? Math.round((100 * m.itens_dominados) / m.total_itens)
                : 0;
              return (
                <Link
                  key={m.id}
                  href={`/q/mapa/${m.id}`}
                  className="rounded-xl border border-border bg-surface p-5 space-y-2 transition hover:border-primary/50"
                >
                  <p className="text-xs text-fg-faint min-h-4">
                    {[m.banca_nome, m.orgao_sigla].filter(Boolean).join(" · ")}
                  </p>
                  <h2 className="font-semibold text-fg-strong leading-snug">{m.concurso_nome}</h2>
                  <p className="text-sm text-primary">{m.cargo_nome}</p>
                  <div className="flex items-center justify-between gap-2 text-xs text-fg-muted pt-2">
                    <span>{textoCountdown(dias)}</span>
                    <span className="shrink-0">{pct}% dominado</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-fg/10 overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
                    />
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
