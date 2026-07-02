/** Convenção central de chaves de query (arrays, do geral ao específico). */
export const qk = {
  disciplinas: () => ["disciplinas"] as const,
  disciplina: (slug: string) => ["disciplinas", slug] as const,
  aula: (id: number) => ["aula", id] as const,
  decks: () => ["decks"] as const,
  deckCards: (id: string) => ["flashcards", id] as const,
  dashboard: () => ["q", "dashboard"] as const,
  billing: () => ["billing", "status"] as const,
  pastas: () => ["q", "pastas"] as const,
  cadernos: (pasta?: string | null) => ["q", "cadernos", pasta ?? null] as const,
  guias: () => ["q", "guias"] as const,
  guia: (id: number | string) => ["q", "guias", id] as const,
  guiasUsuariosPastas: () => ["q", "guias", "usuarios-pastas"] as const,
  coletarJobs: () => ["q", "coletar", "jobs"] as const,
  tcAuth: () => ["q", "coletar", "tc-auth"] as const,
  comentarioJobs: () => ["q", "coletar", "comentario-jobs"] as const,
  guiaFila: () => ["q", "guias", "fila"] as const,
  jobs: () => ["jobs"] as const,
  batchJobs: () => ["batch-jobs"] as const,
  adminLlmModels: () => ["admin", "llm", "models"] as const,
  adminLlmSettings: () => ["admin", "llm", "settings"] as const,
  vouchers: () => ["vouchers"] as const,
  adminAssinaturasOverview: () => ["admin", "assinaturas", "overview"] as const,
  adminAssinaturas: (q: string, plano: string, page: number) =>
    ["admin", "assinaturas", "lista", q, plano, page] as const,
  adminAssinaturaDetalhe: (uid: string) => ["admin", "assinaturas", "detalhe", uid] as const,
  // Fase 2 — detalhe de caderno (singular "caderno" p/ não colidir com a lista "cadernos")
  caderno: (id: string | number) => ["q", "caderno", String(id)] as const,
  cadernoSub: (id: string | number, sub: string) => ["q", "caderno", String(id), sub] as const, // indice|gabarito|estatisticas|stats-detalhe
  questao: (id: string | number) => ["q", "questao", String(id)] as const,
  favoritas: () => ["q", "favoritas"] as const,
  forum: (questaoId: number | string, quadro: string, ordenar: string) =>
    ["q", "forum", String(questaoId), quadro, ordenar] as const,
  adminUsuarios: (q: string, page: number) =>
    ["admin", "usuarios", q, page] as const,
  limite: () => ["q", "limite"] as const,
  categoriasArvore: () => ["q", "categorias-arvore"] as const,
  count: (filtros: unknown) => ["q", "count", filtros] as const,
  concursos: () => ["concursos"] as const,
};
