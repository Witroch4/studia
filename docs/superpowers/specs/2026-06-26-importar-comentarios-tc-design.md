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

1. **Híbrido em 2 fases**: **Fase 1 (MVP)** = coleta **sob demanda (lazy)** por aba.
   **Fase 2** = botão de **coleta em massa** por caderno. Ambas no plano; a Fase 2 é
   a próxima fase logo após a Fase 1 estar de pé. As duas compartilham o mesmo
   armazenamento, marcador e dedup (ver seção "Fases").
2. **Copy do frontend (obrigatória)**: nenhuma string visível ao usuário pode citar
   "TC", "TecConcursos", "tec" ou similar. A origem da coleta é detalhe interno
   (backend/scraper), **nunca** exposto na UI. Termos neutros: *"Buscando…"*,
   *"Importar comentários"*, *"Comentários da comunidade"*.
3. **Imagens** dos comentários → **re-hospedadas no MinIO** (a sessão autenticada do
   scraper baixa, backend sobe via `upload_bytes`, reescreve a URL). Sem isso, os
   comentários que são só imagem ficam vazios.
4. **Abas separadas** espelhando o layout de origem: 🎓 = resolução do professor,
   💬 = fórum dos alunos. Já implementado no front; cada aba coleta sua própria fonte.
5. **Match por `id_externo`** (= `idQuestao` do TC), igual ao import de gabarito.
6. **Pacing do lote**: delay aleatório **5–15s por questão** (simulação humana,
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

## Fases

A entrega é sequenciada. Ambas estão no plano; a Fase 2 começa assim que a Fase 1
estiver de pé.

- **Fase 1 (MVP) — coleta sob demanda (lazy).** Passo 0 (descoberta) + 2 fetch no
  scraper + re-host de imagem no MinIO + endpoint de upsert + marcador anti-rescrape
  + spinner *"Buscando…"* no `ForumPanel`. Entrega valor estudando questão a questão.
- **Fase 2 — coleta em massa por caderno.** Job background (NATS) varrendo todas as
  questões do caderno, delay 5–15s/questão, com botão neutro **"💬 Importar"** na
  lista de cadernos + progresso/cancelamento. Reusa 100% da lógica de upsert,
  marcador e dedup da Fase 1 — é só orquestração em lote por cima.

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
`POST …/importar-comentarios-tc?quadro=`, mostra spinner **"Buscando…"** (sem citar
a origem), e invalida a query do fórum ao concluir. Zero mudança de layout.

**Lista de cadernos** (Fase 2 — `fontend/app/q/cadernos/page.tsx`): botão neutro
**"💬 Importar"** (label sem "TEC"/"TC") ao lado do botão de gabarito existente, no
mesmo padrão (hover, estado de loading por caderno). Dispara a coleta em massa do
caderno (job background) e reflete o progresso. Nota: o botão de gabarito atual
exibe **"↓ TEC"** — viola a regra de copy; **renomear para algo neutro** (ex.:
**"↓ Desempenho"**) entra como ajuste junto da Fase 2.

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

---

# Fase 2 — Arquitetura detalhada (coleta em massa por caderno)

**Status:** Fase 1 (lazy) NO AR (deploy 2026-06-27). Esta seção detalha a Fase 2,
aprovada no brainstorm de 2026-06-27.

## Princípio: reusar a Fase 1, durabilidade no scraper

A lógica de import (fetch + upsert + re-host de imagem + marcador) já existe e está
testada no **backend** (`POST /api/q/questoes/{id}/importar-comentarios-tc?quadro=`).
A Fase 2 **não reimplementa nada disso** — ela orquestra um job durável no scraper
(ledger NATS, igual à coleta de questões) que, por questão, **chama esse endpoint**.
Lazy e massa convergem no mesmo marcador/dedup: uma questão já trazida pelo lazy é
pulada (o endpoint devolve `ja_importado`).

## Decisões (do brainstorm)

1. **Reuso via HTTP interno:** o worker do scraper chama o endpoint da Fase 1 (não
   duplica upsert/re-host). 
2. **Unit = 1 questão**, cobrindo os 2 quadros (alunos + professores) — 2 chamadas
   ao endpoint por unit. O **delay 5–15s** aplica-se **por questão** e **só após
   chamadas que realmente bateram no TC** (quando o endpoint devolve
   `ja_importado=false`); se ambos os quadros já estavam importados, sem sleep.
3. **Disparo no card do caderno** (`/q/cadernos`), **admin-only**, ao lado do
   gabarito. Label neutro **"💬 Importar"**; o "↓ TEC" do gabarito é renomeado para
   **"↓ Desempenho"** (regra de copy: sem "TC"/"tec" na UI).
4. **Progresso/controle no painel admin `/q/coletar`** (reusa barra + pausar/retomar
   + polling 15s já existentes), estendido para `kind='comentarios'`.

## Componentes

### Scraper — ledger (`app/tasks/ledger.py`)

- Novo `kind='comentarios'` em `tc_jobs` (o índice único de job ativo tem cláusula
  `WHERE kind='caderno'`, então não há conflito; criar um índice análogo
  `WHERE kind='comentarios'` para "1 job de comentários ativo por caderno").
- **Nova tabela `tc_comentario_units`**: `id`, `job_id` (FK tc_jobs), `caderno_id`,
  `questao_id` (id studIA), `status` (pending|queued|running|blocked|done|failed),
  `attempts`, `leased_until`, `coments_alunos`, `coments_professores`, `http_status`,
  `block_reason`, `blocked_until`. `UNIQUE(job_id, questao_id)`.
- Funções análogas às de caderno: `upsert_comentario_job(session, *, caderno_id,
  questao_ids, requested_by)` (cria job + 1 unit/questão via ON CONFLICT DO NOTHING),
  `list_enqueueable_comentario_units`, `lease_comentario_unit`,
  `mark_comentario_unit_done/blocked/failed`, `refresh_comentario_job_status`,
  `list_active_comentario_jobs`. `set_caderno_job_paused`/`get_caderno_job` já são
  kind-agnósticos (operam em `tc_jobs` por id) — reusar.

### Scraper — worker (`app/tasks/comentarios.py`)

- `coletar_comentarios_questao(questao_id, caderno_id)` (broker default).
- Por unit: lease atômico → checa pausa (`paused_by_user`) → para cada
  `quadro in (alunos, professores)`: `POST {BACKEND_URL}/api/q/questoes/{questao_id}/
  importar-comentarios-tc?quadro=` com header `X-Internal-Token`. Se a resposta tem
  `ja_importado=false` (bateu no TC), dorme `random.uniform(comentario_pause_min,
  comentario_pause_max)` = **5–15s**; se `ja_importado=true`, sem sleep.
- Marca unit done (contadores = `importados` por quadro) → enfileira a próxima unit
  elegível (chain). Erros de bloqueio (o endpoint devolve 502 por sessão queimada
  irreparável) → `mark_comentario_unit_blocked` com cooldown; outras exceções →
  `failed`. (Sessão expirada comum se auto-cura no fetch via relogin+proxy — não
  falha a unit.)
- Config nova em `config.py`: `comentario_pause_min=5.0`, `comentario_pause_max=15.0`.

### Scraper — API (`app/main.py`)

- `POST /enqueue/comentarios` body `{caderno_id, questao_ids: [int], requested_by?}`
  → `ensure_ledger_schema` → `upsert_comentario_job` → enfileira a 1ª unit →
  devolve `{job_id, status, total_units, enqueued_units}`.

### Backend (`backend/q_router.py`)

- **Auth de serviço:** dependência que aceita **sessão de usuário OU**
  `X-Internal-Token == STUDIA_INTERNAL_TOKEN` (env, injetado pelo build.sh). Aplicada
  ao endpoint `importar-comentarios-tc` (para o worker poder chamá-lo). O token é
  segredo forte (o endpoint é roteável via Traefik).
- `POST /api/q/cadernos/{caderno_id}/importar-comentarios-tc` (**admin**): lê
  `CadernoQuestoes.question_ids`, chama `POST {SCRAPER_URL}/enqueue/comentarios` com a
  lista, devolve `{job_id, status, total_units, ...}`.
- `GET /api/q/coletar/jobs` estendido (ou sibling `comentario-jobs`) para incluir
  `kind='comentarios'` com os contadores/progresso (`pct_units_done`). Pausar/retomar
  já funcionam (proxies `/job/{id}/pause|resume`, kind-agnósticos).

### Scraper — supervisor

- `_queue_supervisor_loop` estendido para também listar `list_active_comentario_jobs`
  e re-enfileirar units elegíveis (recupera de bloqueio/cooldown e units órfãs). Sem
  isso, um bloqueio duro pararia o chain até reinício.

### Frontend (`fontend/app/q/cadernos/page.tsx`)

- Botão **"💬 Importar"** no card (hover, ao lado do gabarito), **admin-only** (gate
  pelo papel já disponível no front). Ao clicar: `POST /api/q/cadernos/{id}/importar-
  comentarios-tc`, mostra "coletando…" brevemente, toast "coleta iniciada — acompanhe
  em Coletar". Renomeia o `"↓ TEC"` existente → **"↓ Desempenho"**.
- Painel `/q/coletar` (`fontend/app/q/coletar/page.tsx`): renderiza também os jobs de
  comentários (mesma barra/pausar), via a query estendida.

## Casos de borda (Fase 2)

- Caderno sem `question_ids` (vazio) → job com 0 units, status done imediato.
- Questão sem `id_externo` → o endpoint da Fase 1 já faz no-op; a unit conclui sem
  bater no TC e sem sleep.
- Re-disparo no mesmo caderno com job ativo → o índice único bloqueia 2º job ativo;
  devolve o job existente. Re-disparo após done → recria units (idempotente; questões
  já marcadas pulam rápido).
- Pausar no meio → `paused_by_user=true`; o worker libera a unit corrente para
  `pending` e para; retomar volta o chain.
- Token de serviço ausente/errado → 401 no endpoint; o worker marca a unit failed e
  loga (não vaza dado).

## Fora de escopo (Fase 2)

- Barra de progresso inline no card do caderno (fica no painel `/q/coletar`).
- Agendamento horário / janela de execução.
- Coleta de comentário em vídeo.
