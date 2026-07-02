"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Skeleton } from "../../../../components/ds";

// ─── Tipos ───────────────────────────────────────────────

export interface ConcursoCatalogoItem {
  id: number;
  nome_completo: string;
  orgao_sigla: string | null;
  orgao_nome: string | null;
  banca_nome: string | null;
  ano: number | null;
  data_aplicacao: string | null;
}

interface CatalogoResponse {
  items: ConcursoCatalogoItem[];
  total: number;
}

const PAGE_SIZE = 24;

// ─── Componente ──────────────────────────────────────────

export function PassoConcurso({
  onSelecionar,
}: {
  onSelecionar: (concurso: ConcursoCatalogoItem) => void;
}) {
  const [buscaInput, setBuscaInput] = useState("");
  const [busca, setBusca] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => {
      setBusca(buscaInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [buscaInput]);

  const { data, isPending, isError, refetch } = useQuery<CatalogoResponse>({
    queryKey: qk.concursosCatalogo(busca, page),
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (busca) params.set("busca", busca);
      return apiJson<CatalogoResponse>(`/api/q/concursos/catalogo?${params.toString()}`, {
        cache: "no-store",
      });
    },
    placeholderData: keepPreviousData,
  });

  const itens = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-fg-strong">1. Escolha o concurso</h2>
        <p className="text-sm text-fg-muted mt-1">
          Selecione o concurso — a IA vai ler o edital para montar o seu plano.
        </p>
      </div>

      <input
        type="text"
        value={buscaInput}
        onChange={(e) => setBuscaInput(e.target.value)}
        placeholder="Buscar por nome, órgão ou banca…"
        className="h-10 w-full rounded-lg border border-border bg-surface-2 px-3 text-sm text-fg focus:border-primary focus:outline-none"
      />

      {isPending && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      )}

      {!isPending && isError && (
        <div className="rounded-xl border border-error/40 bg-error/10 px-4 py-3 text-sm text-error flex items-center justify-between gap-3">
          <span>Não foi possível carregar o catálogo de concursos.</span>
          <button
            onClick={() => void refetch()}
            className="text-xs bg-surface-2 hover:bg-fg-strong/6 px-3 py-1.5 rounded font-medium text-fg shrink-0"
          >
            Tentar de novo
          </button>
        </div>
      )}

      {!isPending && !isError && itens.length === 0 && (
        <div className="rounded-xl border border-border bg-surface p-8 text-center text-sm text-fg-muted">
          {busca
            ? "Nenhum concurso encontrado para essa busca."
            : "Ainda não há concursos com edital coletado. Peça a um admin para coletar."}
        </div>
      )}

      {!isPending && !isError && itens.length > 0 && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {itens.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => onSelecionar(c)}
                className="text-left rounded-xl border border-border bg-surface p-4 space-y-1.5 transition hover:border-primary/50 hover:bg-primary/5"
              >
                <p className="text-xs text-fg-faint">
                  {[c.banca_nome, c.orgao_sigla].filter(Boolean).join(" · ") || "—"}
                </p>
                <h3 className="font-medium text-fg-strong leading-snug line-clamp-2">
                  {c.nome_completo}
                </h3>
                <p className="text-xs text-fg-muted">{c.ano ?? "Ano não informado"}</p>
              </button>
            ))}
          </div>

          {totalPaginas > 1 && (
            <div className="flex items-center justify-between text-xs text-fg-muted">
              <span>
                Página {page} de {totalPaginas}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="rounded border border-border bg-surface-2 px-3 py-1.5 font-medium text-fg disabled:opacity-40"
                >
                  Anterior
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPaginas, p + 1))}
                  disabled={page >= totalPaginas}
                  className="rounded border border-border bg-surface-2 px-3 py-1.5 font-medium text-fg disabled:opacity-40"
                >
                  Próxima
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
