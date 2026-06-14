# Roadmap — React Query v5 (TanStack Query) no studIA

> Mapa do que falta para a adoção **full** do TanStack Query v5 no frontend (`fontend/`).
> Estado atual: **0%** — todo fetch é `apiFetch/apiJson/apiPost` (de `lib/api.ts`) dentro de
> `useEffect`+`useState`, com **polling manual** (`setInterval`) em 9 telas.
> Stack: Next 16.1.6 (App Router) + React 19.2.3. Providers atuais: `ThemeProvider` (next-themes).

## Princípios

- **Não trocar o transporte:** `apiFetch/apiJson` continuam sendo a camada HTTP (já fazem CSRF + handoff JWT 401→retry). O React Query entra **por cima** como cache/estado de servidor — `queryFn: () => apiJson(...)`.
- **Páginas são client + autenticadas** → foco em cache client-side, dedup, refetch e `refetchInterval` (não em SSR/hydration, que é Fase 4 opcional).
- **SSE fica de fora:** chat com streaming (`AulaChat` → `/api/aulas/{id}/chat`) NÃO vira `useQuery`/`useMutation` (RQ não modela stream bem) — permanece `fetch` streaming, no máximo encapsulado num hook.

---

## Fase 0 — Fundação (sem mudança de comportamento)

**Deliverables:**
- `@tanstack/react-query` (+ `@tanstack/react-query-devtools` em dev).
- `fontend/lib/query.ts` — factory do `QueryClient` (defaults: `staleTime` 30s, `gcTime` 5min, `retry` 1, `refetchOnWindowFocus` false).
- `fontend/app/components/QueryProvider.tsx` — `"use client"`, monta `QueryClient` via `useState(() => makeClient())` (instância estável por render-tree), `<QueryClientProvider>` + devtools.
- `layout.tsx` — aninhar `QueryProvider` dentro de `ThemeProvider`, em volta do `AppShell`.
- `fontend/lib/queryKeys.ts` — convenção central de chaves (ex.: `qk.disciplinas()`, `qk.aula(id)`, `qk.cadernos(pasta)`, `qk.questao(id)`…).

**Exit:** app sobe igual, devtools aparece em dev, nenhuma tela ainda migrada.

---

## Fase 1 — Alto valor (escopo APROVADO p/ executar agora)

As telas de **maior ROI**: mata polling manual e dá cache às listas quentes + mutações com invalidação.

### 1a. Polling manual → `useQuery({ refetchInterval })`
| Tela | Endpoint(s) | Condição de parada |
|---|---|---|
| `disciplinas/[slug]/aulas/[id]` | `/api/aulas/{id}` | parar quando `status==="CONCLUIDO"` (ou `ERRO`) |
| `disciplinas/[slug]` | `/api/disciplinas/{slug}` + `/aulas` | parar quando nenhuma aula PENDENTE/PROCESSANDO |
| `flashcards/[id]` | `/api/flashcards/{id}` | idem (aula em processamento) |
| `jobs` | `/api/jobs`, `/api/batch-jobs` | intervalo fixo (ex. 5s) enquanto houver job ativo |
| `q/coletar` | `/api/q/coletar/jobs` | enquanto houver job Running/pending |
| `q/coletar/GuiasPanel` | `/api/q/guias` | enquanto materialização em curso |
| `q/guias`, `q/guias/[id]` | `/api/q/guias`, `/api/q/guias/{id}` | enquanto coleta/materialização ativa |
| `assinar` | billing status | parar quando `plano==="pro"` (pós-checkout) |

### 1b. Listas quentes → `useQuery`
| Tela | Endpoint |
|---|---|
| `disciplinas` | `GET /api/disciplinas` |
| `flashcards` | `GET /api/decks` |
| `q/cadernos` | `GET /api/q/pastas`, `GET /api/q/cadernos?pasta=` |
| `painel/PainelClient` | `GET /api/q/dashboard` |
| `UserNav` | `GET /api/billing/status` |

### 1c. Mutações núcleo → `useMutation` + `invalidateQueries`
| Ação | Endpoint | Invalida |
|---|---|---|
| Criar disciplina | `POST /api/disciplinas` | `qk.disciplinas()` |
| Upload de aula | `POST /api/disciplinas/{slug}/aulas` | `qk.disciplina(slug)` + aulas |
| Criar/Importar card | `POST /api/flashcards`, `/import` | `qk.decks()` |
| Excluir deck | `DELETE /api/decks/{id}` | `qk.decks()` |
| Favoritar / Responder | `POST /api/q/{id}/favoritar`, `/responder` | favoritas + stats do caderno |

**Exit Fase 1:** zero `setInterval` de fetch nas telas acima; listas quentes e mutações núcleo no RQ.

---

## Fase 2 — Resto das leituras e mutações (consistência)

| Tela / módulo | O que falta migrar |
|---|---|
| `q/caderno/[id]` (a maior) | reads: `/{qid}`, `gabarito`, `indice`, `stats-detalhe`, `estatisticas`, `favoritas`, `limite`; mutations: `responder`, `favoritar` (com **optimistic update**) |
| `q/caderno/[id]/annotations/api.ts` | virar mutation fns: anotações `POST/PUT`, histórico de calculadora |
| `q/filtrar` | `categorias-arvore`, `count` (debounced), `pastas`, `favoritas`, `cadernos` — query keys por combinação de filtro |
| `q/questao/[id]` | `GET /api/q/{id}` |
| `q/coletar` + `GuiasPanel` (mutations) | `coletar`, `recoletar`, `materializar`, jobs `pausar/retomar` |
| `q/guias/[id]` (mutations) | `coletar`, `materializar`, `salvar`, `DELETE` |
| `concorrencia` | CRUD concursos: `GET`, `POST`, `DELETE`, `import`, `simular` |
| `jobs` (mutation) | `cancel` batch-job |
| `UserNav` (mutation) | `logout` (opcional via RQ; já é simples) |

**Exit Fase 2:** todo fetch de dados via RQ, exceto SSE.

---

## Fase 3 — Full / polimento

- **Auditoria "zero raw fetch":** nenhum `useEffect`+`apiFetch` de leitura restante (grep limpo); exceções SSE documentadas (`AulaChat`, chat).
- **Optimistic updates** onde melhora UX: `favoritar`, `responder`, anotações.
- **Prefetch** em hover/navegação (ex.: `queryClient.prefetchQuery` ao passar o mouse num caderno/disciplina).
- **Devtools** só em dev; `QueryClient` com `dehydrate`/erro global (toast) padronizado.
- **Convenção anti-regressão:** doc curto + (opcional) regra de lint proibindo `apiFetch` dentro de `useEffect` para leitura.

**Exit Fase 3:** padrão único de estado de servidor; novas telas nascem em RQ.

---

## Fase 4 — Opcional (SSR/Hydration App Router)

Só se houver necessidade de SEO/first-paint nessas páginas (hoje são autenticadas, baixo valor):
`prefetchQuery` em Server Components + `<HydrationBoundary>`. Maior esforço; deixar por último.

---

## Resumo de esforço

| Fase | Telas | Risco | Quando |
|---|---|---|---|
| 0 Fundação | infra | baixo | agora |
| 1 Alto valor | ~13 | baixo-médio | agora (aprovado) |
| 2 Resto | ~8 (1 grande: caderno) | médio | depois |
| 3 Polimento | transversal | baixo | depois |
| 4 SSR | opcional | médio | se precisar |

**Exceções permanentes (não-RQ):** `AulaChat` (SSE), qualquer chat com streaming.
