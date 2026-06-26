# Fórum dos Professores + Sistema de Roles — Design

**Data:** 2026-06-26
**Status:** Aprovado (aguardando review do spec)
**Depende de:** fórum dos alunos (`2026-06-25-forum-questoes-design.md`, já em produção)

## Objetivo

Criar um segundo quadro de comentários por questão — o **fórum dos professores** —
onde **apenas usuários com role `professor` ou `admin` podem escrever**. Alunos
leem e votam, mas não postam. Quando o **admin** (dono) escreve, o sistema atribui
automaticamente uma **persona de cientista famoso** (Einstein, Newton, Bohr…),
dando a sensação de vários professores renomados respondendo.

Junto vem o **sistema de roles** (`aluno`=user · `professor` · `admin`) e a
ferramenta de admin para promover aluno→professor.

## Princípio central

O fórum dos professores **é** o fórum dos alunos com três diferenças:
1. Gate de escrita: `role ∈ {professor, admin}`.
2. Persona de cientista nos posts do admin.
3. Badge visual 🎓 "Professor".

Por isso **reutilizamos a mesma tabela, os mesmos endpoints (parametrizados) e os
mesmos componentes React**. Não duplicamos estrutura (rejeitado: tabela
`professor_comentarios` paralela — duplicaria modelo, votos, serialização e 3
componentes sem ganho).

---

## 1. Sistema de roles

### Estado atual
- `role` vive na coluna `"user".role` do Better Auth (VARCHAR livre, default `"user"`).
- Entra no JWT no handoff (`POST /api/session/handoff` lê a coluna e minta o JWT).
- `auth.py` lê `claims.get("role", "user")` sem hit no banco. Só existe `is_admin` (`role == "admin"`).
- Plugin Better Auth: `admin({ defaultRole: "user", adminRoles: ["admin"] })`.

### Mudanças
- `auth.py` — `CurrentUser`:
  - nova property `is_professor` → `self.role in ("professor", "admin")` (admin é superset de professor).
  - `is_admin` permanece `self.role == "admin"`.
- Nova dependency `require_professor` (espelha `require_admin`): wraps `require_user`;
  lança **403** se `not user.is_professor`.
- **Valores de role válidos:** `"user"`, `"professor"`, `"admin"`. Nada além disso é aceito na escrita.

### Propagação do role (lag conhecido — aceitável)
Promover um aluno grava `role="professor"` na coluna `"user"`. O JWT do usuário
promovido **só reflete o novo role na próxima renovação/login** (o handoff re-minta
do banco; em 401 o front re-faz handoff). Isso é inerente ao modelo JWT zero-DB e é
aceitável para o caso de promoção. Documentar no PATCH (resposta inclui aviso de que
vale no próximo login do usuário).

---

## 2. Promover aluno→professor — `/q/admin/usuarios`

### Backend (todos `require_admin`)
- `GET /api/q/admin/usuarios?q=&page=` — lista usuários da tabela `"user"`
  (campos: `id`, `email`, `name`, `role`, `banned`, `createdAt`), busca por
  `email`/`name` (ILIKE), paginação (ex. 30/página). Ordena por `createdAt` desc.
- `PATCH /api/q/admin/usuarios/{uid}/role` — corpo `{ "role": "user"|"professor"|"admin" }`.
  - Valida role ∈ conjunto permitido (422 caso contrário).
  - **Guarda:** admin não pode alterar o **próprio** role (evita auto-rebaixamento que
    o trancaria fora do admin) → 400.
  - `UPDATE "user" SET role=:role WHERE id=:uid`. 404 se uid inexistente.
  - Resposta: `{ id, role }`.

### Frontend
- Página `/q/admin/usuarios` (admin-only; redireciona não-admin como as outras telas admin).
  - Tabela: nome, email, role atual (badge), `<select>` de role por linha → dispara PATCH.
  - Campo de busca (debounce) + paginação. React Query (`qk.adminUsuarios(q, page)`).
  - Feedback otimista no `<select>` com rollback em erro.
- `CreateUserCard` (em `/conta`): adicionar opção `"professor"` ao `<select>` de role
  (hoje só `user`/`admin`).
- Link "Usuários" no menu/área admin (onde já existem os links admin).

---

## 3. Modelo de dados

Tabela existente `questao_comentarios` ganha **duas colunas**:

| Coluna | Tipo | Default | Notas |
|---|---|---|---|
| `forum_tipo` | String(16) | `"alunos"` (server_default) | index. Discrimina o quadro: `"alunos"` \| `"professores"`. |
| `persona_nome` | String(64) | NULL | Nome da persona de cientista (só posts do admin no quadro professores). |

- Fórum dos alunos = `forum_tipo="alunos"` (todos os comentários existentes herdam o default).
- Fórum dos professores = `forum_tipo="professores"`.
- `comentario_votos` (votos) e `parent_id` (respostas, 1 nível) reutilizados sem mudança.
- **Migração Alembic:** `down_revision = '6cfa560c5346'` (head atual). Apenas `add_column`
  (com `server_default` em `forum_tipo` para preencher linhas existentes), seguindo o
  padrão da migração do fórum (excluir drift pré-existente não relacionado).

---

## 4. Personas de cientistas

### `backend/forum_personas.py` (novo)
Pool fixo de **15** cientistas:

```
Albert Einstein, Isaac Newton, Niels Bohr, Gottfried Leibniz,
J. Robert Oppenheimer, Werner Heisenberg, Ernest Rutherford,
Marie Curie, Galileu Galilei, Nikola Tesla, Richard Feynman,
Max Planck, Erwin Schrödinger, Paul Dirac, Michael Faraday
```

Função `sortear_persona(excluir: set[str] | None = None) -> str`:
- `random.choice` sobre o pool, evitando nomes em `excluir` quando possível
  (se todos excluídos, ignora a exclusão e sorteia normal).

### Atribuição
Na criação de um post no quadro **professores**:
- Se o autor é **admin**: `excluir` = personas já usadas em comentários-raiz da mesma
  questão (1 reroll lógico via `sortear_persona`); grava o resultado em `persona_nome`.
  A persona fica **fixa para sempre** naquele comentário (nunca re-sorteada em leitura).
- Se o autor é **professor real** (não-admin): `persona_nome` fica NULL → exibe o
  **nome real** do professor.

> **Toggle documentado:** caso no futuro se queira persona também para professores
> reais, basta remover o `if admin` e sortear para qualquer autor. Decisão atual:
> persona só para o admin.

### Exibição (`_display_name` estendido)
Para `forum_tipo="professores"`:
- `persona_nome` se houver (admin) → mostra o cientista.
- senão → `autor_nome` real do professor.
Edição/exclusão continuam por `owner_uid` (o admin edita "seu" post mesmo aparecendo
como "Einstein").

---

## 5. Endpoints (parametrizados por `quadro`)

Reutilizam os handlers do fórum dos alunos, adicionando o discriminador.

| Endpoint | Auth | Comportamento |
|---|---|---|
| `GET /questoes/{id}/forum?quadro=alunos\|professores` | `require_user` | Filtra `forum_tipo`. Default `quadro="alunos"`. Alunos leem ambos. |
| `POST /questoes/{id}/forum` (corpo inclui `quadro`) | `require_user` | **403** se `quadro="professores"` e `not user.is_professor`. Se professores: grava `forum_tipo="professores"`, `autor_tipo="professor"`; admin → atribui persona. |
| `PATCH /forum/{id}` | `require_user` | Reusado. Edita só o próprio (`owner_uid==user.id`). |
| `DELETE /forum/{id}` | `require_user` | Reusado. Dono ou admin (soft-delete). |
| `POST /forum/{id}/voto` | `require_user` | Reusado. **Alunos podem votar** em posts dos professores. |
| `POST /forum/upload` | `require_user` | Reusado (imagem só é anexável por quem consegue postar). |
| `GET /forum/imagem/{key}` | público | Reusado. |

- `quadro` validado como `Literal["alunos","professores"]` (Pydantic) — valor inválido → 422.
- Detalhe da questão (`GET /questoes/{id}`) ganha `forum_count_professores`
  (contagem de raízes `forum_tipo="professores"` não removidas) além do `forum_count`
  existente (que passa a contar explicitamente `forum_tipo="alunos"`).
- Serialização (`_serializar_comentario`) ganha `eh_professor: bool`
  (`forum_tipo=="professores"`) para o front renderizar o badge 🎓.

---

## 6. Frontend

### Reúso
- `ForumPanel` ganha props:
  - `quadro: "alunos" | "professores"` (default `"alunos"`).
  - `podeEscrever: boolean` — quando `false`, **esconde o `CommentEditor`** (e os botões
    de responder), deixando só leitura + voto.
  - `titulo`/ícone do header conforme o quadro.
- O chamador calcula `podeEscrever`:
  - quadro alunos → sempre `true` (qualquer logado).
  - quadro professores → `role ∈ {professor, admin}` (lido da sessão Better Auth, padrão
    inline `useSession()` já usado no projeto).
- `CommentItem` / `CommentEditor` / `ForumContent` reusados sem alteração de lógica;
  `CommentItem` exibe badge 🎓 "Professor" quando `comentario.eh_professor`.

### Query keys / hooks
- `qk.forum` passa a incluir `quadro`:
  `forum: (questaoId, quadro, ordenar) => ["q","forum", String(questaoId), quadro, ordenar]`.
- `useForum(questaoId, quadro, ordenar, enabled)` e os mutators passam `quadro` na URL/corpo.
- Invalidação por prefixo `["q","forum", String(questaoId), quadro]`.
- Atualizo os callers existentes do fórum dos alunos para passar `quadro="alunos"`.
- Nova key `qk.adminUsuarios(q, page)` para a página de usuários.

### Página da questão (`page.tsx`)
- Botão **🎓** (hoje enfeite) abre `ForumPanel` com `quadro="professores"`.
  - Estado `forumProfAberto`; abrir um quadro fecha o outro (💬 e 🎓 mutuamente exclusivos).
  - Badge no 🎓 com `forum_count_professores`.
  - Atalho de teclado `p` (professores), somando ao `f` (fórum alunos) já existente.

---

## 7. Testes

| Arquivo | Cobre |
|---|---|
| `test_forum_personas.py` | `sortear_persona` retorna do pool; respeita `excluir`; fallback quando todos excluídos. |
| `test_auth_roles.py` | `require_professor`: 401 deslogado, 403 aluno, ok professor, ok admin; `is_professor`/`is_admin`. |
| `test_forum_api.py` (extensão) | aluno → 403 ao postar em `quadro=professores`; admin posta e recebe `persona_nome` do pool; professor real posta com nome real (sem persona); aluno **lê** e **vota** em post de professor; `quadro` inválido → 422; `forum_count_professores` no detalhe; quadros isolados (post de um quadro não aparece no outro). |
| `test_admin_usuarios.py` | `GET` lista + busca (admin); 403 não-admin; `PATCH` muda role; role inválido → 422; admin não rebaixa a si mesmo → 400; uid inexistente → 404. |

---

## Fora de escopo (YAGNI)
- Professor promover outro professor (só admin promove, por enquanto).
- Persona para professores reais (toggle documentado, não implementado).
- Notificações/menções entre professores.
- Moderação cross-quadro (professor não edita post de outro professor; só o próprio).
- Importar comentários "professor" do TC para este quadro (o fórum dos alunos já cobre TC; este quadro é nativo studIA).

## Resumo das mudanças de arquivos

**Backend**
- `auth.py` — `is_professor`, `require_professor`.
- `forum_personas.py` — novo (pool + `sortear_persona`).
- `models.py` — `QuestaoComentario`: `forum_tipo`, `persona_nome`.
- `alembic/versions/xxxx_forum_professores.py` — novo (2 add_column).
- `q_router.py` — `quadro` em GET/POST do fórum; persona na criação; `eh_professor` na
  serialização; `forum_count_professores` no detalhe; endpoints admin de usuários
  (`GET`/`PATCH role`).
- `tests/` — 3 arquivos novos + extensão de `test_forum_api.py`.

**Frontend**
- `lib/queryKeys.ts` — `forum` com `quadro`; `adminUsuarios`.
- `app/q/hooks/useForum.ts` — `quadro` nos hooks; callers atualizados.
- `app/q/caderno/[id]/components/ForumPanel.tsx` — props `quadro`/`podeEscrever`.
- `app/q/caderno/[id]/components/CommentItem.tsx` — badge 🎓 via `eh_professor`.
- `app/q/caderno/[id]/page.tsx` — botão 🎓 + estado + atalho `p` + badge.
- `app/q/admin/usuarios/page.tsx` — nova página de gestão de roles.
- `app/conta/ContaClient.tsx` — opção `professor` no `CreateUserCard`.
- (hook/util de role do usuário atual, se necessário, seguindo o padrão `useSession` inline.)
