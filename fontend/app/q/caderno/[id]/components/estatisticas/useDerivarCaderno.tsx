"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "@/lib/api";

export type TipoDerivar =
  | "todas"
  | "resolvidas"
  | "acertadas"
  | "erradas"
  | "em_branco"
  | "favoritas"
  | "anotadas";

export const LABEL_DERIVAR: Record<TipoDerivar, string> = {
  todas: "Cópia",
  resolvidas: "Resolvidas",
  acertadas: "Acertadas",
  erradas: "Erradas",
  em_branco: "Em branco",
  favoritas: "Favoritas",
  anotadas: "Anotadas",
};

const DESCRICAO: Record<TipoDerivar, string> = {
  todas: "todas as questões deste caderno (sem levar suas resoluções)",
  resolvidas: "todas as questões que você resolveu",
  acertadas: "as questões que você acertou",
  erradas: "as questões que você errou",
  em_branco: "as questões que você ainda não resolveu",
  favoritas: "as questões que você favoritou",
  anotadas: "as questões em que você fez anotações",
};

/** Recorte opcional (seleção na árvore de matérias/assuntos). */
export interface EscopoDerivar {
  materiaIds?: number[];
  assuntoIds?: number[];
  /** Complemento do nome sugerido, ex.: "Seleção". */
  rotulo?: string;
}

// Lógica compartilhada de "derivar caderno" (aba Estatísticas e cabeçalho da
// questão). Retorna o disparador e a UI dos modais para embutir.
export function useDerivarCaderno(cadernoId: number, cadernoNome: string) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<{ tipo: TipoDerivar; nome: string; escopo?: EscopoDerivar } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [criado, setCriado] = useState<{ id: number; nome: string; total: number } | null>(null);

  const derivarMutation = useMutation({
    mutationFn: (body: { tipo: TipoDerivar; nome: string; escopo?: EscopoDerivar }) =>
      apiPost<{ id: number; nome: string; total: number }>(`/api/q/cadernos/${cadernoId}/derivar`, {
        tipo: body.tipo,
        nome: body.nome,
        materia_ids: body.escopo?.materiaIds?.length ? body.escopo.materiaIds : null,
        assunto_ids: body.escopo?.assuntoIds?.length ? body.escopo.assuntoIds : null,
      }),
    onSuccess: (res) => {
      setCriado(res);
      setDialog(null);
      setErro(null);
      // O caderno novo precisa aparecer em "Minhas pastas".
      queryClient.invalidateQueries({ queryKey: ["q", "cadernos"] });
      queryClient.invalidateQueries({ queryKey: ["q", "pastas"] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : "Não foi possível criar o caderno.";
      setErro(msg);
    },
  });

  function abrirDialog(tipo: TipoDerivar, escopo?: EscopoDerivar) {
    setErro(null);
    const sufixo = escopo?.rotulo ? ` (${escopo.rotulo})` : "";
    setDialog({ tipo, escopo, nome: `${LABEL_DERIVAR[tipo]}${sufixo} — ${cadernoNome}` });
  }

  const modais = (
    <>
      {/* ─── Dialog próprio: criar caderno derivado ─── */}
      {dialog && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => !derivarMutation.isPending && setDialog(null)}
        >
          <div className="w-full max-w-md rounded-2xl border border-primary/30 bg-surface-dark p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-fg-strong">
              {dialog.tipo === "todas"
                ? <>Clonar <span className="text-primary">caderno</span></>
                : <>Criar caderno com as <span className="text-primary">{LABEL_DERIVAR[dialog.tipo].toLowerCase()}</span></>}
            </h2>
            <p className="mt-1 text-sm text-fg-muted">
              Um caderno novo será criado com {DESCRICAO[dialog.tipo]}
              {dialog.escopo?.rotulo ? ", só das matérias/assuntos selecionados" : ""} neste caderno.
            </p>
            <label className="mt-4 block text-xs text-fg-faint">Nome do caderno</label>
            <input
              autoFocus
              value={dialog.nome}
              onChange={(e) => setDialog((d) => (d ? { ...d, nome: e.target.value } : d))}
              onKeyDown={(e) => { if (e.key === "Enter" && dialog.nome.trim()) derivarMutation.mutate(dialog); }}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-primary"
            />
            {erro && <p className="mt-2 text-xs text-error">{erro}</p>}
            <div className="mt-5 flex gap-2">
              <button
                onClick={() => derivarMutation.mutate(dialog)}
                disabled={!dialog.nome.trim() || derivarMutation.isPending}
                className="flex-1 rounded-lg bg-primary py-2.5 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-40 transition"
              >
                {derivarMutation.isPending ? "Criando…" : "Criar caderno"}
              </button>
              <button
                onClick={() => setDialog(null)}
                disabled={derivarMutation.isPending}
                className="rounded-lg border border-border px-4 py-2.5 text-sm text-fg-muted hover:text-fg disabled:opacity-40"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Aviso de caderno criado (fica na tela, com link) ─── */}
      {criado && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setCriado(null)}
        >
          <div className="w-full max-w-sm rounded-2xl border border-success/30 bg-surface-dark p-7 text-center shadow-xl" onClick={(e) => e.stopPropagation()}>
            <span className="material-symbols-outlined text-success text-5xl">task_alt</span>
            <h2 className="mt-3 text-lg font-bold text-fg-strong">Caderno criado</h2>
            <p className="mt-2 text-sm text-fg-muted">
              <span className="text-fg">{criado.nome}</span> — {criado.total} {criado.total === 1 ? "questão" : "questões"}.
            </p>
            <button
              onClick={() => router.push(`/q/caderno/${criado.id}`)}
              className="mt-6 w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-black hover:opacity-90 transition"
            >
              Abrir caderno
            </button>
            <button onClick={() => setCriado(null)} className="mt-2 w-full rounded-lg py-2 text-xs text-fg-faint hover:text-fg">
              Continuar aqui
            </button>
          </div>
        </div>
      )}
    </>
  );

  return { abrirDialog, modais };
}
