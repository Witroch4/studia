# React Query v5 — Fase 2 (telas restantes) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Convenções já codificadas na Fase 0+1 (deployada).

**Goal:** Migrar as telas restantes que ainda usam `apiFetch`-em-`useEffect` para TanStack Query v5, seguindo as convenções já estabelecidas. Ao fim, só SSE (AulaChat) fica fora.

**Convenções (idênticas à Fase 0+1):** RQ por cima de `apiJson/apiFetch/apiPost` (não trocar transporte); **skeleton só no load inicial (`isPending`)**; refetch/poll/mutation nunca derruba pra skeleton; chaves via `qk` (`lib/queryKeys.ts`); mutação → `useMutation` + `invalidateQueries`; `placeholderData: keepPreviousData` em filtros; gate por task = `pnpm lint` (0 erros) + `npx tsc --noEmit` (limpo); build no fim.

**Não migrar:** `AulaChat` (SSE streaming).

---

## Extensão do `qk` (lib/queryKeys.ts) — adicionar

```ts
  caderno: (id: string | number) => ["q", "cadernos", String(id)] as const,
  cadernoSub: (id: string | number, sub: string) => ["q", "cadernos", String(id), sub] as const, // indice|gabarito|estatisticas|stats-detalhe
  questao: (id: string | number) => ["q", "questao", String(id)] as const,
  favoritas: () => ["q", "favoritas"] as const,
  limite: () => ["q", "limite"] as const,
  categoriasArvore: () => ["q", "categorias-arvore"] as const,
  count: (filtros: unknown) => ["q", "count", filtros] as const,
  concursos: () => ["concursos"] as const,
```

---

### Task A — Reads simples: `q/cadernos` + `q/questao/[id]`

- `fontend/app/q/cadernos/page.tsx` (203 ln): reads `GET /api/q/pastas` → `useQuery(qk.pastas())`; `GET /api/q/cadernos?pasta=` → `useQuery(qk.cadernos(pasta), { placeholderData: keepPreviousData })`; `GET /api/q/cadernos/{id}/estatisticas` → `useQuery(qk.cadernoSub(id,"estatisticas"))` (por caderno, conforme uso). Skeleton só `isPending`.
- `fontend/app/q/questao/[id]/page.tsx` (224 ln): read `GET /api/q/{id}` → `useQuery(qk.questao(id))`. Skeleton só `isPending`. Se houver mutação (favoritar), `useMutation` + invalidate `qk.favoritas()`/`qk.questao(id)`.

Gate: lint + tsc. Commit: `feat(rq): migra q/cadernos e q/questao p/ useQuery`.

---

### Task B — `q/filtrar` (filtros + count)

- `fontend/app/q/filtrar/page.tsx` (533 ln, 16 useState): reads `categorias-arvore` → `useQuery(qk.categoriasArvore())`; `pastas` → `qk.pastas()`; `favoritas` → `qk.favoritas()`; `cadernos` → `qk.cadernos(...)`; **`count`** (POST com filtros) → `useQuery({ queryKey: qk.count(filtros), queryFn: () => apiPost("/api/q/count", filtros), placeholderData: keepPreviousData })` — manter o **debounce** existente (ex.: alimentar `filtros` num state debounced que entra na queryKey). Preservar todo o estado de UI de filtros. Skeleton só no load inicial das árvores; o count usa `isFetching` apenas para um spinner sutil (sem skeleton).

Gate: lint + tsc. Commit: `feat(rq): migra q/filtrar (árvore/contagem) p/ useQuery + keepPreviousData`.

---

### Task C — `concorrencia` (CRUD admin)

- `fontend/app/concorrencia/page.tsx` (748 ln, 20 useState): read `GET /api/concursos` → `useQuery(qk.concursos())`; mutações `POST /api/concursos`, `POST /api/concursos/import`, `DELETE /api/concursos/{id}`, `POST /api/concursos/{id}/simular` → `useMutation` + invalidate `qk.concursos()` (simular pode retornar dado sem invalidar a lista — avaliar). Preservar todo o estado/UX. Skeleton só `isPending`.

Gate: lint + tsc. Commit: `feat(rq): migra concorrencia (CRUD) p/ useQuery/useMutation`.

---

### Task D — `q/caderno/[id]` (NÚCLEO, conservador) + annotations

> **ALTO RISCO** (1035 ln, 27 useState, loop de responder). Regra: **preservar 100% do comportamento**; migrar SÓ a camada de dados; **SEM optimistic update** (invalidação simples); manter todos os `useEffect` não-fetch (timer de sessão, navegação, atalhos) e os 27 `useState` de UI.

- `fontend/app/q/caderno/[id]/page.tsx`:
  - Reads → `useQuery`: `cadernos/{id}` → `qk.caderno(id)`; `indice` → `qk.cadernoSub(id,"indice")`; `gabarito` → `qk.cadernoSub(id,"gabarito")`; `estatisticas` → `qk.cadernoSub(id,"estatisticas")`; `stats-detalhe` → `qk.cadernoSub(id,"stats-detalhe")`; `q/{currentQid}` → `qk.questao(currentQid)` (habilitar com `enabled: !!currentQid`); `favoritas` → `qk.favoritas()`; `limite` → `qk.limite()`.
  - Mutações → `useMutation` + invalidate: `responder` → invalidar `qk.cadernoSub(id,"estatisticas")`, `qk.cadernoSub(id,"stats-detalhe")`, `qk.limite()`, `qk.cadernoSub(id,"gabarito")`; `favoritar` → invalidar `qk.favoritas()` (+ `qk.questao(qid)`).
  - O `setInterval` é timer de sessão (UI) — **manter**.
  - Skeleton só no load inicial do caderno; trocar de questão usa `isFetching`/placeholder (sem skeleton cheio).
- `fontend/app/q/caderno/[id]/annotations/api.ts` (49 ln): pode permanecer como funções de fetch chamadas por `useMutation` na página; garantir invalidação da query de anotações após `POST/PUT`.

Gate: lint + tsc. Commit: `feat(rq): migra q/caderno (núcleo) p/ useQuery/useMutation (sem optimistic)`.
**⚠️ Requer smoke humano no browser** (responder questão, navegar, favoritar, stats) — sinalizar ao usuário.

---

### Task E — Build + deploy + smoke

- Build: `docker exec studia-frontend-dev sh -lc 'cd /app && pnpm build'` (exit 0).
- Auditoria: `grep -rlnE "apiFetch|apiJson|apiPost" fontend/app | xargs grep -lE "useEffect\(\(\) =>" ` — só devem restar SSE (`AulaChat`) e casos justificados.
- Deploy: `git push && ./build.sh`; smoke: frontend 1/1, `/login` 200.
- Memória: marcar Fase 2 ✅.

---

## Self-Review
Cobertura: q/cadernos, q/questao, q/filtrar, concorrencia, q/caderno (núcleo), annotations. Restará só SSE. Risco concentrado em Task D — mitigado por migração conservadora (sem optimistic) + review dedicado + flag de smoke humano. Optimistic updates e prefetch ficam p/ Fase 3.
