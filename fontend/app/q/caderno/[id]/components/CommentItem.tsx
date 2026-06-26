"use client";

import { useState } from "react";
import type { Comentario } from "../../../hooks/useForum";
import {
  useCriarComentario, useEditarComentario, useExcluirComentario, useVotar,
} from "../../../hooks/useForum";
import ForumContent from "../../../../components/ForumContent";
import { CommentEditor } from "./CommentEditor";

function dataRelativa(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" }) +
    " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

interface CommentItemProps {
  comentario: Comentario;
  questaoId: number;
  ordenar: "recentes" | "pontos";
  podeResponder: boolean;
}

export function CommentItem({ comentario: c, questaoId, ordenar, podeResponder }: CommentItemProps) {
  const votar = useVotar(questaoId, ordenar);
  const editar = useEditarComentario(questaoId);
  const excluir = useExcluirComentario(questaoId);
  const responder = useCriarComentario(questaoId);
  const [editando, setEditando] = useState(false);
  const [respondendo, setRespondendo] = useState(false);

  const votarPara = (valor: -1 | 1) => {
    if (votar.isPending) return;
    votar.mutate({ id: c.id, valor: c.meu_voto === valor ? 0 : valor });
  };

  return (
    <div className="flex gap-3 py-3">
      {/* Coluna de voto */}
      <div className="flex w-8 shrink-0 flex-col items-center text-fg-faint">
        <button type="button" aria-label="Votar a favor" disabled={c.removido}
          onClick={() => votarPara(1)}
          className={c.meu_voto === 1 ? "text-primary" : "hover:text-fg"}>▲</button>
        <span className="text-sm font-semibold text-fg">{c.score}</span>
        <button type="button" aria-label="Votar contra" disabled={c.removido}
          onClick={() => votarPara(-1)}
          className={c.meu_voto === -1 ? "text-error" : "hover:text-fg"}>▼</button>
      </div>

      {/* Corpo */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20 text-[10px] font-bold text-primary">
            {c.autor_inicial}
          </span>
          <span className="font-semibold text-fg">{c.display_name}</span>
          <span className="text-fg-faint">{dataRelativa(c.criado_em)}</span>
          {c.editado && <span className="text-fg-faint">(editado)</span>}
        </div>

        <div className="mt-1">
          {c.removido ? (
            <p className="text-sm italic text-fg-faint">[comentário removido]</p>
          ) : editando ? (
            <CommentEditor
              valorInicial={c.texto_md ?? ""}
              submitting={editar.isPending}
              autoFocus
              onSubmit={async (texto) => { await editar.mutateAsync({ id: c.id, texto_md: texto }); setEditando(false); }}
              onCancel={() => setEditando(false)}
            />
          ) : (
            <ForumContent content={c.texto_md ?? ""} />
          )}
        </div>

        {!c.removido && !editando && (
          <div className="mt-1 flex items-center gap-3 text-xs text-fg-faint">
            {podeResponder && c.parent_id === null && (
              <button type="button" onClick={() => setRespondendo((v) => !v)} className="hover:text-fg">Responder</button>
            )}
            {c.posso_editar && <button type="button" onClick={() => setEditando(true)} className="hover:text-fg">Editar</button>}
            {c.posso_excluir && (
              <button type="button" onClick={() => { if (confirm("Excluir este comentário?")) excluir.mutate(c.id); }}
                className="hover:text-error">Excluir</button>
            )}
          </div>
        )}

        {respondendo && (
          <div className="mt-2">
            <CommentEditor
              autoFocus
              submitting={responder.isPending}
              placeholder="Escreva sua resposta"
              onSubmit={async (texto) => { await responder.mutateAsync({ texto_md: texto, parent_id: c.id }); setRespondendo(false); }}
              onCancel={() => setRespondendo(false)}
            />
          </div>
        )}

        {/* Respostas (1 nível) */}
        {c.respostas.length > 0 && (
          <div className="mt-2 space-y-0 border-l-2 border-border/50 pl-3">
            {c.respostas.map((r) => (
              <CommentItem key={r.id} comentario={r} questaoId={questaoId} ordenar={ordenar} podeResponder={false} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
