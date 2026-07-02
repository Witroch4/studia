"use client";
import { useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Skeleton } from "@/app/components/ds";
import {
  getCronograma, criarCronograma, recalcular,
  type CronogramaResp, type CronogramaInput,
} from "./api";
import { ConfigForm } from "./components/ConfigForm";
import { VereditoHero } from "./components/VereditoHero";
import { MapaQuestoes } from "./components/MapaQuestoes";
import { RitmoChart } from "./components/RitmoChart";
import { DistribuicaoDonut } from "./components/DistribuicaoDonut";
import { ErrosPorAssunto } from "./components/ErrosPorAssunto";
import { TimelineTable } from "./components/TimelineTable";
import { RevisarHoje } from "./components/RevisarHoje";
import { DiscursivasList } from "./components/DiscursivasList";
import { SimuladosList } from "./components/SimuladosList";

export default function CronogramaPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const chave = qk.cadernoSub(id, "cronograma");

  // getCronograma devolve null no 404 (caderno ainda sem cronograma).
  const { data, isPending, isError, refetch } = useQuery<CronogramaResp | null>({
    queryKey: chave,
    queryFn: () => getCronograma(id),
    staleTime: 30_000,
  });

  // Mapa da Aprovação: se este caderno pertence a algum mapa com prova marcada,
  // usamos a data como sugestão inicial no form de criação (nunca sobrescreve
  // valor já salvo). Erro na busca não bloqueia — segue com data manual.
  const {
    data: mapasData,
    isPending: mapasPending,
    isError: mapasError,
  } = useQuery({
    queryKey: qk.mapas(),
    queryFn: async (): Promise<{ mapas: { caderno_ids: number[]; data_prova: string | null }[] }> => {
      const r = await apiFetch("/api/q/mapas", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 60_000,
  });

  const recalcMutation = useMutation({
    mutationFn: () => recalcular(id),
    onSuccess: (resp) => queryClient.setQueryData(chave, resp),
  });
  const criarMutation = useMutation({
    mutationFn: (input: CronogramaInput) => criarCronograma(id, input),
    onSuccess: (resp) => queryClient.setQueryData(chave, resp),
  });

  const diasAteProva = useMemo(() => {
    if (!data) return 0;
    const agora = new Date();
    agora.setHours(0, 0, 0, 0);
    return Math.max(0, Math.ceil((+new Date(data.config.data_prova) - +agora) / 86400000));
  }, [data]);

  async function baixarXlsx() {
    const r = await apiFetch(`/api/q/cadernos/${id}/cronograma/export.xlsx`);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `cronograma_${id}.xlsx`; a.click();
    URL.revokeObjectURL(url);
  }

  if (isPending) {
    // Skeleton no formato da página final — nada pula quando os dados chegam.
    return (
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <div className="flex items-center justify-between">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-8 w-64" />
        </div>
        <Skeleton className="h-44 w-full rounded-xl" />
        <Skeleton className="h-56 w-full rounded-xl" />
        <div className="grid lg:grid-cols-5 gap-6">
          <Skeleton className="h-72 rounded-xl lg:col-span-3" />
          <Skeleton className="h-72 rounded-xl lg:col-span-2" />
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <h1 className="text-xl font-semibold mb-2">Cronograma</h1>
        <p className="text-sm text-fg-muted mb-4">Não deu para carregar o cronograma.</p>
        <button onClick={() => refetch()}
          className="text-sm border border-border/60 rounded px-3 py-1.5 hover:bg-surface-2">
          Tentar de novo
        </button>
      </div>
    );
  }

  if (!data) {
    // Espera a query de mapas resolver antes de montar o form — senão a data
    // "pula" de vazia para preenchida. Em erro, segue sem sugestão (não trava).
    if (mapasPending && !mapasError) {
      return (
        <div className="p-6">
          <h1 className="text-xl font-semibold mb-4">Criar cronograma</h1>
          <div className="max-w-lg mx-auto bg-surface border border-border/60 rounded-lg p-6 space-y-4">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </div>
      );
    }
    const sugestaoDataProva =
      mapasData?.mapas.find((m) => m.caderno_ids.includes(Number(id)))?.data_prova ?? null;
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold mb-4">Criar cronograma</h1>
        <ConfigForm submitLabel="Gerar cronograma" sugestaoDataProva={sugestaoDataProva}
          onSubmit={(input) => criarMutation.mutateAsync(input).then(() => undefined)} />
      </div>
    );
  }

  const invalidar = () => queryClient.invalidateQueries({ queryKey: chave });

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Cronograma</h1>
        <div className="flex gap-2">
          <Link href={`/q/caderno/${id}`}
            className="text-sm border border-border/60 rounded px-3 py-1.5 hover:bg-surface-2">
            ← Ir ao caderno
          </Link>
          <button onClick={() => recalcMutation.mutate()} disabled={recalcMutation.isPending}
            className="text-sm border border-border/60 rounded px-3 py-1.5 hover:bg-surface-2 disabled:opacity-50">
            {recalcMutation.isPending ? "Recalculando…" : "Recalcular automático"}
          </button>
          <button onClick={baixarXlsx}
            className="text-sm bg-primary text-black font-semibold rounded px-3 py-1.5 hover:opacity-90">
            Baixar .xlsx
          </button>
        </div>
      </div>

      {/* Veredito: a resposta de "estou atrasado?" em uma frase */}
      <VereditoHero kpis={data.kpis} diasAteProva={diasAteProva} dataProva={data.config.data_prova} />

      {/* O caderno inteiro, questão a questão */}
      <MapaQuestoes cadernoId={id} />

      {/* Ritmo no tempo + distribuição */}
      <div className="grid lg:grid-cols-5 gap-6">
        <section className="bg-surface border border-border/60 rounded-xl p-5 lg:col-span-3">
          <h2 className="text-sm font-semibold text-fg mb-3">Seu ritmo até a prova</h2>
          <RitmoChart plano={data.plano} progresso={data.progresso ?? []} />
        </section>
        <section className="bg-surface border border-border/60 rounded-xl p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold text-fg mb-3">Distribuição do caderno</h2>
          <DistribuicaoDonut kpis={data.kpis} />
        </section>
      </div>

      {/* Onde concentrar a revisão */}
      <ErrosPorAssunto cadernoId={id} />

      <section>
        <h2 className="text-sm font-semibold mb-2 text-fg-muted">Plano diário</h2>
        <TimelineTable plano={data.plano} />
      </section>
      {data.config.incluir_revisao && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Revisar hoje</h2>
          <RevisarHoje itens={data.revisar_hoje} /></section>)}
      {data.config.incluir_discursivas && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Discursivas</h2>
          <DiscursivasList id={id} itens={data.discursivas} onChange={invalidar} /></section>)}
      {data.config.incluir_simulados && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Simulados</h2>
          <SimuladosList id={id} itens={data.simulados} onChange={invalidar} /></section>)}
    </div>
  );
}
