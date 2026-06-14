# React Query v5 — Fase 0 (Fundação) + Fase 1 (Alto valor) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Adotar TanStack Query v5 no frontend studIA: fundação (provider + conventions) e migrar as superfícies de alto valor (polling manual → `refetchInterval`; listas quentes → `useQuery`; mutações núcleo → `useMutation` + invalidação), com **skeleton só no load inicial**.

**Architecture:** O React Query entra **por cima** de `lib/api.ts` (que já faz CSRF + handoff JWT 401→retry): `queryFn: () => apiJson(...)`. Páginas são client/autenticadas → foco em cache, dedup e `refetchInterval`. Roadmap completo (Fases 2-4) em `docs/superpowers/plans/2026-06-14-react-query-roadmap.md`.

**Tech Stack:** Next 16.1.6 (App Router), React 19.2.3, `@tanstack/react-query` v5 (+ devtools). Lint: `docker exec studia-frontend-dev sh -lc 'cd /app && pnpm lint'`. Typecheck: `... npx tsc --noEmit`.

---

## Convenções (OBRIGATÓRIAS em toda migração)

1. **Transporte:** nunca trocar `apiJson/apiFetch/apiPost`. `queryFn: () => apiJson<T>(path)`; `mutationFn` chama `apiPost`/`apiJson` com método.
2. **Skeleton só no load inicial:** renderizar skeleton **apenas** quando `isPending` (primeira carga, sem dado em cache). Em refetch/poll com `data` presente, **manter a tela** (sem skeleton). Mutação → estado inline (botão `disabled`/spinner), nunca skeleton.
3. **Polling:** `refetchInterval: (query) => <condição> ? <ms> : false` — parar quando o trabalho terminou (status final). Sem `setInterval` manual.
4. **Filtros/paginação:** `placeholderData: keepPreviousData` (mantém dado anterior visível ao trocar filtro).
5. **Mutações:** `useMutation({ mutationFn, onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.X() }) })`.
6. **Chaves:** sempre via `qk` de `lib/queryKeys.ts`.
7. **SSE fica fora:** `AulaChat` e chat com streaming permanecem `fetch` streaming.

---

### Task 1: Fundação (provider + client + keys + skeleton)

**Files:**
- Modify: `fontend/package.json` (deps)
- Create: `fontend/lib/query.ts`, `fontend/lib/queryKeys.ts`, `fontend/app/components/QueryProvider.tsx`, `fontend/app/components/Skeleton.tsx`
- Modify: `fontend/app/layout.tsx`

- [ ] **Step 1: Instalar deps**

```bash
docker exec studia-frontend-dev sh -lc 'cd /app && pnpm add @tanstack/react-query@^5 && pnpm add -D @tanstack/react-query-devtools@^5'
```
Conferir que `package.json` ganhou `@tanstack/react-query` e o devtools.

- [ ] **Step 2: `fontend/lib/query.ts`**

```ts
import { QueryClient } from "@tanstack/react-query";

/** Factory do QueryClient. Defaults conservadores p/ app single-user. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000, // 30s "fresco" — evita refetch redundante ao navegar
        gcTime: 5 * 60_000, // 5min em cache após inativo
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}
```

- [ ] **Step 3: `fontend/lib/queryKeys.ts`**

```ts
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
```

- [ ] **Step 4: `fontend/app/components/QueryProvider.tsx`**

```tsx
"use client";

import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { makeQueryClient } from "@/lib/query";

export default function QueryProvider({ children }: { children: React.ReactNode }) {
  // Instância estável por árvore de render (não recria a cada render).
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      {children}
      {process.env.NODE_ENV === "development" && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
```

- [ ] **Step 5: `fontend/app/components/Skeleton.tsx`** (idioma já usado no app: `animate-pulse bg-surface-2`)

```tsx
/** Bloco de carregamento. Usar SÓ no load inicial (isPending), nunca em refetch/mutation. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-surface-2 rounded ${className}`} />;
}
```

- [ ] **Step 6: Aninhar o provider em `layout.tsx`**

Trocar:
```tsx
        <ThemeProvider>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
```
por:
```tsx
        <ThemeProvider>
          <QueryProvider>
            <AppShell>{children}</AppShell>
          </QueryProvider>
        </ThemeProvider>
```
E adicionar o import no topo: `import QueryProvider from "./components/QueryProvider";`

- [ ] **Step 7: Lint + typecheck + boot**

```bash
docker exec studia-frontend-dev sh -lc 'cd /app && pnpm lint && npx tsc --noEmit'
sleep 3 && curl -fsS http://localhost:3000/ -o /dev/null && echo " front OK"
```
Expected: lint sem novos erros; `tsc` limpo; front responde.

- [ ] **Step 8: Commit**

```bash
git add fontend/package.json fontend/pnpm-lock.yaml fontend/lib/query.ts fontend/lib/queryKeys.ts fontend/app/components/QueryProvider.tsx fontend/app/components/Skeleton.tsx fontend/app/layout.tsx
git commit -m "feat(rq): fundação TanStack Query v5 (provider, queryClient, queryKeys, Skeleton)"
```

---

### Exemplar de migração (PADRÃO a seguir nas Tasks 3-5)

Antes (`disciplinas/[slug]/aulas/[id]/page.tsx`):
```tsx
const [data, setData] = useState<AulaDetail | null>(null);
const [loading, setLoading] = useState(true);
useEffect(() => {
  apiFetch(`/api/aulas/${aulaId}`).then((r) => r.json()).then(setData).catch(console.error).finally(() => setLoading(false));
}, [aulaId]);
if (loading) { /* skeleton */ }
if (!data) { /* não encontrada */ }
```
Depois (skeleton só no load inicial; polling para em status final):
```tsx
import { useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

const { data, isPending } = useQuery({
  queryKey: qk.aula(aulaId),
  queryFn: () => apiJson<AulaDetail>(`/api/aulas/${aulaId}`),
  refetchInterval: (query) => {
    const s = query.state.data?.status;
    return s && s !== "CONCLUIDO" && s !== "ERRO" ? 4000 : false;
  },
});
if (isPending) { /* MESMO markup de skeleton de antes */ }
if (!data) { /* não encontrada */ }
```
Remover `useState`/`useEffect`/`loading` e o import `apiFetch` se ficar sem uso (manter `apiUrl` se ainda usado). Toda a UI restante (tabs, chat) permanece igual.

---

### Task 2: Listas quentes + mutações núcleo (disciplinas/flashcards/painel/billing)

**Files (migrar seguindo o exemplar; skeleton só em `isPending`):**
- `fontend/app/disciplinas/page.tsx` — read `GET /api/disciplinas` → `useQuery(qk.disciplinas())`; mutação criar disciplina (`POST /api/disciplinas`) → `useMutation` + invalidate `qk.disciplinas()`.
- `fontend/app/flashcards/page.tsx` — read `GET /api/decks` → `useQuery(qk.decks())`; mutação excluir deck (`DELETE /api/decks/{id}`) → invalidate `qk.decks()`.
- `fontend/app/flashcards/novo/page.tsx` — mutações `POST /api/flashcards` e `POST /api/flashcards/import` → `useMutation` + invalidate `qk.decks()` (mantém navegação/feedback atuais).
- `fontend/app/painel/PainelClient.tsx` — read `GET /api/q/dashboard` → `useQuery(qk.dashboard())`.
- `fontend/app/components/UserNav.tsx` — read `GET /api/billing/status` → `useQuery(qk.billing(), { enabled: !!session?.user })`. Manter o `logout` como está (apiFetch).

- [ ] **Step 1:** migrar os 5 arquivos acima conforme convenções (skeleton só `isPending`; manter todo markup/estado de UI).
- [ ] **Step 2:** `docker exec studia-frontend-dev sh -lc 'cd /app && pnpm lint && npx tsc --noEmit'` → limpo.
- [ ] **Step 3:** Commit `feat(rq): migra disciplinas, flashcards, painel e billing p/ useQuery/useMutation`.

---

### Task 3: Polling de processamento de aula

**Files:**
- `fontend/app/disciplinas/[slug]/aulas/[id]/page.tsx` — exemplar acima (read `GET /api/aulas/{id}`, `refetchInterval` para em `CONCLUIDO`/`ERRO`).
- `fontend/app/disciplinas/[slug]/page.tsx` — reads `GET /api/disciplinas/{slug}` + `GET /api/disciplinas/{slug}/aulas` → `useQuery` (chaves `qk.disciplina(slug)` e `[...qk.disciplina(slug), "aulas"]`); `refetchInterval` na lista de aulas enquanto houver aula com status PENDENTE/PROCESSANDO; mutação upload (`POST /api/disciplinas/{slug}/aulas`) → invalidate as duas chaves. Remover o `setInterval` manual.
- `fontend/app/flashcards/[id]/page.tsx` — read `GET /api/flashcards/{id}` → `useQuery`; `refetchInterval` enquanto aula em processamento (mesma regra). Remover `setInterval`.

- [ ] **Step 1:** migrar os 3 arquivos (skeleton só `isPending`; refetch/poll mantém a tela; zero `setInterval`).
- [ ] **Step 2:** lint + tsc limpos.
- [ ] **Step 3:** Commit `feat(rq): polling de processamento de aula via refetchInterval (sem setInterval)`.

---

### Task 4: Polling de jobs/coleta/guias (reads)

**Files (migrar a LEITURA + polling; mutações de coleta avançadas ficam p/ Fase 2 — manter como apiFetch por ora, sem quebrar):**
- `fontend/app/jobs/page.tsx` — reads `GET /api/jobs`, `GET /api/batch-jobs` → `useQuery` (`qk.jobs()`, `qk.batchJobs()`) com `refetchInterval` (ex. 5s) enquanto houver job ativo; manter o `cancel` (`POST .../cancel`) como mutação simples + invalidate `qk.batchJobs()`. Remover `setInterval`.
- `fontend/app/q/coletar/page.tsx` — read `GET /api/q/coletar/jobs` → `useQuery(qk.coletarJobs(), { refetchInterval })` enquanto houver job Running/pending; demais reads (`/api/q/coletar`) → `useQuery`. Mutações (materializar/recoletar/jobs ação) podem permanecer apiFetch nesta fase, mas após sucesso chamar `queryClient.invalidateQueries({ queryKey: qk.coletarJobs() })`. Remover `setInterval`.
- `fontend/app/q/coletar/GuiasPanel.tsx` — read `GET /api/q/guias` → `useQuery(qk.guias())` com `refetchInterval` enquanto materialização em curso. Remover `setInterval`.
- `fontend/app/q/guias/page.tsx` — read `GET /api/q/guias` → `useQuery(qk.guias(), { refetchInterval })`. Remover `setInterval`.
- `fontend/app/q/guias/[id]/page.tsx` — read `GET /api/q/guias/{id}` → `useQuery(qk.guia(id), { refetchInterval })` enquanto coleta/materialização ativa. Mutações ficam apiFetch nesta fase, com invalidate `qk.guia(id)` após sucesso. Remover `setInterval`.
- `fontend/app/assinar/page.tsx` — read billing/status → `useQuery(qk.billing(), { refetchInterval: (q) => q.state.data?.plano === "pro" ? false : 4000 })` (parar quando virar pro). Remover `setInterval`.

- [ ] **Step 1:** migrar os 6 arquivos (skeleton só `isPending`; zero `setInterval`; invalidate após mutações que permanecerem).
- [ ] **Step 2:** lint + tsc limpos.
- [ ] **Step 3:** Commit `feat(rq): polling de jobs/coleta/guias/assinar via refetchInterval`.

---

### Task 5: Verificação consolidada + build

- [ ] **Step 1: Auditar `setInterval` de fetch removidos nas telas da Fase 1**

```bash
cd /home/wital/studia/fontend && grep -rlnE "setInterval" app/jobs app/q/coletar app/q/guias app/assinar app/disciplinas/'[slug]' app/flashcards/'[id]' 2>/dev/null || echo "sem setInterval nas telas migradas"
```
Expected: nenhum `setInterval` nas telas migradas (exceto usos não-fetch legítimos, se houver — justificar).

- [ ] **Step 2: Build completo (typecheck + compile)**

```bash
docker exec studia-frontend-dev sh -lc 'cd /app && pnpm build' 2>&1 | tail -25
```
Expected: build sucesso (sem erros de tipo).

- [ ] **Step 3:** Se algo falhar, corrigir e repetir. Commit de ajustes se necessário.

---

### Task 6: Deploy + smoke (controlador)

- [ ] **Step 1:** `cd /home/wital/studia && git push && ./build.sh` (autorizado em automode).
- [ ] **Step 2: Smoke prod:**
```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 'docker service ls | grep -E "studia_frontend|studia_backend"; curl -fsS https://studia.witdev.com.br/ -o /dev/null && echo " front 200"'
```
Expected: frontend 1/1, front 200. Rollback: `docker service rollback studia_frontend`.
- [ ] **Step 3:** Worktree limpo; atualizar memória (`studia-padronizacao.md`: React Query Fase 0+1 ✅; padrão skeleton-só-no-load).

---

## Self-Review

**Spec coverage:** Fundação (Task 1); polling→refetchInterval (Tasks 3-4); listas quentes (Task 2); mutações núcleo + invalidação (Tasks 2-4); skeleton-só-no-load (convenção §2, aplicada em todas). Fases 2-4 ficam na roadmap.

**Placeholders:** foundation com código completo; exemplar com before/after literal; migrações por-tela com endpoint→queryKey→regra de polling→invalidação explícitos. Subagentes leem cada arquivo-fonte e aplicam o exemplar.

**Riscos:** componentes stateful (estado de UI misturado com fetch) — mitigado por: manter todo markup/estado de UI, só trocar a camada de dados; gate `pnpm lint` + `npx tsc --noEmit` por task + `pnpm build` no fim; sem teste de browser (assumido — typecheck é o gate). Padrão misto temporário (mutações de coleta avançadas só na Fase 2) é intencional e documentado.
