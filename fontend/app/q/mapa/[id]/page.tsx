"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiJson, ApiError } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { diasRestantes } from "@/lib/utils";
import { Skeleton, ProgressBar } from "../../../components/ds";
import { TimelineEventos } from "./components/TimelineEventos";
import { Verticalizacao } from "./components/Verticalizacao";
import type { Evento } from "./components/TimelineEventos";
import type { GrupoMateria } from "./components/Verticalizacao";

export type { Evento } from "./components/TimelineEventos";
export type { GrupoMateria, ItemVerticalizacao } from "./components/Verticalizacao";

// ─── Tipos ───────────────────────────────────────────────

interface CadernoMapa {
  id: number;
  nome: string;
  total: number;
}

export interface MapaDetalhe {
  id: number;
  concurso_id: number;
  concurso_nome: string;
  orgao_sigla: string | null;
  banca_nome: string | null;
  cargo_nome: string;
  cargo_dados: unknown;
  data_prova: string | null;
  eventos: Evento[];
  verticalizacao: GrupoMateria[];
  cadernos: CadernoMapa[];
}

// ─── Helpers ─────────────────────────────────────────────

function formatarData(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR");
}

function textoCountdown(dias: number | null): string {
  if (dias === null) return "Data da prova ainda não divulgada";
  if (dias < 0) return "Prova já realizada";
  if (dias === 0) return "A prova é hoje!";
  if (dias === 1) return "Falta 1 dia para a prova";
  return `Faltam ${dias} dias para a prova`;
}

// ─── Página ──────────────────────────────────────────────

export default function MapaDetalhePage() {
  const params = useParams<{ id: string }>();
  const mapaId = params.id;
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data, isPending, isError, error } = useQuery<MapaDetalhe, ApiError>({
    queryKey: qk.mapa(mapaId),
    queryFn: () => apiJson<MapaDetalhe>(`/api/q/mapas/${mapaId}`, { cache: "no-store" }),
  });

  const excluirMutation = useMutation({
    mutationFn: () => apiJson(`/api/q/mapas/${mapaId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.mapas() });
      router.push("/q/mapa");
    },
    onError: () => toast.error("Não foi possível excluir o Mapa. Tente de novo."),
  });

  function handleExcluir() {
    if (!data) return;
    const confirmado = confirm(
      `Excluir o Mapa "${data.cargo_nome}"? Os cadernos e questões continuam disponíveis em Meus Cadernos — só o plano de estudos é removido.`
    );
    if (confirmado) excluirMutation.mutate();
  }

  const todosItens = data ? data.verticalizacao.flatMap((g) => g.itens) : [];
  const totalItens = todosItens.length;
  const dominados = todosItens.filter((i) => i.status === "dominado").length;
  const pct = totalItens ? Math.round((100 * dominados) / totalItens) : 0;
  const dias = data ? diasRestantes(data.data_prova) : null;
  const contagemAlerta = dias !== null && dias >= 0 && dias <= 7;

  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        <div className="flex items-center justify-between gap-3">
          <Link
            href="/q/mapa"
            className="text-sm text-fg-faint hover:text-primary inline-flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Meus Mapas
          </Link>
          {data && (
            <button
              type="button"
              onClick={handleExcluir}
              disabled={excluirMutation.isPending}
              className="text-xs text-fg-faint hover:text-error transition disabled:opacity-50"
            >
              {excluirMutation.isPending ? "Excluindo…" : "Excluir Mapa"}
            </button>
          )}
        </div>

        {isPending && (
          <div className="space-y-6">
            <Skeleton className="h-40 rounded-2xl" />
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-4">
                <Skeleton className="h-72 rounded-xl" />
                <Skeleton className="h-28 rounded-xl" />
              </div>
              <Skeleton className="h-56 rounded-xl" />
            </div>
          </div>
        )}

        {isError && (
          <div className="rounded-xl border border-error/40 bg-error/10 px-4 py-8 text-center space-y-2">
            <p className="text-sm text-error">
              {error?.status === 404
                ? "Este Mapa não existe ou não é seu."
                : "Não foi possível carregar o Mapa. Recarregue a página."}
            </p>
            <Link href="/q/mapa" className="inline-block text-primary font-medium hover:underline">
              ← Voltar para Meus Mapas
            </Link>
          </div>
        )}

        {data && (
          <>
            {/* Hero */}
            <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
              <div>
                <p className="text-xs text-fg-faint uppercase tracking-wide">
                  {[data.banca_nome, data.orgao_sigla].filter(Boolean).join(" · ") || "Concurso"}
                </p>
                <h1 className="text-xl font-bold text-fg-strong leading-snug mt-0.5">
                  {data.concurso_nome}
                </h1>
                <p className="text-primary font-medium">{data.cargo_nome}</p>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                <div>
                  <p className={`text-2xl font-bold ${contagemAlerta ? "text-warning" : "text-fg-strong"}`}>
                    {textoCountdown(dias)}
                  </p>
                  {data.data_prova && (
                    <p className="text-xs text-fg-faint mt-0.5">{formatarData(data.data_prova)}</p>
                  )}
                </div>
                <div className="w-full sm:w-64 space-y-1.5">
                  <div className="flex justify-between text-xs text-fg-muted">
                    <span>Progresso</span>
                    <span>{pct}% dominado</span>
                  </div>
                  <ProgressBar value={pct} color="primary" height={8} />
                </div>
              </div>
            </section>

            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-6">
                <div>
                  <h2 className="text-sm font-semibold text-fg-strong mb-3 flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px] text-primary">checklist</span>
                    Verticalização do edital
                  </h2>
                  <Verticalizacao mapaId={mapaId} grupos={data.verticalizacao} />
                </div>

                {data.cadernos.length > 0 && (
                  <div>
                    <h2 className="text-sm font-semibold text-fg-strong mb-3 flex items-center gap-2">
                      <span className="material-symbols-outlined text-[18px] text-primary">quiz</span>
                      Cadernos gerados
                    </h2>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {data.cadernos.map((c) => (
                        <div
                          key={c.id}
                          className="rounded-xl border border-border bg-surface p-4 space-y-2"
                        >
                          <Link
                            href={`/q/caderno/${c.id}`}
                            className="font-medium text-fg-strong hover:text-primary transition block truncate"
                          >
                            {c.nome} — {c.total} questões
                          </Link>
                          <Link
                            href={`/q/caderno/${c.id}/cronograma`}
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            <span className="material-symbols-outlined text-[14px]">calendar_month</span>
                            Gerar cronograma
                          </Link>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div>
                <TimelineEventos eventos={data.eventos} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
