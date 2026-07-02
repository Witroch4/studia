"use client";

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiJson, apiPost } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { BrandLoader } from "../../../../components/ds";
import type { ConcursoCatalogoItem } from "./PassoConcurso";

// ─── Tipos ───────────────────────────────────────────────

export interface EventoEdital {
  titulo: string;
  data_inicio: string | null;
  data_fim: string | null;
  tipo: string;
}

export interface MateriaProgramatica {
  materia: string;
  assuntos: string[];
}

export interface CargoEdital {
  nome: string;
  escolaridade: string | null;
  vagas: string | null;
  salario: string | null;
  requisitos: string | null;
  jornada: string | null;
  conteudo_programatico: MateriaProgramatica[];
  etapas: { nome: string; carater: string | null }[];
  distribuicao_questoes: { materia: string; quantidade: number | null; peso: number | null }[];
}

export interface DadosExtracao {
  concurso: {
    orgao: string | null;
    banca: string | null;
    taxa_inscricao: string | null;
    data_prova: string | null;
  };
  eventos: EventoEdital[];
  cargos: CargoEdital[];
}

interface ExtracaoStatus {
  status: "nao_iniciada" | "pendente" | "processando" | "concluido" | "erro";
  erro_msg: string | null;
  dados?: DadosExtracao;
}

// ─── Componente ──────────────────────────────────────────

export function PassoExtracao({
  concurso,
  onConcluido,
  onTrocarConcurso,
}: {
  concurso: ConcursoCatalogoItem;
  onConcluido: (dados: DadosExtracao) => void;
  onTrocarConcurso: () => void;
}) {
  const queryClient = useQueryClient();

  const { data } = useQuery<ExtracaoStatus>({
    queryKey: qk.mapaExtracao(concurso.id),
    queryFn: () =>
      apiJson<ExtracaoStatus>(`/api/q/mapas/extracao/${concurso.id}`, { cache: "no-store" }),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "concluido" || s === "erro" ? false : 4000;
    },
  });

  const extrair = useMutation({
    // ApiError de apiPost carrega o detail do backend (ex.: 409 "sem edital").
    mutationFn: () => apiPost("/api/q/mapas/extrair", { concurso_id: concurso.id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.mapaExtracao(concurso.id) });
    },
  });

  // Dispara a extração uma única vez, assim que soubermos que ainda não foi
  // iniciada — mesmo padrão do import lazy de comentários (ForumPanel.tsx).
  const jaDisparou = useRef(false);
  useEffect(() => {
    if (!jaDisparou.current && data?.status === "nao_iniciada" && !extrair.isPending) {
      jaDisparou.current = true;
      extrair.mutate();
    }
  }, [data, extrair]);

  // Avança o wizard automaticamente assim que a extração termina.
  const jaAvancou = useRef(false);
  useEffect(() => {
    if (!jaAvancou.current && data?.status === "concluido" && data.dados) {
      jaAvancou.current = true;
      onConcluido(data.dados);
    }
  }, [data, onConcluido]);

  function tentarDeNovo() {
    extrair.mutate();
  }

  const status = data?.status;
  // Cobre TANTO a extração que terminou em erro (status do polling) quanto a
  // falha do próprio POST /extrair (rede/500) — senão o usuário ficaria preso
  // no BrandLoader para sempre, sem erro nem retry.
  const comErro = status === "erro" || extrair.isError;
  const msgErro =
    status === "erro"
      ? data?.erro_msg
      : extrair.isError
      ? extrair.error.message
      : null;

  return (
    <section className="space-y-4">
      <button
        type="button"
        onClick={onTrocarConcurso}
        className="text-xs text-fg-faint hover:text-primary"
      >
        ‹ Trocar concurso
      </button>

      <div>
        <h2 className="text-lg font-semibold text-fg-strong">2. Lendo o edital</h2>
        <p className="text-sm text-fg-muted mt-1">{concurso.nome_completo}</p>
      </div>

      {!comErro && (
        <div className="rounded-xl border border-border bg-surface p-10">
          <BrandLoader label="studIA está lendo o edital… isso leva um ou dois minutos." />
        </div>
      )}

      {comErro && (
        <div className="rounded-xl border border-error/40 bg-error/10 px-4 py-4 text-sm text-error space-y-3">
          <p>
            Não foi possível ler o edital
            {msgErro ? `: ${msgErro}` : "."}
          </p>
          <button
            type="button"
            onClick={tentarDeNovo}
            disabled={extrair.isPending}
            className="inline-flex items-center gap-1.5 rounded bg-error px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
          >
            <span className={`material-symbols-outlined text-[14px] ${extrair.isPending ? "animate-spin" : ""}`}>
              {extrair.isPending ? "progress_activity" : "refresh"}
            </span>
            Tentar de novo
          </button>
        </div>
      )}
    </section>
  );
}
