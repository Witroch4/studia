"use client";

import { useEffect, useRef, useState } from "react";
import { useCriarComentario, useForum, useImportarComentariosTc, type Quadro } from "../../../hooks/useForum";
import { CommentItem } from "./CommentItem";
import { CommentEditor } from "./CommentEditor";
import { BrandLoader } from "../../../../components/ds/BrandLoader";
import { Skeleton } from "../../../../components/ds/Skeleton";

interface ForumPanelProps {
  questaoId: number;
  quadro: Quadro;
  podeEscrever: boolean;
  onFechar: () => void;
}

export function ForumPanel({ questaoId, quadro, podeEscrever, onFechar }: ForumPanelProps) {
  const [ordenar, setOrdenar] = useState<"recentes" | "pontos">("recentes");
  const { data, isPending, isError } = useForum(questaoId, quadro, ordenar);
  const criar = useCriarComentario(questaoId, quadro);
  const importar = useImportarComentariosTc(questaoId, quadro);
  const jaDisparou = useRef(false);
  useEffect(() => {
    if (!jaDisparou.current && data && data.tc_importado === false && !importar.isPending) {
      jaDisparou.current = true;
      importar.mutate();
    }
  }, [data, importar]);

  // "importando" cobre o import ao vivo E o gap entre o GET resolver e o
  // mutate disparar (tc_importado=false) — assim o BrandLoader segura o espaço
  // e nunca pisca o estado-vazio antes dos comentários chegarem.
  const importando = importar.isPending || data?.tc_importado === false;

  const ehProf = quadro === "professores";
  const titulo = ehProf ? "🎓 Fórum dos professores" : "💬 Fórum de discussão";

  return (
    <section className="border-y border-border bg-surface-2/30">
      <header className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-fg">
          {titulo}
          {/* Contador só quando estável — não pisca (0)→(2) durante o import. */}
          {data && !importando ? <span className="text-fg-faint">({data.total})</span> : null}
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

      {podeEscrever ? (
        <div className="px-4 py-3">
          <CommentEditor
            submitting={criar.isPending}
            placeholder={ehProf ? "Escreva a explicação do professor" : "Escreva aqui seu comentário"}
            onSubmit={async (texto) => { await criar.mutateAsync({ texto_md: texto }); }}
          />
        </div>
      ) : ehProf ? (
        <p className="px-4 py-3 text-xs text-fg-faint">
          Somente professores podem escrever aqui. Você pode ler e votar nas explicações.
        </p>
      ) : null}

      <div className="divide-y divide-border/50 px-4 pb-4" aria-busy={isPending || importando}>
        {/* Carga do banco (rápida): skeleton no formato dos comentários. */}
        {isPending && <ForumSkeleton />}

        {isError && <p className="py-4 text-sm text-error">Não foi possível carregar o fórum.</p>}

        {/* Comentários já disponíveis renderizam estáveis (não saem do lugar). */}
        {!isPending && !isError && data?.comentarios.map((c) => (
          <CommentItem key={c.id} comentario={c} questaoId={questaoId} quadro={quadro}
            ordenar={ordenar} podeResponder={podeEscrever} />
        ))}

        {/* Op. lenta (import ao vivo): loader da marca segura o espaço — os
            comentários entram NO LUGAR dele, sem empurrar nada. */}
        {!isPending && !isError && importando && (
          <BrandLoader className="py-8" label="Buscando comentários…" />
        )}

        {/* Estado-vazio só quando NÃO há import pendente (mata o flash). */}
        {!isPending && !isError && !importando && data && data.comentarios.length === 0 && (
          <p className="py-4 text-sm text-fg-faint">
            {ehProf ? "Nenhuma explicação de professor ainda." : "Seja o primeiro a comentar esta questão."}
          </p>
        )}
      </div>
    </section>
  );
}

/** Placeholder no formato de 3 comentários — evita o "pulo" na carga do banco. */
function ForumSkeleton() {
  return (
    <div className="space-y-5 py-4" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex gap-3">
          <Skeleton className="h-9 w-6 shrink-0" />
          <Skeleton className="h-9 w-9 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2 pt-0.5">
            <Skeleton className="h-3 w-40" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
          </div>
        </div>
      ))}
    </div>
  );
}
