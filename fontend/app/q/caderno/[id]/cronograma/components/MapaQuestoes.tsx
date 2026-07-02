"use client";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Skeleton } from "@/app/components/ds";
import type { IndiceItem, MinhasResolucoes } from "../api";

/**
 * O caderno inteiro numa grade: 1 célula = 1 questão, na ordem do caderno.
 * Verde = acertou, vermelho = errou, neutro = ainda não resolvida (a legenda
 * com contagens é a codificação secundária — nunca só cor). Clicar numa célula
 * abre a questão no caderno (mesmo mecanismo de posição salva do quiz).
 */
export function MapaQuestoes({ cadernoId }: { cadernoId: string }) {
  const router = useRouter();

  const indiceQ = useQuery<{ items: IndiceItem[] }>({
    queryKey: qk.cadernoSub(cadernoId, "indice"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/indice`),
    staleTime: 5 * 60 * 1000,
  });
  const resQ = useQuery<MinhasResolucoes>({
    queryKey: qk.cadernoSub(cadernoId, "minhas-resolucoes"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/minhas-resolucoes`),
    staleTime: 30_000,
  });

  if (indiceQ.isPending || resQ.isPending) {
    return (
      <section className="bg-surface border border-border/60 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-fg mb-3">Mapa de questões</h2>
        <Skeleton className="h-40 w-full" />
      </section>
    );
  }
  if (indiceQ.isError || resQ.isError) {
    return (
      <section className="bg-surface border border-border/60 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-fg mb-1">Mapa de questões</h2>
        <p className="text-sm text-fg-muted">Não deu para carregar o mapa. Recarregue a página para tentar de novo.</p>
      </section>
    );
  }

  const items = indiceQ.data?.items ?? [];
  const resolucoes = resQ.data?.resolucoes ?? {};

  let acertos = 0;
  let erros = 0;
  for (const it of items) {
    const r = resolucoes[String(it.questao_id)];
    if (!r) continue;
    if (r.acertou) acertos += 1;
    else erros += 1;
  }
  const restantes = items.length - acertos - erros;

  function abrir(n: number) {
    // O quiz retoma da posição salva — mesmo contrato do idxStorageKey da página do caderno.
    window.localStorage.setItem(`studia:caderno:${cadernoId}:idx`, String(n - 1));
    router.push(`/q/caderno/${cadernoId}`);
  }

  return (
    <section className="bg-surface border border-border/60 rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h2 className="text-sm font-semibold text-fg">Mapa de questões</h2>
        <div className="flex items-center gap-4 text-xs text-fg-muted">
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] bg-success" />
            {acertos} certas
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] bg-error" />
            {erros} erradas
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] bg-fg/15" />
            {restantes} restantes
          </span>
        </div>
      </div>

      <div
        className="flex flex-wrap gap-[3px] max-h-72 overflow-y-auto pr-1"
        role="group"
        aria-label={`Mapa das ${items.length} questões do caderno`}
      >
        {items.map((it) => {
          const r = resolucoes[String(it.questao_id)];
          const status = !r ? "restante" : r.acertou ? "acerto" : "erro";
          const cor =
            status === "acerto" ? "bg-success hover:brightness-110"
            : status === "erro" ? "bg-error hover:brightness-110"
            : "bg-fg/15 hover:bg-fg/30";
          const statusLabel =
            status === "acerto" ? "acertou" : status === "erro" ? "errou" : "não resolvida";
          return (
            <button
              key={it.questao_id}
              onClick={() => abrir(it.n)}
              title={`#${it.n} · ${it.materia ?? "—"} · ${statusLabel}`}
              aria-label={`Abrir questão ${it.n} (${statusLabel})`}
              className={`w-3.5 h-3.5 rounded-[3px] ${cor} transition
                focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary`}
            />
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-fg-faint">Clique numa célula para abrir a questão no caderno.</p>
    </section>
  );
}
