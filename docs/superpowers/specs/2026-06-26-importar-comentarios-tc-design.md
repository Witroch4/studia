# Importar comentários do TecConcursos (alunos + professor)

**Data:** 2026-06-26
**Status:** Design aprovado, aguardando plano de implementação

## Problema

O studIA já tem um fórum de discussão por questão, com **dois quadros** (💬 alunos
e 🎓 professores) espelhando o TecConcursos. Hoje esses quadros só recebem
comentários escritos dentro do studIA. O objetivo é **importar os comentários
reais do TC** — a discussão dos alunos (foto: tabelas/imagens de resolução) e o
"Comentário em Texto" oficial do professor — casando cada comentário com a
questão correta e exibindo cada aluno como um pseudônimo estável.

## Descoberta-chave: o destino já existe

Quase toda a infraestrutura de armazenamento e exibição **já está construída**.
Falta apenas a fonte (buscar no TC e gravar).

| Camada | O que já existe | Arquivo |
|---|---|---|
| Banco | `questao_comentarios` com `origem` (`studia`/`tc`), `forum_tipo` (`alunos`/`professores`), `autor_tipo`, `autor_nome`, `curtidas`, `tc_comentario_id` (unique, dedup), `tc_parent_id` (thread) | `backend/models.py:644` |
| Banco | `Questao.id_externo` = `idQuestao` do TC (chave de match) | `backend/models.py:291` |
| Banco | `CadernoQuestoes.tc_caderno_id` + `question_ids` (lista ordenada) | `backend/models.py:442-445` |
| Backend | `GET /api/q/questoes/{id}/forum?quadro=` já filtra por quadro | `backend/q_router.py:1913` |
| Backend | `pseudonimo(seed)` determinístico aplicado em `origem=="tc"` | `backend/forum_pseudonimo.py` / `q_router.py:1882` |
| Backend | `upload_bytes()` / `get_presigned_url()` (re-host de imagem) | `backend/minio_client.py:30` |
| Scraper | `TcClient` (cookies via Playwright, proxy residencial, relogin automático), `html_to_md`, `render-latex → $…$` | `services/scraper/app/client.py`, `auth.py` |
| Frontend | 2 abas 🎓/💬, hotkeys `f`/`o`, dois `ForumPanel quadro=...` | `fontend/app/q/caderno/[id]/page.tsx:607-644` |

**Conclusão:** a feature é plugar a fonte (scraper → upsert), não construir o fórum.

## Decisões de design (do brainstorm)

1. **Híbrido**: coleta **sob demanda (lazy)** por padrão **+** botão de **coleta em
   massa** por caderno. Os dois compartilham o mesmo armazenamento e dedup.
2. **Imagens** dos comentários → **re-hospedadas no MinIO** (a sessão autenticada do
   scraper baixa, backend sobe via `upload_bytes`, reescreve a URL). Sem isso, os
   comentários que são só imagem ficam vazios.
3. **Abas separadas espelhando o TC**: 🎓 = resolução do professor, 💬 = fórum dos
   alunos. Já implementado no front; cada aba coleta sua própria fonte.
4. **Match por `id_externo`** (= `idQuestao` do TC), igual ao import de gabarito.
5. **Pacing do lote**: delay aleatório **5–15s por questão** (simulação humana,
   anti-bot-booster) — distinto do modo-humano genérico do scraper.

## Passo 0 (bloqueador) — descobrir os 2 endpoints do TC

A página `/questoes/{id}` é HTML; os comentários carregam por XHR separadas ainda
não mapeadas (o scraper hoje não busca **nenhum** comentário). Primeiro passo da
implementação:

- Rodar Playwright pela sessão autenticada do scraper, abrir uma questão, clicar
  em 💬 e 🎓, e capturar as 2 requisições (URL + método + payload + formato da
  resposta).
- **Dependência:** scraper logado no TC. Credenciais (`TC_EMAIL`/`TC_PASSWORD`)
  vão para as envs do stack do scraper — **nunca commitadas**. O usuário forneceu o
  login; será configurado fora do git.
- Se o passo 0 falhar (comentário server-rendered, exige captcha, etc.), o design
  muda — reavaliar antes de seguir.

## Arquitetura

### Scraper (`services/scraper`)

Duas funções novas, sobre o `TcClient` existente:

- `fetch_comentarios_alunos(id_questao) -> list[ComentarioTC]`
- `fetch_comentario_professor(id_questao) -> list[ComentarioTC]`

`ComentarioTC` normalizado:
```
{ tc_comentario_id, tc_parent_id, autor_nome, autor_tipo, curtidas, md, imagens[] }
```
- HTML do TC → markdown via `html_to_md` já existente (inclui `render-latex → $…$`).
- `imagens[]` = lista de URLs do TC encontradas no HTML.
- Rotas HTTP no scraper (consumidas pelo backend):
  - `GET /questao/{id}/comentarios?quadro=alunos|professores` → JSON normalizado.
  - `GET /tc/imagem?u=<url>` → stream dos bytes da imagem pela sessão autenticada
    (resolve imagens que exigem cookie/proxy).

### Backend

**Modelo novo (marcador):** `QuestaoTcImport`
```
questao_id  FK questoes.id
quadro      "alunos" | "professores"
fetched_at  datetime
count       int
UNIQUE(questao_id, quadro)
```
Função: distinguir "questão sem comentário no TC" de "ainda não buscada", evitando
re-scrape de questões vazias. Migração via `migrate.py` (auto-add) ou Alembic.

**Endpoint novo (lazy + unidade do lote):**
`POST /api/q/questoes/{questao_id}/importar-comentarios-tc?quadro=alunos|professores`
1. Carrega `Questao`; se `id_externo` for nulo → no-op (questão não veio do TC).
2. Se já existe marcador `(questao_id, quadro)` → retorna cedo (idempotente).
3. Chama o scraper `GET /questao/{id_externo}/comentarios?quadro=`.
4. Para cada imagem: baixa via `GET /tc/imagem?u=`, `upload_bytes()` no MinIO,
   reescreve a URL no markdown para o presigned URL.
5. **Upsert** em `questao_comentarios` (`origem="tc"`, `forum_tipo=quadro`,
   `autor_tipo`, dedup por `tc_comentario_id`, thread 1 nível por `tc_parent_id`).
6. Grava/atualiza o marcador com `count`.
7. Retorna `{ importados, ja_tinha, count }`.

**Endpoint alterado:** `GET /api/q/questoes/{id}/forum` passa a devolver
`tc_importado: bool` (lido do marcador para aquele quadro) para o front decidir se
dispara a coleta.

**Coleta em massa (job background, NATS):** reusa o sistema de jobs do scraper
(`enqueue/caderno`, `/job/{id}/{action}`, progresso no card — `q_router.py:299,663`).
- `POST /api/q/cadernos/{id}/importar-comentarios-tc` enfileira um job que varre
  `question_ids` do caderno, e para cada questão chama a mesma lógica de import
  (alunos + professores).
- **Delay aleatório 5–15s entre questões** (simulação humana). As duas chamadas de
  quadro de uma mesma questão podem ser back-to-back; o delay é por questão.
- Compartilha marcador + upsert com o lazy: questão já buscada por qualquer via não
  é re-scrapeada.
- Volume: ~876 questões × ~10s ≈ ~2–5h — aceitável para job de fundo "deixar
  baixando". Progresso e cancelamento via UI, como a coleta de questões.

### Frontend

**`ForumPanel`** (já recebe `quadro`): ao abrir, se `tc_importado === false`, chama
`POST …/importar-comentarios-tc?quadro=`, mostra spinner *"buscando no TC…"*, e
invalida a query do fórum ao concluir. Zero mudança de layout.

**Lista de cadernos** (`fontend/app/q/cadernos/page.tsx`): botão **"💬 TEC"** ao lado
do **"↓ TEC"** existente, no mesmo padrão (hover, estado de loading por caderno).
Dispara a coleta em massa do caderno (job background) e reflete o progresso.

## Casos de borda

- Questão sem `id_externo` → pula sem erro (não veio do TC).
- Reimport → idempotente por `tc_comentario_id` unique.
- Questão com **zero** comentário no TC → marcador gravado com `count=0`; não re-scrapeia.
- Pseudônimo determinístico: mesmo `autor_nome` → sempre o mesmo nome do pool.
- `curtidas` do TC exibidas; voto interno do studIA continua separado em `score`.
- Lazy e lote convergem no mesmo marcador/dedup — sem corrida de duplicação.

## Fora de escopo

- Comentário em **vídeo** do professor (só texto).
- Reimport/refresh automático com TTL (por ora, import-once; refresh manual fica
  para depois se houver demanda).

## Pacing interativo (lazy)

A chamada lazy é 1 request por quadro. Para não herdar as pausas longas do
modo-humano de varredura, o caminho interativo usa pacing leve (resposta em
segundos, com spinner). O delay 5–15s é só do **lote**.
