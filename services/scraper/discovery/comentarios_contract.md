# Contrato — endpoints de comentários do TecConcursos

Capturado em 2026-06-26 via DevTools/MCP na questão `id_externo=2272394`, logado.
Fixtures reais: `tests/fixtures/coment_alunos_sample.json`, `coment_professor_sample.json`.

## 💬 Fórum dos alunos (botão "Fórum de discussão", atalho `f`)

- **Método/URL:** `GET /api/discussoes/{id_questao}/comentarios-alunos?ordenarPor=data&pagina={n}`
  - ATENÇÃO: base é `/api/discussoes/{id}`, **não** `/api/questoes/{id}`.
  - `ordenarPor`: `data` | `pontos`. `pagina`: 1-indexed.
- **Referer:** `https://www.tecconcursos.com.br/questoes/{id_questao}`
- **Resposta:** lista em `comentarios.pageComentarios.list`. Paginação em
  `comentarios.pageComentarios`: `pageSize` (50), `currentPage`, `totalPages`,
  `listSize`. (No exemplo, `totalPages=0` com 3 itens → página única parcial:
  parar quando `len(list) < pageSize`.)
- **Item:**
  | campo TC | uso |
  |---|---|
  | `id` (int) | `tc_comentario_id` |
  | `apelidoUsuario` (str) | `autor_nome` (re-pseudonimizado na exibição) |
  | `quantidadeVoto` (int) | `curtidas` (votos no comentário) |
  | `comentario` (str HTML) | corpo → `html_to_md`; imagens em `<img src>` |
  | `professor` / `administrador` (bool) | `autor_tipo` |
  | `dataPublicacao.$` ("DD/MM/AAAA HH:MM:SS") | `publicado_em` |
  - `pontos` é a reputação do USUÁRIO (não do comentário) — ignorar.
  - Sem campo de resposta/thread no exemplo → tratar tudo como raiz (`tc_parent_id=None`).

## 🎓 Comentário do professor (botão "Comentário da Questão", atalho `o`)

- **Método/URL:** `GET /api/questoes/{id_questao}/comentario?tokenPreVisualizacao=`
- **Referer:** `https://www.tecconcursos.com.br/questoes/{id_questao}`
- **Resposta:** objeto único em `comentario` (1 comentário oficial por questão).
- **Campos:**
  | campo TC | uso |
  |---|---|
  | `textoComentario` (str HTML) | corpo → `html_to_md`; tem `span.render-latex` e imagens |
  | `nomeProfessor` (str) | `autor_nome` (re-pseudonimizado) |
  | `dataFormatadaParaHtml5` ("AAAA-MM-DD") | `publicado_em` |
  - **Sem id de comentário** → sintetizar `tc_comentario_id = -id_questao` (determinístico,
    1/questão, sem colidir com ids positivos do fórum).
  - `autor_tipo = "professor"`.

## Hosts de imagem (allowlist anti-SSRF do proxy `/tc/imagem`)

- `cdn.tecconcursos.com.br`
- `s3-sa-east-1.amazonaws.com` (bucket `conteudo.tecconcursos.com.br`)
- qualquer `*.tecconcursos.com.br`

Regra: `host == "s3-sa-east-1.amazonaws.com"` OU `host` termina em `tecconcursos.com.br`.
