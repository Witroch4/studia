# Design: Fórum de discussão por questão (studIA)

**Data:** 2026-06-25
**Status:** Aprovado para planejamento

## Objetivo

Transformar o botão 💬 (hoje placeholder) da página de caderno em um fórum de
discussão funcional por questão, espelhando o fórum do TecConcursos. Cada aluno
pode escrever comentários, responder, votar e editar/excluir os próprios. O campo
de comentário interpreta markdown + LaTeX (incluindo o formato gerado pelo Gemini,
ex.: `$$D_h = CV \times TH$$`, `**negrito**`, `###`, listas).

## Decisões travadas

1. **Recursos (MVP):** completo estilo TC — posts + respostas (1 nível) + votos
   (▲/▼) + ordenação (Data/Pontos) + editar/excluir o próprio.
2. **Editor:** markdown com pré-visualização ao vivo.
3. **Comentários do TC:** feed único; comentários importados do TC aparecem
   anonimizados como se fossem comentários originais do studIA.
4. **Imagens:** upload para MinIO.
5. **Pseudônimo TC:** estável por autor (mesmo autor TC = sempre o mesmo nome
   fake) e inclui apenas `autor_tipo="aluno"` (professor reservado para o botão 🎓
   futuro).
6. **UI:** painel inline expansível abaixo da questão (igual TC).

## Arquitetura

### Modelo de dados

Reaproveita a tabela `questao_comentarios` (modelo `QuestaoComentario` em
`backend/models.py`), hoje **dormente e vazia** — nenhuma rota ou scraper a
popula. Por isso a alteração de schema não migra dados e já deixa a tabela pronta
para o futuro importador do TC.

**Colunas novas em `questao_comentarios`:**

| coluna | tipo | uso |
|---|---|---|
| `origem` | `String(16)`, default `"studia"` | `"studia"` (aluno) \| `"tc"` (importado) |
| `owner_uid` | `String`, nullable, index | dono = `CurrentUser.id` (Better Auth). NULL para TC |
| `parent_id` | `BigInteger`, self-FK → `questao_comentarios.id`, nullable, index | resposta. **1 nível só**: resposta sempre anexa a um post raiz |
| `score` | `Integer`, default 0, index | `curtidas` (seed do TC) + soma dos votos. Cache para ordenar |
| `edited_at` | `DateTime(tz)`, nullable | marca edição |
| `deleted_at` | `DateTime(tz)`, nullable | soft-delete |

**Colunas existentes reutilizadas:**

- `autor_nome` — studIA: nome do aluno no momento do post (snapshot, exibido);
  TC: nome original (**nunca exibido**, só usado como semente do pseudônimo).
- `autor_tipo` — `professor` | `aluno` (só `aluno` entra no feed).
- `texto_md` — markdown cru = **fonte da verdade** do conteúdo.
- `texto_html` — opcional (importado do TC); studIA não preenche (renderiza do md).
- `tc_comentario_id` / `tc_parent_id` — idempotência e threading do import futuro.
- `curtidas` — TC: semente de `score`; studIA: 0.
- `created_at`, `publicado_em` — data de criação / data original do TC.

**Tabela nova `comentario_votos`:**

| coluna | tipo |
|---|---|
| `id` | `BigInteger` PK |
| `comentario_id` | FK → `questao_comentarios.id` ON DELETE CASCADE, index |
| `usuario_uid` | `String`, index |
| `valor` | `SmallInteger` (`+1` \| `-1`) |
| `created_at` | `DateTime(tz)` server_default now |

Constraint `unique(comentario_id, usuario_uid)` — um voto por usuário por comentário.

### Pseudônimo de autores do TC

Determinístico e estável por autor: `pseudo(autor_nome) = POOL[hash(autor_nome) %
len(POOL)]`, onde `POOL` é uma lista curada de nomes PT-BR (nome + sobrenome) no
backend. Mesmo autor → sempre o mesmo nome fake (threads coerentes). Calculado em
tempo de leitura; nada extra é persistido. Aplica-se só a `origem="tc"`; para
`origem="studia"` exibe-se `autor_nome` (nome real do aluno).

### Renderização (segurança)

O conteúdo é **gerado por usuário**, portanto **não** pode usar o
`MarkdownRenderer` atual (`fontend/app/components/MarkdownRenderer.tsx`), que usa
`rehypeRaw` (HTML cru = XSS).

Novo componente **`fontend/app/components/ForumContent.tsx`**: mesmo pipeline
markdown (`react-markdown` + `remarkMath` + `rehypeKatex`) porém com
**`rehype-sanitize`** no lugar de `rehypeRaw`. Schema de sanitização estendido para:

- permitir as classes/elementos que o KaTeX emite (`span`, `math`, classes
  `katex*`, atributos `aria-hidden`, `style` controlado pelo KaTeX);
- permitir `<img>` apenas com `src` apontando para o endpoint de imagem do fórum
  do próprio app (`/api/q/forum/imagem/...` no host do backend), nunca URLs
  arbitrárias externas;
- bloquear scripts, handlers `on*`, iframes, etc.

As tags XML customizadas (`<atencao>/<destaque>/<resumo>`) **não** são suportadas
no fórum (saem na sanitização). Dependência nova: `rehype-sanitize`.

## Endpoints (backend — `backend/q_router.py`, prefixo `/api/q`)

Todos exigem `require_user` (banido bloqueado; coerente com o TC, que só mostra o
fórum logado).

### `GET /questoes/{questao_id}/forum?ordenar=recentes|pontos`

Retorna a árvore do fórum. Posts raiz ordenados por `recentes` (`created_at` desc)
ou `pontos` (`score` desc, desempate `created_at` desc). Respostas sempre por
`created_at` asc. Exclui registros `deleted_at` que sejam folha; mantém placeholder
para deletados que tenham respostas.

```jsonc
{
  "total": 12,            // posts + respostas não-deletados
  "comentarios": [
    {
      "id": 123,
      "parent_id": null,
      "origem": "studia",
      "display_name": "Maria Souza",   // pseudônimo se origem=tc
      "autor_inicial": "M",
      "texto_md": "...",               // null se removido
      "score": 2,
      "meu_voto": 0,                    // -1 | 0 | 1
      "criado_em": "2026-06-25T13:24:00Z",
      "editado": false,
      "removido": false,
      "posso_editar": true,            // dono e origem=studia
      "posso_excluir": true,           // dono ou admin
      "respostas": [ /* mesma forma, sem aninhar além de 1 nível */ ]
    }
  ]
}
```

### `POST /questoes/{questao_id}/forum`

Body `{ "texto_md": str, "parent_id": int|null }`. Cria comentário com
`origem="studia"`, `owner_uid=user.id`, `autor_nome=user.name`. Valida:
- `texto_md` não-vazio (após trim), tamanho máximo (ex.: 20.000 chars);
- se `parent_id`: o pai existe, é da **mesma** `questao_id` e é **raiz**
  (`parent_id IS NULL`) — proíbe resposta-de-resposta (achata em 1 nível).

Retorna o comentário criado (mesma forma do GET).

### `PATCH /forum/{comentario_id}`

Body `{ "texto_md": str }`. Só o **dono** e só `origem="studia"`. Seta `edited_at`.
404 se não existe/deletado; 403 se não é dono ou é `origem="tc"`.

### `DELETE /forum/{comentario_id}`

Soft-delete (`deleted_at = now`). Dono **ou** admin. Se tiver respostas, o corpo
vira "[comentário removido]" no GET (mantém a thread); se for folha, sai do feed.
Votos e score são congelados.

### `POST /forum/{comentario_id}/voto`

Body `{ "valor": 1|-1|0 }` (0 = remove o voto). Upsert/delete em
`comentario_votos`, recalcula e persiste `score` (= `curtidas` + Σ votos).
Bloqueia voto no **próprio** comentário (`owner_uid == user.id` → 400). Funciona
para `origem` `studia` e `tc`. Retorna `{ "score": int, "meu_voto": -1|0|1 }`.

### `POST /forum/upload`

`multipart/form-data` com `file`. Aceita `image/png|jpeg|webp|gif`, ≤ 5 MB.
Armazena no MinIO sob `forum/{uuid}.{ext}` (reutiliza `backend/minio_client.py`).
Retorna `{ "url": "<API>/api/q/forum/imagem/{key}" }` (URL estável do app).

### `GET /forum/imagem/{key}`

302 para URL presigned do MinIO. Sem `require_user` (a imagem é embutida em
markdown e carregada pelo browser). Valida o formato do `key` (`forum/<uuid>.<ext>`).

### Badge de contagem

Adiciona `forum_count` (comentários não-deletados da questão) ao serializer do
**detalhe da questão** já consumido pela página do caderno
(`GET /api/q/{questao_id}` em `q_router.py`), para o badge do botão 💬 sem abrir o
painel.

## Frontend

Página afetada: `fontend/app/q/caderno/[id]/page.tsx`.

### Componentes novos

- **`ForumPanel.tsx`** — painel inline expansível abaixo da questão. Header
  "💬 Fórum de discussão" + seletor Ordenar `[Data | Pontos]` + Fechar. Editor de
  novo comentário + lista de `CommentItem`. Estado de loading/erro/vazio.
- **`CommentItem.tsx`** — coluna de voto (▲ `score` ▼ com destaque do `meu_voto`),
  avatar (inicial do `display_name`), nome, data relativa, corpo via
  `ForumContent`, ações (Responder / Editar / Excluir conforme `posso_*`), e
  respostas aninhadas (1 nível). Reply abre `CommentEditor` inline com `parent_id`.
- **`CommentEditor.tsx`** — abas **Escrever | Pré-visualizar**; toolbar mínima
  (B, I, lista, link, fórmula `$$`, imagem→upload); textarea; Publicar / Cancelar.
  Upload chama `POST /forum/upload` e insere `![](url)` no cursor. Aba Preview
  renderiza via `ForumContent`.
- **`ForumContent.tsx`** — renderer markdown+KaTeX sanitizado (ver acima).

### Hooks (React Query — `fontend/app/q/hooks/useForum.ts`)

- `useForum(questaoId, ordenar)` — `useQuery`.
- `useCreateComment`, `useEditComment`, `useDeleteComment` — `useMutation` com
  invalidação de `['forum', questaoId]`.
- `useVote` — `useMutation` **otimista** (atualiza `score` e `meu_voto` na hora,
  rollback no erro).

### Integração na página

No bloco de botões ([page.tsx](../../../fontend/app/q/caderno/[id]/page.tsx) ~L577-602):
- estado `forumAberto` alterna o `ForumPanel`;
- badge com `forum_count` no botão 💬;
- atalho de teclado **`f`** alterna o fórum (respeitando o handler de atalhos
  existente, sem disparar quando o foco está em campo de texto).

## Migração

Uma migração Alembic (`backend/alembic/versions/`):
- `ALTER TABLE questao_comentarios` adicionando `origem`, `owner_uid`, `parent_id`
  (+ self-FK), `score`, `edited_at`, `deleted_at` e índices (`owner_uid`,
  `parent_id`, `score`);
- `CREATE TABLE comentario_votos` (+ unique e índices).

Tabela vazia → seguro. Gerar via `alembic revision --autogenerate`, revisar, e
`scripts/db_prepare` aplica no deploy (`./build.sh`).

## Testes (pytest — `backend/tests/`)

- Criar comentário raiz e resposta; **proíbe resposta-de-resposta** (1 nível).
- Resposta a `parent_id` de outra questão → erro.
- Votar: adicionar, trocar (+1→-1), remover (0); **não pode votar no próprio**;
  `score` reflete `curtidas` + votos.
- Editar/excluir: dono OK; outro usuário 403; admin pode excluir qualquer;
  não pode editar `origem="tc"`.
- Soft-delete: folha some do feed; com respostas vira placeholder; `forum_count`
  ignora deletados.
- Ordenação `recentes` vs `pontos`.
- Anonimização TC: `origem="tc"` nunca expõe `autor_nome`; pseudônimo estável;
  só `autor_tipo="aluno"` entra no feed.
- Upload: rejeita tipo inválido e arquivo acima do limite.

## Fora de escopo (YAGNI)

- Filtros "Usuário" / "Meus votos" do TC.
- Denúncia/flag, notificações ("acompanhar esta questão"), menções.
- Respostas além de 1 nível; edição de comentários do TC; tempo-real.
- O **importador de comentários do TC** em si (o schema fica pronto; a coleta é
  trabalho separado).
- Rate limiting / antispam (anotar como melhoria futura).
