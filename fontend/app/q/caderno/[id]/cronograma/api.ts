import { apiFetch } from "@/lib/api";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export type CronogramaConfig = {
  caderno_id: number;
  data_inicio: string;
  data_prova: string;
  rebaseline_em: string | null;
  dias_folga: number[];
  buffer_dias: number;
  incluir_revisao: boolean;
  incluir_discursivas: boolean;
  incluir_simulados: boolean;
  discursivas_por_semana: number;
};

export type DiaPlano = {
  data: string;
  weekday: number;
  fase: string;
  questoes_novas: number;
  meta_acumulada: number;
  hoje: boolean;
};

export type Kpis = {
  total: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  pct_conclusao: number;
  pct_acerto: number;
  restantes: number;
  dias_uteis_restantes: number;
  questoes_dia_necessarias: number;
  meta_hoje: number;
  saldo: number;
};

export type Discursiva = {
  id: number;
  data: string;
  tema: string;
  tipo: string;
  qtd: number;
  status: string;
  nota: number | null;
  reescrita: boolean;
  observacoes: string | null;
};

export type Simulado = {
  id: number;
  data: string;
  tipo: string;
  objetivas_planejadas: number;
  meta_objetiva: number;
  resultado_objetiva: number | null;
  discursiva_planejada: number;
  resultado_discursiva: number | null;
  observacoes: string | null;
};

export type RevisaoItem = {
  questao_id: number;
  revisar_em: string;
  intervalo: string;
};

/** Curva real acumulada: questões distintas resolvidas até cada dia. */
export type ProgressoDia = {
  data: string;
  resolvidas: number;
};

export type CronogramaResp = {
  config: CronogramaConfig;
  plano: DiaPlano[];
  kpis: Kpis;
  progresso: ProgressoDia[];
  revisar_hoje: RevisaoItem[];
  discursivas: Discursiva[];
  simulados: Simulado[];
};

// Tipos dos endpoints reaproveitados pelos gráficos (indice / minhas-resolucoes
// / stats-detalhe já existem no backend e são cacheados junto com o quiz).

export type IndiceItem = {
  n: number;
  questao_id: number;
  banca: string | null;
  materia: string | null;
  preview: string;
};

export type MinhasResolucoes = {
  caderno_id: number;
  resolucoes: Record<string, { resposta: string | null; acertou: boolean }>;
};

export type GrupoStat = {
  nome: string;
  resolvidas: number;
  acertos: number;
  taxa: number;
};

export type StatsDetalheResp = {
  questoes_total: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  por_materia: GrupoStat[];
  por_assunto: GrupoStat[];
  por_banca: GrupoStat[];
};

export type CronogramaInput = {
  data_prova: string;
  data_inicio: string;
  dias_folga: number[];
  buffer_dias: number;
  incluir_revisao: boolean;
  incluir_discursivas: boolean;
  incluir_simulados: boolean;
  discursivas_por_semana: number;
};

// ---------------------------------------------------------------------------
// Helpers internos
// ---------------------------------------------------------------------------

const base = (id: string | number) => `/api/q/cadernos/${id}/cronograma`;

const JSON_HEADERS = { "Content-Type": "application/json" };

// ---------------------------------------------------------------------------
// Funções de API
// ---------------------------------------------------------------------------

export async function getCronograma(
  id: string
): Promise<CronogramaResp | null> {
  const r = await apiFetch(base(id));
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("falha ao carregar cronograma");
  return r.json();
}

export async function criarCronograma(
  id: string,
  body: CronogramaInput
): Promise<CronogramaResp> {
  const r = await apiFetch(base(id), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "falha ao criar");
  return r.json();
}

export async function atualizarCronograma(
  id: string,
  body: CronogramaInput
): Promise<CronogramaResp> {
  const r = await apiFetch(base(id), {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error("falha ao atualizar");
  return r.json();
}

export async function recalcular(id: string): Promise<CronogramaResp> {
  const r = await apiFetch(`${base(id)}/recalcular`, { method: "POST" });
  if (!r.ok) throw new Error("falha ao recalcular");
  return r.json();
}

export async function deletarCronograma(id: string): Promise<void> {
  await apiFetch(base(id), { method: "DELETE" });
}

export async function patchDiscursiva(
  id: string,
  did: number,
  body: Partial<Discursiva>
): Promise<void> {
  await apiFetch(`${base(id)}/discursivas/${did}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export async function regenerarDiscursivas(
  id: string
): Promise<CronogramaResp> {
  const r = await apiFetch(`${base(id)}/discursivas/regenerar`, {
    method: "POST",
  });
  if (!r.ok) throw new Error("falha ao regenerar");
  return r.json();
}

export async function patchSimulado(
  id: string,
  sid: number,
  body: Partial<Simulado>
): Promise<void> {
  await apiFetch(`${base(id)}/simulados/${sid}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}
