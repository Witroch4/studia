"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Skeleton } from "@/app/components/ds";
import type { GrupoStat, StatsDetalheResp } from "../api";

const TOP = 12;

/**
 * Onde você está errando: barras horizontais por assunto (ou matéria),
 * ordenadas por número de erros. Cada barra empilha erradas (a partir da
 * baseline) + certas, então o comprimento total = resoluções no grupo.
 * Valores visíveis em texto ao lado — a cor nunca é o único canal.
 */
export function ErrosPorAssunto({ cadernoId }: { cadernoId: string }) {
  const [modo, setModo] = useState<"assunto" | "materia">("assunto");

  const { data, isPending, isError } = useQuery<StatsDetalheResp>({
    queryKey: qk.cadernoSub(cadernoId, "stats-detalhe"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/stats-detalhe`),
    staleTime: 30_000,
  });

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
      <h2 className="text-sm font-semibold text-fg">Onde você está errando</h2>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-3 text-[11px] text-fg-muted">
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] bg-error" /> erradas
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] bg-success" /> certas
          </span>
        </div>
        <div className="flex rounded-md border border-border/60 overflow-hidden text-xs">
          {([["assunto", "Assuntos"], ["materia", "Matérias"]] as const).map(([valor, rotulo]) => (
            <button
              key={valor}
              onClick={() => setModo(valor)}
              aria-pressed={modo === valor}
              className={`px-2.5 py-1 transition ${
                modo === valor ? "bg-primary/15 text-primary font-medium" : "text-fg-muted hover:text-fg"
              }`}
            >
              {rotulo}
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  if (isPending) {
    return (
      <section className="bg-surface border border-border/60 rounded-xl p-5">
        {header}
        <div className="space-y-2.5">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}
        </div>
      </section>
    );
  }
  if (isError || !data) {
    return (
      <section className="bg-surface border border-border/60 rounded-xl p-5">
        {header}
        <p className="text-sm text-fg-muted">Não deu para carregar as estatísticas. Recarregue a página para tentar de novo.</p>
      </section>
    );
  }

  const grupos: GrupoStat[] = modo === "assunto" ? data.por_assunto : data.por_materia;
  const comErro = grupos
    .map((g) => ({ ...g, erros: Math.max(g.resolvidas - g.acertos, 0) }))
    .filter((g) => g.erros > 0)
    .sort((a, b) => b.erros - a.erros);
  const mostrados = comErro.slice(0, TOP);
  const maxResolvidas = Math.max(...mostrados.map((g) => g.resolvidas), 1);

  return (
    <section className="bg-surface border border-border/60 rounded-xl p-5">
      {header}

      {mostrados.length === 0 ? (
        <p className="text-sm text-fg-muted">
          {data.resolvidas === 0
            ? "Resolva questões do caderno para ver onde concentrar a revisão."
            : `Nenhum erro registrado por ${modo === "assunto" ? "assunto" : "matéria"} até agora. 🎉`}
        </p>
      ) : (
        <>
          <ul className="space-y-2">
            {mostrados.map((g) => {
              const wErro = (g.erros / maxResolvidas) * 100;
              const wAcerto = (g.acertos / maxResolvidas) * 100;
              return (
                <li
                  key={g.nome}
                  className="grid grid-cols-[minmax(0,10rem)_1fr_auto] sm:grid-cols-[minmax(0,14rem)_1fr_auto] items-center gap-3"
                  title={`${g.nome}: ${g.erros} erradas e ${g.acertos} certas em ${g.resolvidas} resoluções (${g.taxa}% de acerto)`}
                >
                  <span className="text-xs text-fg-muted truncate">{g.nome}</span>
                  <div className="flex items-center gap-[2px] h-4" aria-hidden>
                    <div className="h-full bg-error" style={{ width: `${wErro}%`, borderRadius: g.acertos > 0 ? "0" : "0 4px 4px 0" }} />
                    {g.acertos > 0 && (
                      <div className="h-full bg-success rounded-r-[4px]" style={{ width: `${wAcerto}%` }} />
                    )}
                  </div>
                  <span className="text-xs tabular-nums whitespace-nowrap">
                    <span className="font-semibold text-fg">{g.erros}</span>
                    <span className="text-fg-muted"> {g.erros === 1 ? "erro" : "erros"}</span>
                    <span className="text-fg-faint"> · {g.taxa}%</span>
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-[11px] text-fg-faint">
            {comErro.length > TOP
              ? `Mostrando os ${TOP} ${modo === "assunto" ? "assuntos" : "matérias"} com mais erros, de ${comErro.length}. `
              : ""}
            Conta cada resolução (re-tentativas incluídas){modo === "assunto" ? "; uma questão pode ter mais de um assunto" : ""}. % = taxa de acerto no grupo.
          </p>
        </>
      )}
    </section>
  );
}
