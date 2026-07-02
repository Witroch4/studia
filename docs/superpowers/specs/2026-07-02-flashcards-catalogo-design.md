# Flashcards multi-usuário + catálogo público — Design

Data: 2026-07-02 · Status: aprovado pelo usuário

## Objetivo

Transformar o sistema de flashcards (legado single-user, sem auth) em
multi-usuário: cada usuário tem decks privados; existe um **catálogo público
read-only** (mesmo padrão do Catálogo de Concorrências, `Concurso.user_id` +
`is_public`); o admin vê tudo e **promove** decks de usuários ao catálogo,
salvo quando o dono marcou "Impedir promoção"; qualquer usuário pode **copiar**
um deck público para o próprio acervo; a página de criação ganha um
**mini-guia** (accordion, padrão `ConcursoGuiaCsv`) do formato `.md`.

## Decisões do usuário

- Promoção = **flag no lugar** (deck continua do dono, edições refletem no
  catálogo). Não é cópia/snapshot.
- Decks legados (72 cards em prod, importados pelo admin) → `is_public=true`,
  `user_id=NULL` (dono efetivo: sistema/admin). Viram o catálogo inicial.
- Catálogo permite **"Copiar pro meu acervo"** (clona deck + cards para o
  usuário), além de estudar read-only.

## Modelo de dados (migração Alembic `decks_dono_catalogo`)

`decks` ganha:

| coluna              | tipo         | default | semântica |
|---------------------|--------------|---------|-----------|
| `user_id`           | String(64) NULL, index | NULL | dono (Better Auth user.id); NULL = legado/sistema |
| `is_public`         | Boolean NOT NULL | false | no catálogo público |
| `permitir_promocao` | Boolean NOT NULL | true  | false = dono impediu promoção |

- Backfill: `UPDATE decks SET is_public = true` (legado vira catálogo).
- `slug` deixa de ser UNIQUE global → `UniqueConstraint(user_id, slug)`
  (+ index simples em slug). Dois usuários podem ter "engenharia-civil".
- **Rotas passam a usar `deck.id` numérico** (slug vira só display); o
  frontend `/flashcards/[id]` recebe o id.

## Permissões / endpoints (todos `require_user`; fecha o buraco de import sem auth)

- `GET /api/decks` → `{ meus: [...], catalogo: [...] }`; p/ admin também
  `usuarios: [{dono: {id, nome, email}, decks: [...]}]` (join tabela `"user"`).
  Cada deck: `id, slug, nome, icon, icon_color, total, publico,
  permitir_promocao, dono_sou_eu`.
- `GET /api/flashcards/deck/{deck_id}` → dono, público ou admin.
- `POST /api/flashcards` e `POST /api/flashcards/import` → decks do próprio
  usuário (match por `(user_id, slug)`); form aceita `impedir_promocao: bool`
  aplicado a decks **novos** criados na operação. Import mantém dedup
  (deck+frente+verso) e resposta `imported/skipped`.
- `POST /api/decks/{id}/promover` (admin; 409 se `permitir_promocao=false`) e
  `POST /api/decks/{id}/despromover` (admin).
- `POST /api/decks/{id}/copiar` → deck visível (público ou próprio) é clonado
  p/ o usuário (novo deck `user_id=eu`, `is_public=false`, cards copiados);
  slug já existente no acervo → sufixo `-2`, `-3`…
- `PATCH /api/decks/{id}` `{impedir_promocao}` → só o dono (admin não muda a
  vontade do dono). Impedir com deck já público **despromove** junto.
- `DELETE /api/decks/{id}` → dono ou admin.
- `GET /api/flashcards/todos` → só os cards do usuário (revisão geral).

## Frontend

- **/flashcards**: seção "Meus decks" (grid atual) + seção "Catálogo público"
  (badge 🌐, estudo read-only, botão "Copiar pro meu acervo"); admin vê também
  "Decks dos usuários" agrupado por dono com Promover/Remover do catálogo
  (botão desabilitado + tooltip quando o dono impediu). React Query,
  `<Skeleton>` reservando espaço (regra rígida de UI), nada de flash (0).
- **/flashcards/novo**: checkbox "Impedir promoção ao catálogo público"
  (desmarcado por padrão) no form e no import; mini-guia accordion
  "Como criar seus flashcards" no padrão visual de `ConcursoGuiaCsv`:
  formato do `.md`, tags XML, LaTeX, exemplo copiável, tolerâncias
  (labels em negrito, `(Tema:)`, CRLF).
- **/flashcards/[id]** (estudo): deck público e não-meu → esconde ações de
  escrita. Sem estado SRS compartilhado (SRS não persiste revisões hoje).

## Erros / bordas

- Promover deck com `permitir_promocao=false` → 409 com mensagem clara.
- Copiar deck não-visível → 403; deck inexistente → 404.
- Usuário sem decks e catálogo vazio → estados vazios distintos por seção
  (gated em `!isPending`).
- Decks legados (`user_id NULL`): aparecem no catálogo; admin os administra
  como donos de fato (aparecem na seção admin como "Sistema").

## Testes

- pytest: escopo por dono (A não vê privado de B), catálogo visível a todos,
  promover/despromover (admin only, respeita `permitir_promocao`), copiar
  (clone + sufixo de slug + 403), import escopado + `impedir_promocao`,
  PATCH dono-only, DELETE dono/admin, drift Alembic verde.

## Alternativas descartadas

- Catálogo como cópia/snapshot (usuário escolheu flag in-place).
- Visibilidade por card (deck é a unidade, como Concurso).
- Manter slug único global (impede decks homônimos entre usuários).
