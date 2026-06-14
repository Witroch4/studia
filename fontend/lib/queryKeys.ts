/** Convenção central de chaves de query (arrays, do geral ao específico). */
export const qk = {
  disciplinas: () => ["disciplinas"] as const,
  disciplina: (slug: string) => ["disciplinas", slug] as const,
  aula: (id: number) => ["aula", id] as const,
  decks: () => ["decks"] as const,
  dashboard: () => ["q", "dashboard"] as const,
  billing: () => ["billing", "status"] as const,
  pastas: () => ["q", "pastas"] as const,
  cadernos: (pasta?: string | null) => ["q", "cadernos", pasta ?? null] as const,
  guias: () => ["q", "guias"] as const,
  guia: (id: number | string) => ["q", "guias", id] as const,
  coletarJobs: () => ["q", "coletar", "jobs"] as const,
  jobs: () => ["jobs"] as const,
  batchJobs: () => ["batch-jobs"] as const,
};
