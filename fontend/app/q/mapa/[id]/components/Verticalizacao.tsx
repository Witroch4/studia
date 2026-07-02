"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

// ─── Tipos ───────────────────────────────────────────────

export type StatusItem = "nao_visto" | "estudando" | "dominado";

export interface ItemVerticalizacao {
  id: number;
  assunto_texto: string;
  status: StatusItem;
}

export interface GrupoMateria {
  materia_nome: string;
  materia_id: number | null;
  caderno_id: number | null;
  itens: ItemVerticalizacao[];
}

/** Forma mínima do cache de `qk.mapa(id)` que este componente atualiza — o
 * restante das chaves do objeto real (`MapaDetalhe`) é preservado pelo spread
 * em `onMutate`, mas não precisa ser conhecido aqui. */
interface MapaCacheComVerticalizacao {
  verticalizacao: GrupoMateria[];
}

// ─── Helpers ─────────────────────────────────────────────

const PROXIMO_STATUS: Record<StatusItem, StatusItem> = {
  nao_visto: "estudando",
  estudando: "dominado",
  dominado: "nao_visto",
};

const STATUS_CFG: Record<StatusItem, { icon: string; filled: boolean; cls: string; label: string }> = {
  nao_visto: { icon: "radio_button_unchecked", filled: false, cls: "text-fg-faint", label: "Não visto" },
  estudando: { icon: "adjust", filled: false, cls: "text-warning", label: "Estudando" },
  dominado: { icon: "check_circle", filled: true, cls: "text-success", label: "Dominado" },
};

// ─── Componente ──────────────────────────────────────────

/**
 * Accordion por matéria do edital verticalizado. Cada assunto é clicável e
 * cicla nao_visto → estudando → dominado → nao_visto via PATCH otimista
 * (React Query v5: onMutate cancela + snapshot + setQueryData; onError
 * restaura o snapshot; onSettled invalida para reconciliar com o servidor).
 */
export function Verticalizacao({
  mapaId,
  grupos,
}: {
  mapaId: string | number;
  grupos: GrupoMateria[];
}) {
  const queryClient = useQueryClient();
  const [abertos, setAbertos] = useState<Set<string>>(
    () => new Set(grupos.length > 0 ? [grupos[0].materia_nome] : [])
  );

  const cicloMutation = useMutation({
    mutationFn: ({ itemId, status }: { itemId: number; status: StatusItem }) =>
      apiJson(`/api/q/mapas/${mapaId}/itens/${itemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      }),
    onMutate: async ({ itemId, status }) => {
      await queryClient.cancelQueries({ queryKey: qk.mapa(mapaId) });
      const anterior = queryClient.getQueryData<MapaCacheComVerticalizacao>(qk.mapa(mapaId));
      queryClient.setQueryData<MapaCacheComVerticalizacao>(qk.mapa(mapaId), (old) => {
        if (!old) return old;
        return {
          ...old,
          verticalizacao: old.verticalizacao.map((g) => ({
            ...g,
            itens: g.itens.map((it) => (it.id === itemId ? { ...it, status } : it)),
          })),
        };
      });
      return { anterior };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.anterior) queryClient.setQueryData(qk.mapa(mapaId), ctx.anterior);
      toast.error("Não foi possível atualizar o assunto. Tente de novo.");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.mapa(mapaId) });
    },
  });

  function toggleGrupo(nome: string) {
    setAbertos((prev) => {
      const next = new Set(prev);
      if (next.has(nome)) next.delete(nome);
      else next.add(nome);
      return next;
    });
  }

  function ciclar(item: ItemVerticalizacao) {
    cicloMutation.mutate({ itemId: item.id, status: PROXIMO_STATUS[item.status] });
  }

  if (grupos.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface p-6 text-center text-sm text-fg-muted">
        Nenhuma matéria verticalizada para este cargo.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface divide-y divide-border overflow-hidden">
      {grupos.map((g) => {
        const total = g.itens.length;
        const dominados = g.itens.filter((i) => i.status === "dominado").length;
        const aberto = abertos.has(g.materia_nome);
        return (
          <div key={g.materia_nome}>
            <div className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-fg/5 transition">
              <button
                type="button"
                onClick={() => toggleGrupo(g.materia_nome)}
                className="flex items-center gap-2 min-w-0 flex-1 text-left"
                aria-expanded={aberto}
              >
                <span
                  className={`material-symbols-outlined text-[18px] text-fg-faint transition-transform shrink-0 ${
                    aberto ? "rotate-90" : ""
                  }`}
                >
                  chevron_right
                </span>
                <span className="font-medium text-fg-strong truncate">{g.materia_nome}</span>
                <span className="text-xs text-fg-muted shrink-0">
                  {dominados}/{total} dominados
                </span>
              </button>
              {g.caderno_id && (
                <Link
                  href={`/q/caderno/${g.caderno_id}`}
                  className="text-xs text-primary hover:underline shrink-0"
                >
                  caderno →
                </Link>
              )}
            </div>
            {aberto && (
              <ul className="px-4 pb-3 space-y-0.5">
                {g.itens.map((item) => {
                  const cfg = STATUS_CFG[item.status];
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => ciclar(item)}
                        className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-fg/5 transition"
                        title={`${cfg.label} — clique para avançar`}
                      >
                        <span
                          className={`material-symbols-outlined text-[18px] shrink-0 ${cfg.cls}`}
                          style={{ fontVariationSettings: `'FILL' ${cfg.filled ? 1 : 0}` }}
                        >
                          {cfg.icon}
                        </span>
                        <span
                          className={
                            item.status === "dominado" ? "text-fg-muted line-through" : "text-fg"
                          }
                        >
                          {item.assunto_texto}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
