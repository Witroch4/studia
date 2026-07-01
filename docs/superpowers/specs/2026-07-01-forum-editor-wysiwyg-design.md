# Editor WYSIWYG do fórum (estilo TC) — Design

**Data:** 2026-07-01
**Status:** aprovado em conversa (opção "WYSIWYG TipTap")

## Problema

O editor do fórum é um `<textarea>`: o aluno vê código (`![imagem](url)`,
`<span data-cor=...>`) em vez da formatação, e editar tags na mão quebra o
markup (ex.: `</span<span ...>>` observado em produção). No TC o editor é
contentEditable: imagem, cor, fundo e tamanho aparecem renderizados dentro do
próprio corpo de edição. Objetivo: paridade com essa experiência.

## Decisão

Reescrever o miolo do `CommentEditor` com **TipTap** (ProseMirror, headless,
compatível com React 19), mantendo:

- a **API externa do componente** (`onSubmit`, `onCancel`, `submitting`,
  `valorInicial`, `autoFocus`, `placeholder`) — `ForumPanel` e `CommentItem`
  não mudam;
- o **formato de armazenamento atual** (`texto_md` com HTML simples +
  `<span data-cor|data-fundo|data-tam>` + `$...$` para fórmulas + markdown
  legado) — o render (`ForumContent`, pipeline rehype-raw → sanitize →
  componentes validados) **não muda e continua sendo a única fronteira de
  segurança XSS**;
- o **endpoint de upload existente** (`POST /api/q/forum/upload` → MinIO).

O painel "Pré-visualização" é removido: o editor é a visualização.

## Componentes

### 1. Editor TipTap (`CommentEditor.tsx` reescrito)

Extensões: StarterKit (negrito, itálico, listas, citação, undo/redo),
TextStyle + marks customizados **Cor**, **Fundo**, **Tamanho** (ver
serialização), Image, Mathematics (KaTeX ao vivo no corpo), Placeholder.

Toolbar (mesma linguagem visual atual, com estado ativo destacado):
↶ ↷ | B I | lista, citação | ∑ (fórmula) | 🖼 (upload) | A cor (paleta 10
cores), A fundo (paleta), Aa tamanho (12 / normal / 18 / 24 — "normal" remove
a marca).

### 2. Serialização compatível (marks customizados)

Os marks emitem/parseiam exatamente o formato já aceito pelo sanitize:

- cor da letra → `<span data-cor="#hex">`
- cor de fundo → `<span data-fundo="#hex">`
- tamanho → `<span data-tam="12|18|24">`

`Publicar` envia `editor.getHTML()` pós-processado:

- nós de matemática voltam a `$latex$` / `$$latex$$` (formato dos comentários
  antigos; o render já os trata via remark-math);
- documento vazio (`<p></p>`) vira string vazia (botão continua desabilitado).

### 3. Carga de conteúdo existente (edição)

`valorInicial` pode ser HTML novo ou markdown legado. Heurística: se contém
tags HTML de bloco conhecidas, carrega direto; senão converte
markdown → HTML com unified (remark-parse + remark-gfm + remark-rehype),
preservando `$...$` literal para o Mathematics parsear. Fórmulas e formatação
de comentários antigos continuam editáveis.

### 4. Imagens

- **Colar** (blob de "Copiar imagem"/print): reusa `forumClipboard.ts` →
  insere nó de imagem placeholder "enviando…" → upload MinIO → troca o `src`
  pela URL nossa. Falha de upload remove o nó e avisa inline.
- **Colar HTML com `<img>` externa** (sem blob): a imagem externa é
  **removida** no `transformPastedHTML` (nunca entra conteúdo que o render
  bloquearia).
- **Botão 🖼**: mesmo fluxo do paste.
- `Publicar` fica desabilitado ("Enviando imagem…") enquanto houver upload.

### 5. Render (sem mudança de comportamento)

`ForumContent` permanece o único renderer e a única fronteira de sanitização.
Ajuste pontual só se o StarterKit emitir alguma tag fora do schema atual
(ex.: `s` de riscado) — nesse caso a tag entra no schema com teste cobrindo.

## Fluxo de dados

digitar/colar → documento ProseMirror (renderizado ao vivo) → Publicar →
getHTML() + pós-processo → `texto_md` (API atual, sem migração de banco) →
`ForumContent` sanitiza e renderiza para todos os leitores.

## Erros

- Upload falho: nó placeholder removido + aviso inline no editor.
- Conversão markdown→HTML falha: carrega o texto cru como parágrafo (nunca
  perde conteúdo do usuário).
- HTML colado hostil: TipTap só absorve o que o schema das extensões conhece;
  e o render continua sanitizando de qualquer forma (defesa em profundidade).

## Testes

- **Unit (node --test):** serialização dos marks (data-cor/fundo/tam ida e
  volta), math ↔ `$...$`, heurística md/HTML, strip de `<img>` externa no
  paste. Helpers puros em módulos separados do componente para serem
  testáveis sem DOM.
- **Pipeline:** testes existentes de `forumMarkdown` continuam passando; novos
  casos para tags extras do StarterKit se entrarem no schema.
- **Browser (Playwright, harness temporário):** colar imagem (blob) e vê-la
  inline; aplicar cor/fundo/tamanho e ver ao vivo; fórmula renderizada;
  payload do Publicar no formato esperado; editar comentário legado em
  markdown.

## Fora de escopo

- Botão de tabela no editor (tabelas markdown seguem renderizando).
- Re-host em massa de imagens externas de comentários antigos.
- Outros editores do app (flashcards, etc.).

## Riscos

- **Versões TipTap × React 19/Next 16**: verificar na implementação (docs
  atuais via context7) e fixar versões no package.json.
- **Mathematics em conteúdo carregado** (não só digitado): usar o mecanismo de
  parse do extension-mathematics; se insuficiente, pré-converter `$...$` nos
  nós ao carregar. Critério de aceite: fórmula de comentário antigo aparece
  renderizada ao editar e volta como `$...$` ao salvar.
