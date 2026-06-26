"use client";

import { useState } from "react";
import { useCriarComentario, useForum } from "../../../hooks/useForum";
import { CommentItem } from "./CommentItem";
import { CommentEditor } from "./CommentEditor";

interface ForumPanelProps {
  questaoId: number;
  onFechar: () => void;
}

export function ForumPanel({ questaoId, onFechar }: ForumPanelProps) {
  const [ordenar, setOrdenar] = useState<"recentes" | "pontos">("recentes");
  const { data, isPending, isError } = useForum(questaoId, ordenar);
  const criar = useCriarComentario(questaoId);

  return (
    <section className="border-y border-border bg-surface-2/30">
      <header className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-fg">
          💬 Fórum de discussão
          {data ? <span className="text-fg-faint">({data.total})</span> : null}
        </h3>
        <div className="flex items-center gap-3 text-xs text-fg-faint">
          <span>Ordenar:</span>
          <button type="button" onClick={() => setOrdenar("recentes")}
            className={ordenar === "recentes" ? "font-semibold text-primary" : "hover:text-fg"}>Data</button>
          <button type="button" onClick={() => setOrdenar("pontos")}
            className={ordenar === "pontos" ? "font-semibold text-primary" : "hover:text-fg"}>Pontos</button>
          <button type="button" onClick={onFechar} className="ml-2 rounded bg-error/80 px-2 py-0.5 text-white">✕ Fechar</button>
        </div>
      </header>

      <div className="px-4 py-3">
        <CommentEditor
          submitting={criar.isPending}
          placeholder="Escreva aqui seu comentário"
          onSubmit={async (texto) => { await criar.mutateAsync({ texto_md: texto }); }}
        />
      </div>

      <div className="divide-y divide-border/50 px-4 pb-4">
        {isPending && <p className="py-4 text-sm text-fg-faint">Carregando…</p>}
        {isError && <p className="py-4 text-sm text-error">Não foi possível carregar o fórum.</p>}
        {data && data.comentarios.length === 0 && (
          <p className="py-4 text-sm text-fg-faint">Seja o primeiro a comentar esta questão.</p>
        )}
        {data?.comentarios.map((c) => (
          <CommentItem key={c.id} comentario={c} questaoId={questaoId} ordenar={ordenar} podeResponder />
        ))}
      </div>
    </section>
  );
}
