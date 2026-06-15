# React Query v5 — Fase 3 (polish: optimistic + prefetch) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Convenções da Fase 0-2 (deployadas) valem.

**Goal:** Devolver a snappiness perdida na migração conservadora: **optimistic update no favoritar** (estrela instantânea) e **prefetch on-hover** das listas → telas de detalhe (navegação instantânea). Escopo de polimento, baixo risco.

**Convenções:** RQ por cima de `apiJson/apiPost`; `qk` central; não refatorar as telas de detalhe (recém-validadas) — prefetch fica isolado nos componentes de lista. Verificação via container helper `studia-fe-check` (`docker exec studia-fe-check sh -lc 'cd /app && npx tsc --noEmit'` e `pnpm -s lint`); NUNCA `pnpm build`/`pnpm dev` em container ativo.

---

### Task 1 — Optimistic favoritar (`q/caderno/[id]`)

**File:** `fontend/app/q/caderno/[id]/page.tsx`

A `favoritarMutation` hoje só invalida `qk.favoritas()` (toggle visível só após round-trip). Tornar optimistic com rollback:

```ts
const favoritarMutation = useMutation({
  mutationFn: (qid: number) => apiPost(`/api/q/${qid}/favoritar`),
  onMutate: async (qid) => {
    await queryClient.cancelQueries({ queryKey: qk.favoritas() });
    const prev = queryClient.getQueryData(qk.favoritas());
    queryClient.setQueryData(qk.favoritas(), (old) => /* toggla qid no shape real de favoritas */);
    return { prev };
  },
  onError: (_e, _qid, ctx) => {
    if (ctx?.prev !== undefined) queryClient.setQueryData(qk.favoritas(), ctx.prev);
  },
  onSettled: () => queryClient.invalidateQueries({ queryKey: qk.favoritas() }),
});
```
- LER o shape real retornado por `GET /api/q/favoritas` (como `favData`/`favIds` é derivado na página) e togglar o `qid` nesse shape dentro do `setQueryData` (adicionar se ausente, remover se presente).
- Preservar todo o resto. A estrela (derivada de `favIds`) passa a alternar instantaneamente; em erro, reverte.

Gate: `tsc` limpo + `lint` 0 erros. Commit: `feat(rq): optimistic update no favoritar (estrela instantânea + rollback)`.

---

### Task 2 — Prefetch on-hover (listas → detalhe)

Adicionar `onMouseEnter`/`onFocus` nos cards/links que navegam pra telas de detalhe, disparando `queryClient.prefetchQuery` com a MESMA `qk` e o MESMO endpoint que a tela de destino usa (sem refatorar o destino). `const queryClient = useQueryClient();`

Padrão por item:
```tsx
onMouseEnter={() => queryClient.prefetchQuery({
  queryKey: qk.X(id),
  queryFn: () => apiJson(`/api/...${id}`),
  staleTime: 30_000,
})}
```

**Alvos:**
- `fontend/app/q/cadernos/page.tsx` — card/link de caderno (→ `/q/caderno/{id}`): prefetch `qk.caderno(id)` ← `GET /api/q/cadernos/{id}`.
- `fontend/app/disciplinas/page.tsx` — card de disciplina (→ `/disciplinas/{slug}`): prefetch `qk.disciplina(slug)` ← `GET /api/disciplinas/{slug}`.
- `fontend/app/flashcards/page.tsx` — card de deck (→ `/flashcards/{id}`): prefetch `qk.deckCards(id)` ← `GET /api/flashcards/{id}`.

LER cada tela de destino p/ confirmar a `qk` e o path exatos (devem casar com o `useQuery` de lá, senão o prefetch não é aproveitado). Não duplicar lógica além do necessário; o prefetch fica só no componente de lista.

Gate: `tsc` limpo + `lint` 0 erros. Commit: `feat(rq): prefetch on-hover de cadernos/disciplinas/decks (navegação instantânea)`.

---

### Task 3 — Build + deploy + smoke

- Build de imagem via `./build.sh` (gate autoritativo) — NÃO rodar `pnpm build` em container ativo.
- Deploy + smoke: frontend 1/1, `/login` 200.
- Memória: RQ Fase 3 ✅.

---

## Self-Review
Cobertura: optimistic favoritar (snappiness do quiz) + prefetch nas 3 listas navegacionais principais. Baixo risco: prefetch é aditivo (só popula cache antes), optimistic tem rollback em erro. Telas de detalhe não são tocadas. Restará Fase 4 (SSR/hydration) — opcional. Smoke humano do favoritar (alternar estrela rápido) é recomendável mas o rollback protege contra erro.
