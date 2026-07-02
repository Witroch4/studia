# Design — Perfil completo de usuário (/conta expandida + /u/[apelido])

**Data:** 2026-07-02
**Status:** aprovado pelo usuário (brainstorming concluído)

## Objetivo

Expandir a rota `/conta` do studIA para um perfil completo estilo TC: apelido único
usado no fórum, upload de foto, opções de visibilidade, resumo estatístico (metas
batidas, combos X2/X3/X4), pontuação do fórum e uma pontuação final consolidada —
com perfil público clicável em `/u/[apelido]`.

## Decisões tomadas

1. **Apelido substitui o nome no fórum** e o perfil é público clicável em
   `/u/[apelido]` (estilo TC completo). Quem não definiu apelido continua exibindo
   o nome real, sem link.
2. **Pontuação final** = pontos do fórum + pontos de estudo:
   - Fórum = soma dos `score` dos comentários do usuário (votos recebidos + curtidas).
   - Estudo = metas batidas ×10 + combos X2 ×20 + X3 ×30 + X4 ×40.
   - UI mostra a fórmula em tooltip.
3. **Visibilidade — 3 toggles:** perfil público on/off, mostrar estatísticas de
   estudo on/off, mostrar foto on/off. Pontuação do fórum sempre visível quando o
   perfil é público.
4. **Foto:** upload simples (png/jpg/webp até 5 MB), backend faz crop central
   quadrado + resize 256×256 via Pillow, salva como webp no MinIO. Sem editor de
   crop no frontend.
5. **Armazenamento: tabela nova no backend FastAPI** (Abordagem 1) — Alembic,
   unicidade garantida pelo banco, join direto com o fórum. Better Auth continua
   dono apenas de nome/email/senha.
6. **Apelido pode ser trocado a qualquer momento**; links antigos `/u/apelido-velho`
   passam a dar 404 (aceito).
7. **Nada de pontuação persistida** — tudo derivado on-the-fly (ver §2).

## 1. Dados (nova tabela, Alembic)

Tabela `perfis_usuario`:

| Campo | Tipo | Notas |
|---|---|---|
| `id` | Integer PK | |
| `owner_uid` | String(64) unique, not null, indexed | Better Auth `user.id` |
| `apelido` | String(32) unique, nullable | lowercase, regex `^[a-z0-9][a-z0-9-]{2,31}$`; nulo até o usuário definir |
| `avatar_key` | String nullable | objeto MinIO `avatars/{uuid}.webp` (uuid aleatório por upload — não usa o uid, que nunca pode vazar em URL; re-upload gera chave nova = cache-busting) |
| `perfil_publico` | Boolean, default true | off → `/u/[apelido]` responde "perfil privado" e o fórum não linka |
| `mostrar_estatisticas` | Boolean, default true | |
| `mostrar_foto` | Boolean, default true | |
| `created_at` / `updated_at` | DateTime | |

A linha é criada lazy (upsert) no primeiro PATCH/upload do usuário; ausência de
linha = todos os defaults.

## 2. Derivação de pontuação (sem persistência nova)

Módulo próprio `backend/perfil_service.py` (testável isolado):

- **Fórum**: `SUM(QuestaoComentario.score)` com `owner_uid = uid`,
  `origem = 'studia'`, `deleted_at IS NULL`. Também expõe contagem de comentários.
- **Metas/combos históricos**: `resolucoes` agrupada por dia com corte de
  meia-noite **America/Fortaleza** (mesma regra de `entitlements.py`), contando
  **questões distintas** por dia:
  - dia com ≥15 → 1 meta batida;
  - ≥25 → 1 combo X2; ≥35 → 1 combo X3; ≥45 → 1 combo X4
  - (um dia com 45 conta meta + X2 + X3 + X4, igual ao comportamento ao vivo de
  `COMBOS_META_DIARIA = {25: 2, 35: 3, 45: 4}`).
  - Contas grátis são limitadas a 10/dia, então a derivação é naturalmente
    consistente com a regra "meta/combo só para conta ilimitada".
- **Pontuação final** = fórum + metas×10 + X2×20 + X3×30 + X4×40.
- Resumo de estudo reaproveita as queries do dashboard: resolvidas, acertos,
  taxa, streak (`_compute_streak`).

## 3. Backend — endpoints novos (prefixo `/api/q/perfil`)

| Endpoint | Auth | Descrição |
|---|---|---|
| `GET /perfil` | require_user | meu perfil (campos + toggles) + resumo completo (pontuação com breakdown, metas, combos, resolvidas, taxa, streak) |
| `PATCH /perfil` | require_user | apelido e toggles; **409** apelido em uso, **422** formato inválido |
| `POST /perfil/avatar` | require_user | multipart png/jpg/webp ≤5 MB → Pillow crop central + 256×256 → webp → MinIO `avatars/{uuid}.webp`; remove o objeto antigo |
| `DELETE /perfil/avatar` | require_user | remove objeto e limpa `avatar_key` |
| `GET /perfil/avatar/{key}` | público | serve a imagem em stream (mesmo padrão de `GET /forum/imagem/{key}`, path validado por regex `^avatars/[uuid]\.webp$`) — a chave é aleatória, não revela o dono |
| `GET /perfil/u/{apelido}` | público | perfil público (ver regras abaixo) |

Regras do endpoint público `GET /perfil/u/{apelido}`:
- Apelido inexistente → **404** simples.
- `perfil_publico = false` → **404** com corpo `{"privado": true}`.
- Sempre (quando público): apelido, "membro desde" (`user.createdAt`), badge de
  role (professor/admin), pontuação final + breakdown do fórum, nº de comentários.
- Avatar só se `mostrar_foto`; estatísticas de estudo (resolvidas, taxa, streak,
  metas, combos) só se `mostrar_estatisticas`.
- **Nunca** expõe `owner_uid`, e-mail ou nome real.

**Dependência nova**: `Pillow` em `backend/requirements.txt`.

## 4. Fórum — apelido e link

- `_display_name` (q_router.py): persona (admin) > pseudônimo TC > **apelido** >
  `autor_nome` real.
- `_serializar_comentario` ganha:
  - `autor_apelido` — só quando `origem = 'studia'` + apelido definido + perfil público;
  - `autor_avatar_url` — idem, e só se `mostrar_foto`.
- Carregamento em lote: uma query de perfis por conjunto de `owner_uid` da página
  de comentários (sem N+1).
- Frontend do fórum: nome do autor vira link para `/u/[apelido]` quando
  `autor_apelido` presente; avatar real no lugar da inicial quando
  `autor_avatar_url` presente.
- `owner_uid` continua nunca exposto ao cliente.

## 5. Frontend — `/conta` expandida

Mantém `BillingSection`, Segurança (senha) e `CreateUserCard` (admin). Muda/adiciona:

- **Header**: foto real (ou iniciais como hoje) + apelido abaixo do nome.
- **Card Perfil**: nome (Better Auth via `authClient.updateUser`, como hoje) +
  campo **apelido** (salva via `PATCH /api/q/perfil`, mostra erro de conflito) +
  **upload de foto** com preview e botão remover.
- **Card Visibilidade** (novo): os 3 toggles, salvamento via `PATCH /perfil`.
- **Card Resumo estatístico** (novo): pontuação final em destaque com tooltip da
  fórmula; breakdown (pontos do fórum, metas batidas, combos X2/X3/X4);
  resolvidas/taxa/streak; link "ver painel completo" → `/painel`.
- **React Query v5 obrigatório** + `<Skeleton>` reservando o espaço final
  (regra rígida de UI — nada de layout pulando). Mutations invalidam a query do
  perfil.

## 6. Rota pública `/u/[apelido]`

Página client-side (React Query + Skeleton no formato final):
- Avatar/iniciais, apelido, "membro desde", badge professor/admin.
- Pontuação final em destaque + breakdown do fórum.
- Estatísticas de estudo quando permitidas.
- Estados: **perfil privado** (mensagem própria) e **404** apelido inexistente.

## 7. Tratamento de erros

- Apelido: 409 (em uso), 422 (formato). Normalização para lowercase antes de validar.
- Avatar: 415 tipo inválido, 413 acima de 5 MB, erro Pillow → 422 "imagem inválida".
- Race de unicidade: constraint do banco é a fonte de verdade; IntegrityError → 409.

## 8. Testes (pytest, `backend/tests/`)

- CRUD do perfil: criação lazy, PATCH de apelido/toggles, unicidade (409) e
  formato (422).
- `perfil_service`: derivação de pontuação com `resolucoes` semeadas (dias com
  14/15/25/35/45 questões distintas; repetições da mesma questão no dia não
  inflam a contagem) e comentários com scores.
- Endpoint público: respeita os 3 toggles; nunca vaza `owner_uid`/e-mail/nome.
- Upload: validação de tipo/tamanho; serve avatar com path validado.
- Fórum: serializer expõe `autor_apelido`/`autor_avatar_url` nas condições certas.

## 9. Deploy

Fluxo padrão do projeto: worktree → commits → merge na `main` → `git push` →
`./build.sh` → `git worktree remove`. A migração Alembic roda sozinha no startup
(`scripts.db_prepare`).

## Fora de escopo (YAGNI)

- Reputação com histórico/gráfico temporal; badges/conquistas além dos combos.
- Aprovações ("Informar nova aprovação" do TC), bloqueio/silenciamento de usuários.
- Editor de crop no frontend; múltiplos tamanhos de avatar.
- Redirect de apelidos antigos.
