# Celebração de meta diária (15 questões / PRO)

**Data:** 2026-06-27
**Status:** Aprovado (design)

## Objetivo

Quando um usuário **PRO** (ilimitado) resolve **15 questões no dia**, disparar
uma celebração: **confetes** + **toast de parabéns** ("meta diária batida").

Reaproveita a ideia do confete que já existe ao assinar o PRO
(`celebrarPro()` em `fontend/lib/confetti.ts`, lib `canvas-confetti`).

## Decisões de design

1. **Público:** a meta de 15 é **exclusiva do PRO**. O plano grátis trava em
   10 questões/dia (`LIMITE_DIARIO_GRATIS = 10`), logo nunca alcança 15 e nunca
   dispara. Coerente com a regra de negócio atual; nenhuma mudança no paywall.
2. **Fonte da verdade = backend.** A detecção do marco fica no servidor, que já
   conta questões distintas do dia com fuso correto (`America/Fortaleza`) e
   idempotência. O frontend apenas *reage* a um flag — evita falso disparo ao
   recarregar a página ou re-responder a mesma questão.
3. **Toast:** instalar **`sonner`** (padrão do ecossistema shadcn/ui, que é a
   stack-alvo do projeto). Reutilizável para futuros avisos do app.
4. **Confete distinto** do confete de assinatura, para não confundir "assinou
   PRO" com "bateu meta". Mantém a paleta cyan `#06b6d4` / violeta `#8b5cf6`.

## Backend — `POST /api/q/{id}/responder`

Arquivo: `backend/q_router.py` (rota em ~1243-1326), `backend/entitlements.py`.

1. Nova constante em `entitlements.py`: `META_DIARIA_PRO = 15`.
2. Helper em `entitlements.py` para encapsular a regra do marco, ex.:
   `meta_diaria_status(db, user, *, era_nova: bool) -> dict`, que devolve
   `{"meta": 15, "total": <n>, "batida_agora": <bool>}`.
   - `total = contagem_questoes_hoje(db, user.id)` (questões DISTINTAS de hoje).
   - `batida_agora = True` **somente quando**: usuário é **ilimitado**
     (admin **ou** `acesso_pro_ativo`) **E** `era_nova` (esta resposta criou uma
     `Resolucao` nova, não o caminho idempotente de questão já respondida) **E**
     `total == META_DIARIA_PRO` (exato). Dispara uma única vez na transição
     14→15.
3. No endpoint:
   - No caminho idempotente (questão já respondida hoje): `era_nova=False` →
     `batida_agora` sempre `false`.
   - No caminho de resolução nova: após o commit da `Resolucao`, calcular o
     status com `era_nova=True` e incluir no JSON de resposta:
     ```json
     "meta_diaria": { "meta": 15, "total": 15, "batida_agora": true }
     ```

> Observação: `contagem_questoes_hoje` usa `COUNT(DISTINCT questao_id)`, então
> repetições e questões entre cadernos diferentes não inflam o contador.

## Frontend

1. **Dependência:** instalar `sonner` no `fontend`.
2. **Layout raiz** (`fontend/app/layout.tsx`): adicionar
   `<Toaster richColors position="top-center" />`.
3. **Confete** (`fontend/lib/confetti.ts`): extrair o núcleo de disparo
   compartilhado e adicionar `celebrarMetaDiaria()` — uma "chuva" de confetes
   mais festiva que `celebrarPro()`, mantendo as cores do tema. SSR-safe
   (guard `typeof window`), como a função existente.
4. **Gancho de disparo** — `fontend/app/q/caderno/[id]/page.tsx`, no
   `responderMutation.onSuccess` (~223-268): se `data.meta_diaria?.batida_agora`,
   chamar `celebrarMetaDiaria()` e
   `toast.success("🎯 Meta diária batida!", { description: "Você resolveu 15 questões hoje. Continue assim! 🔥" })`.

Único ponto de resposta de questão no app é `q/caderno/[id]/page.tsx`
(`CommentItem.tsx` é "responder comentário" do fórum, não conta), então o
gancho único cobre todos os fluxos.

## Fora de escopo (YAGNI)

- Contador visual "12/15 hoje" para o PRO (não pedido; o contador atual é só do
  grátis). Backend já devolve `total`, então é trivial adicionar depois.
- Celebrações em múltiplos marcos (30, 45…). Apenas a meta diária única (15).

## Testes

Backend (`backend/tests/`, pytest + aiosqlite):

- PRO resolve a 15ª questão distinta → `meta_diaria.batida_agora == true`.
- PRO na 14ª e na 16ª → `false`.
- PRO re-responde a 15ª questão (idempotente) → `false`.
- Grátis nunca dispara (`batida_agora == false`), mesmo no limite.
