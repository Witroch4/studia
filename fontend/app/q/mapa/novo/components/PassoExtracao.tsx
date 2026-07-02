"use client";

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
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

async function parseApiError(r: Response, fallback: string): Promise<string> {
  const data = await r.json().catch(() => null);
  return data?.detail || data?.message || fallback;
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
    queryFn: async () => {
      const r = await apiFetch(`/api/q/mapas/extracao/${concurso.id}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()) as ExtracaoStatus;
    },
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "concluido" || s === "erro" ? false : 4000;
    },
  });

  const extrair = useMutation({
    mutationFn: async () => {
      const r = await apiFetch("/api/q/mapas/extrair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concurso_id: concurso.id }),
      });
      if (!r.ok) throw new Error(await parseApiError(r, `HTTP ${r.status}`));
      return r.json();
    },
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
    jaDisparou.current = true; // já passamos do auto-disparo inicial
    extrair.mutate();
  }

  const status = data?.status;
  const comErro = status === "erro";

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
            {data?.erro_msg ? `: ${data.erro_msg}` : "."}
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
