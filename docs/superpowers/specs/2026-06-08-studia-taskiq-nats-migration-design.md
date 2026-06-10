# studIA - Base TaskIQ/NATS para coleta TC e imagens

**Status**: Design revisada, foco na base operacional  
**Owner**: Wital  
**Data**: 2026-06-08  
**Doc-pai normativa**: [witdev-platform-core/docs/TASKIQ_PLATFORM_ARCHITECTURE.md](../../../../witdev-platform-core/docs/TASKIQ_PLATFORM_ARCHITECTURE.md)

---

## 1. Decisão desta revisão

Esta spec substitui o desenho anterior que tentava trazer Control Center, painel
central e toda a superfície da platform de uma vez.

**Decisão atual**: implementar primeiro uma base profissional mínima:

- NATS JetStream como fila persistente;
- workers permanentes, sem container cujo `CMD` seja o lote inteiro;
- ledger de jobs/unidades em Postgres;
- idempotência em duas camadas: enqueue e execução;
- retries com cooldown e sem loop agressivo;
- DLQ operacional básica;
- cadernos divididos em unidades pequenas;
- imagens usando a mesma metodologia.

**Fora de escopo agora**:

- Control Center;
- painel `/admin/monitoring/taskiq`;
- UI sofisticada de monitoramento;
- migração completa do `backend/worker.py` legado em Redis;
- mover todo o scraper para dentro do backend principal.

O foco é parar a bagunça: nada de lote reiniciando do zero, nada de checkpoint
em arquivo como fonte de verdade, nada de imagem rodando como script monolítico
sem controle.

---

## 2. Problema real

Na coleta TC de 2026-06-07 para 2026-06-08, o container executava o lote como
comando principal:

```text
container start
  -> python scripts/scrape_lote.py cadernos_petrobras.json
  -> lote termina com exit 0
  -> swarm restart_policy=any reinicia
  -> lote comeca do zero
  -> UPSERT dedup no banco esconde o loop
```

Resultado:

- cerca de 5 execuções em 24h;
- requests repetidos ao TC;
- consumo inútil de CPU, Chromium, proxy e sessão;
- progresso real invisível;
- risco de queimar conta/IP;
- imagens prestes a repetir o mesmo erro se rodarem como script longo.

A causa raiz não é só `restart_policy=any`. Isso foi o gatilho. A causa raiz é
que o trabalho era modelado como **processo**, não como **fila de tarefas
persistentes com estado externo**.

---

## 3. Invariantes

1. Serviço Docker sobe worker permanente. Serviço Docker não é lote.
2. Unidade de trabalho tem chave natural estável e estado em Postgres.
3. Reenfileirar unidade já concluída é no-op.
4. Crash de container não perde progresso nem reinicia o job inteiro.
5. 401/452/403/429 do TC não podem virar retry quente.
6. Imagem segue o mesmo padrão de caderno: uma unidade, uma chave, um estado.
7. `.kiq()` direto não é usado em callsites de negócio; publicação passa por
   uma facade `enqueue()` com `idempotency_key`.
8. A lane existe de verdade somente se houver broker registrado e worker
   consumindo aquela lane.
9. Job de caderno só fica `done` quando **todas** as faixas planejadas do
   caderno estiverem `done`.
10. Se a faixa `inicio=1200,page_size=200` falhar, a retomada reenfileira essa
    mesma faixa; nunca recomeça em `inicio=0`.

---

## 4. Arquitetura escolhida

### 4.1 Separação por serviço

O caminho mais seguro no repo atual é manter o trabalho externo TC dentro de
`services/scraper`, porque esse serviço já possui:

- Playwright;
- login TC;
- `storage_state.json`;
- proxy residencial;
- scraper `/imprimir`;
- persistência direta no Postgres studIA;
- script de imagens com MinIO.

O `backend` fica como control-plane:

- recebe `POST /api/q/coletar`;
- valida URL/caderno;
- chama uma operação rápida de enqueue;
- retorna `202 Accepted` com `job_id`;
- expõe consulta simples de job/progresso lendo Postgres.

No primeiro corte, esse enqueue rápido pode ser um HTTP curto para
`studia-scraper-api` (`POST /enqueue/caderno`), e o scraper publica no NATS.
Isso mantém as definições TaskIQ junto do serviço que já tem Playwright/proxy.
Depois, se fizer sentido, o producer pode ser movido para o backend.

O `services/scraper` vira também worker NATS:

- publica jobs/fatias;
- consome tasks;
- executa TC/MinIO;
- atualiza ledger no Postgres.

Isto evita instalar Playwright no backend principal agora e reduz o blast radius.

### 4.2 NATS JetStream

Domínio lógico: `studia`.

```text
Stream: TASKIQ_STUDIA

Subjects:
  taskiq.studia.default
  taskiq.studia.low
  taskiq.studia.dlq

Durables:
  studia-default-workers
  studia-low-workers
  studia-dlq-inspect
```

As lanes `critical` e `high` ficam reservadas, mas não entram no primeiro corte.
Elas só devem ser habilitadas quando houver broker registrado e processo de
worker consumindo a lane. Isto segue o alerta da arquitetura da platform:
`priority="high"` sozinho não cria isolamento real.

### 4.3 Semântica inicial das lanes

| Lane | Uso inicial | Concorrência inicial |
|---|---|---:|
| `default` | coleta TC por página/faixa | 1 worker |
| `low` | imagens CDN -> MinIO, rewrite, manutenção | 5 workers |

Coleta TC começa com concorrência 1 de propósito. Dividir caderno em tasks não
significa bombardear o TC; significa controlar progresso, retry e retomada.
Para essa garantia ser real, a lane `default` inicial deve usar `pull_batch=1`
e `max_ack_pending=1`.

Imagens podem paralelizar mais porque o alvo é CDN público, mas ainda com limite
explícito.

---

## 5. Modelo de dados operacional

O estado operacional fica no Postgres do studIA. SQLite em `/state` deixa de ser
fonte de verdade para progresso.

### 5.1 `tc_jobs`

Representa um job raiz.

```sql
CREATE TABLE tc_jobs (
  id BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL,               -- caderno | imagens | rewrite_imagens
  status TEXT NOT NULL,             -- pending | running | blocked | done | failed | cancelled
  source TEXT NOT NULL,             -- tc | tc_cdn
  external_id TEXT,                 -- caderno_id ou batch key
  expected_total INTEGER,
  page_size INTEGER NOT NULL DEFAULT 200,
  requested_by INTEGER,
  params JSONB NOT NULL DEFAULT '{}',
  total_units INTEGER NOT NULL DEFAULT 0,
  done_units INTEGER NOT NULL DEFAULT 0,
  failed_units INTEGER NOT NULL DEFAULT 0,
  blocked_units INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  blocked_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_tc_jobs_active_caderno
ON tc_jobs (kind, external_id)
WHERE kind = 'caderno' AND status IN ('pending', 'running', 'blocked');
```

### 5.2 `tc_caderno_units`

Uma unidade é uma página/faixa do endpoint `/imprimir`.

```sql
CREATE TABLE tc_caderno_units (
  id BIGSERIAL PRIMARY KEY,
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  caderno_id BIGINT NOT NULL,
  inicio INTEGER NOT NULL,
  page_size INTEGER NOT NULL DEFAULT 200,
  position_start INTEGER NOT NULL,  -- 1-based, inclusivo, para leitura humana
  position_end INTEGER NOT NULL,    -- 1-based, inclusivo, para leitura humana
  status TEXT NOT NULL,             -- pending | queued | running | blocked | done | failed
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  questoes_ok INTEGER NOT NULL DEFAULT 0,
  questoes_novas INTEGER NOT NULL DEFAULT 0,
  questoes_atualizadas INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER,
  block_reason TEXT,
  blocked_until TIMESTAMPTZ,
  last_error TEXT,
  leased_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  UNIQUE (caderno_id, inicio, page_size)
);

CREATE INDEX idx_tc_caderno_units_job_status
ON tc_caderno_units (job_id, status, inicio);

CREATE INDEX idx_tc_caderno_units_blocked_until
ON tc_caderno_units (status, blocked_until);
```

### 5.3 `tc_image_assets`

Uma unidade é uma imagem única do CDN.

```sql
CREATE TABLE tc_image_assets (
  uuid TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  status TEXT NOT NULL,             -- pending | queued | running | done | failed | not_found
  task_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  minio_url TEXT,
  minio_object_key TEXT,
  content_type TEXT,
  bytes INTEGER,
  http_status INTEGER,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE INDEX idx_tc_image_assets_status
ON tc_image_assets (status, updated_at);
```

### 5.4 `tc_image_job_assets`

Relaciona um batch de imagens com os assets.

```sql
CREATE TABLE tc_image_job_assets (
  job_id BIGINT NOT NULL REFERENCES tc_jobs(id) ON DELETE CASCADE,
  image_uuid TEXT NOT NULL REFERENCES tc_image_assets(uuid) ON DELETE CASCADE,
  PRIMARY KEY (job_id, image_uuid)
);
```

O rewrite não olha `num_pending` da lane low. Ele olha este relacionamento:
quando o job não tem assets `pending|queued|running|blocked`, o rewrite pode ser
enfileirado uma única vez.

---

## 6. Granularidade correta

### 6.1 Caderno não é mais uma task gigante

Modelo novo:

```text
Job: caderno 95872872
  Unit 1: inicio=0, page_size=200
  Unit 2: inicio=200, page_size=200
  Unit 3: inicio=400, page_size=200
  ...
```

Mas as unidades não precisam ser todas executadas em paralelo.

O campo `inicio` é o `configuracoes.questaoInicial` do endpoint TC. Ele é
0-based. Para operação humana, a unidade também grava `position_start` e
`position_end` 1-based.

Exemplo:

| `inicio` | `page_size` | posições humanas |
|---:|---:|---|
| 0 | 200 | 1-200 |
| 200 | 200 | 201-400 |
| 1000 | 200 | 1001-1200 |
| 1200 | 200 | 1201-1400 |

Se `inicio=1000` deu certo e `inicio=1200` falhou, o ledger fica assim:

```text
caderno 95872884
  inicio=0       done
  inicio=200     done
  ...
  inicio=1000    done
  inicio=1200    blocked/failed
```

Quando o cooldown vencer, o reconciliador reenfileira **somente**
`tc:page:95872884:1200:200`. Ele não reenfileira `inicio=0` e não roda o
caderno todo de novo.

Para TC, o modo inicial é **janela 1 por caderno**:

1. enfileira a primeira unidade;
2. se ela terminar com 200 questões, cria/enfileira a próxima;
3. se terminar parcial ou vazia, fecha o job;
4. se bloquear em 401/452/403/429, pausa o job com `blocked_until`;
5. um reconciliador reativa jobs bloqueados somente depois do cooldown.

Isto dá controle fino sem provocar anti-bot.

Quando o total exibido pelo TC é conhecido, o planner cria todas as unidades
esperadas antes de começar. Isso permite medir cobertura real e saber
exatamente quais faixas faltam.

Exemplos:

| Caderno | TC mostra | `page_size` | Unidades esperadas | Último `inicio` |
|---|---:|---:|---:|---:|
| 95872853 | 11.364 | 200 | 57 | 11.200 |
| 95872884 | 15.298 | 200 | 77 | 15.200 |
| 95872821 | 22.455 | 200 | 113 | 22.400 |
| 95872872 | 29.774 | 200 | 149 | 29.600 |

O job só é considerado 100% completo quando a contagem de unidades `done`
atinge `ceil(expected_total / page_size)`. Se qualquer unidade permanecer
`pending`, `queued`, `running`, `blocked` ou `failed`, o caderno não é completo.

### 6.2 Imagem é uma task por UUID

Modelo novo:

```text
Job: imagens 2026-06-08
  Asset aaaaa-bbbb...
  Asset ccccc-dddd...
  Asset eeeee-ffff...
```

Cada UUID tem status próprio. Rodar de novo o batch não baixa novamente o que já
está em `done`.

---

## 7. Catálogo inicial de tasks

As tasks ficam em `services/scraper/app/tasks/` no primeiro corte.

### 7.1 `POST /enqueue/caderno`

```python
async def enqueue_caderno(
    caderno_id: int,
    expected_total: int | None = None,
    page_size: int = 200,
    enqueue_limit: int | None = 1,
    discover_total: bool = False,
    relogin: bool = False,
) -> dict:
    """Cria/reutiliza job, planeja faixas e enfileira unidades elegíveis."""
```

Idempotência de enqueue:

```text
tc-page:{sha256(caderno_id, inicio, page_size, attempts + 1)}
```

Efeito:

- upsert em `tc_jobs`;
- grava `expected_total` quando conhecido;
- calcula `total_units = ceil(expected_total / page_size)` quando há total;
- cria as unidades esperadas (`inicio=0,200,400...`) com `UNIQUE` idempotente;
- se o total não for conhecido, cria apenas `inicio=0`; garantia de 100% exige `expected_total`;
- enfileira unidades `pending`, `failed` e `blocked` com cooldown vencido;
- não enfileira unidades `done`, `running` ou `blocked` ainda dentro do cooldown;
- `enqueue_limit=0` é modo dry-plan: cria/reutiliza job e unidades sem publicar tasks;
- `enqueue_limit=1` é o modo padrão seguro: publica só a menor faixa elegível;
- `discover_total=true` tenta descobrir o total no TC antes de planejar as faixas;
- `relogin=true` renova `storage_state.json` antes de publicar a primeira unidade;
- duplicata da mesma tentativa é no-op por Redis; nova tentativa usa `attempts + 1`.

### 7.2 `coletar_pagina_caderno_tc`

```python
async def coletar_pagina_caderno_tc(
    caderno_id: int,
    inicio: int,
    page_size: int = 200,
) -> dict:
    """Busca uma página/faixa do endpoint imprimir e persiste as questões."""
```

Idempotência de enqueue:

```text
tc-page:{sha256(caderno_id, inicio, page_size, attempts + 1)}
```

Regras:

- se unidade está `done`, retorna skip;
- se outra execução tem lease válido, retorna skip;
- marca `running`;
- chama `fetch_pagina`;
- upserta questões;
- marca `done`;
- a task não recomeça o caderno nem decide executar `inicio=0`;
- após sucesso, a task enfileira exatamente a próxima menor unidade elegível do mesmo caderno;
- se `inicio=1200` falhar, o encadeamento para ali até cooldown/reconcile; `inicio=0` não volta;
- se TC retorna 401/452, marca unidade e job como `blocked` por cooldown longo;
- se TC retorna 403/429, marca `blocked` por cooldown médio;
- se timeout/5xx/erro de parsing, marca a unidade como `failed`.

Regra de fechamento:

- se `expected_total` existe, **não** fechar pelo retorno parcial isolado;
- fechar somente quando todas as unidades planejadas estiverem `done`;
- retorno parcial na última unidade esperada é válido;
- retorno vazio antes da última unidade esperada é inconsistência e deve marcar
  a unidade como `failed`, não completar o job.

### 7.3 `reconciliar_jobs_tc`

```python
async def reconciliar_jobs_tc(limit: int = 100) -> dict:
    """Reenfileira unidades pendentes ou bloqueadas cujo cooldown venceu."""
```

Roda via cron externo ou scheduler simples, uma única réplica.

Não precisa Control Center para isso. É só uma task de manutenção.

### 7.4 `descobrir_imagens_pendentes`

```python
async def descobrir_imagens_pendentes(limit: int | None = None) -> dict:
    """Varre HTML/MD, cria assets por UUID e enfileira downloads pendentes."""
```

Idempotência de enqueue:

```text
tc:images:discover:{yyyy-mm-dd}
```

Efeito:

- extrai URLs únicas de `questoes` e `alternativas`;
- upsert em `tc_image_assets`;
- vincula no `tc_image_job_assets`;
- enfileira uma task por UUID pendente.

### 7.5 `baixar_imagem_tc`

```python
async def baixar_imagem_tc(uuid: str) -> dict:
    """Baixa uma imagem TC CDN e envia ao MinIO."""
```

Idempotência de enqueue:

```text
tc:image:{uuid}
```

Regras:

- se asset está `done` e objeto existe no MinIO, skip;
- 404 vira `not_found` sem retry quente;
- 5xx/timeout retry limitado;
- objeto MinIO usa chave determinística `figuras/{uuid}.{ext}`;
- resultado grava `minio_url`, `content_type`, `bytes`.

### 7.6 `reescrever_urls_imagens`

```python
async def reescrever_urls_imagens(job_id: int, batch_size: int = 500) -> dict:
    """Substitui URLs TC CDN por URLs MinIO nos textos."""
```

Idempotência de enqueue:

```text
tc:images:rewrite:{job_id}
```

Disparo:

- pelo reconciliador quando todos os assets do job estão em estado terminal;
- nunca por heurística de fila vazia.

---

## 8. Tratamento de bloqueio TC

O cap do TC não deve ser tratado como erro comum.

### 8.1 Classificação

| Resposta | Significado operacional | Ação |
|---|---|---|
| 401 | sessão inválida ou conta bloqueada naquela janela | bloquear job |
| 452 | sessão queimada/anti-bot | bloquear job |
| 403 | acesso bloqueado | bloquear unidade/job |
| 429 | rate limit | bloquear unidade/job |
| 5xx | erro transitório servidor | retry limitado |
| timeout | erro transitório rede | retry limitado |
| 404 imagem | asset inexistente | terminal `not_found` |

### 8.2 Cooldowns iniciais

| Caso | Cooldown inicial |
|---|---:|
| 401/452 em página TC | 24h |
| 403/429 em página TC | 2h |
| timeout/5xx em página TC | retry NATS, máximo 3 |
| 5xx/timeout em imagem | retry NATS, máximo 3 |

Após dois bloqueios consecutivos no mesmo caderno, sobe para 72h e marca o job
como `blocked`. Isso impede o comportamento que causou os 215k requests inúteis.

No primeiro corte, retry de timeout/5xx pode ser redelivery do JetStream por
`max_deliver`, sem scheduler exponencial. Cooldown de bloqueio TC é sempre
controlado pelo Postgres e pelo reconciliador, não pelo retry quente do worker.

### 8.3 O que significa garantir 100%

Há duas garantias diferentes:

1. **Garantia do nosso controle**: o sistema sabe exatamente quais faixas faltam
   e nunca declara caderno completo sem todas elas.
2. **Garantia de acesso ao TC**: se o TC impuser cap por conta/IP/plano, o
   sistema não consegue forçar a resposta. Ele pausa e retoma a faixa faltante
   após cooldown ou quando houver outra conta/proxy autorizado.

Portanto, o status correto para `95872884` não seria "feito com 3.360". Seria:

```text
caderno 95872884
  expected_total=15298
  total_units=77
  done_units=contado em tc_caderno_units, nao inferido por questoes_ok
  blocked_units=contado em tc_caderno_units
  status=blocked
  next_retry=inicio_da_primeira_faixa_bloqueada
```

E o status correto para `95872872` seria:

```text
caderno 95872872
  expected_total=29774
  total_units=149
  done_units=contado em tc_caderno_units, nao inferido por questoes_ok
  blocked_units=contado em tc_caderno_units
  status=blocked
  next_retry=inicio_da_primeira_faixa_bloqueada
```

O reconciliador sempre escolhe a menor faixa que não está `done`, por exemplo:

```sql
SELECT id, caderno_id, inicio, page_size
FROM tc_caderno_units
WHERE caderno_id = 95872884
  AND (
    status IN ('pending', 'failed')
    OR (status = 'blocked' AND blocked_until <= now())
  )
ORDER BY inicio
LIMIT 1;
```

Esse é o ponto que impede repetir 0-200, 200-400, 400-600 quando a falha real
está em 1200-1400.

---

## 9. DLQ básica sem Control Center

Sem painel por enquanto. A base precisa apenas de inspeção e replay manual.

Implementar:

- stream/subject `taskiq.studia.dlq`;
- script `services/scraper/scripts/taskiq_dlq_inspect.py`;
- script `services/scraper/scripts/taskiq_dlq_replay.py`;
- logs estruturados com `job_id`, `unit_id`, `task_id`, `caderno_id`, `inicio`.

Critério mínimo:

```bash
python scripts/taskiq_dlq_inspect.py --limit 20
python scripts/taskiq_dlq_replay.py --task-id <id>
```

Se a cópia do forwarder advisory-based da platform for rápida, usar esse
padrão. Se não, o primeiro corte pode usar uma DLQ explícita no próprio wrapper
da task quando falhas não retryable forem classificadas.

---

## 10. API mínima

### 10.1 Coleta de caderno

`POST /api/q/coletar`

Antes:

```text
backend -> HTTP blocking scraper /run/caderno-imprimir -> espera terminar
```

Depois:

```text
backend -> enqueue rapido -> retorna 202
```

Resposta:

```json
{
  "job_id": 123,
  "status": "pending",
  "status_url": "/api/q/jobs/123"
}
```

### 10.2 Consulta de job

`GET /api/q/jobs/{job_id}`

Resposta:

```json
{
  "id": 123,
  "kind": "caderno",
  "status": "running",
  "external_id": "95872872",
  "total_units": 149,
  "done_units": 87,
  "failed_units": 0,
  "blocked_units": 0,
  "blocked_until": null,
  "last_error": null
}
```

### 10.3 Imagens

`POST /api/q/imagens/download`

Cria job de imagens e retorna `202`.

`POST /api/q/imagens/rewrite`

Uso manual/admin para reescrever novamente se necessário.

---

## 11. Deploy inicial

### 11.1 Services

No stack do scraper/prod:

```yaml
services:
  studia-scraper-api:
    image: studia-scraper:latest
    command: python -m app.main api
    restart: unless-stopped

  studia-worker-default:
    image: studia-scraper:latest
    command: >
      taskiq worker app.tasks.brokers.studia:broker_studia_default
      --workers 1 --fs-discover --tasks-pattern 'app/tasks/**/*.py'
    restart: unless-stopped

  studia-worker-low:
    image: studia-scraper:latest
    command: >
      taskiq worker app.tasks.brokers.studia:broker_studia_low
      --workers 5 --fs-discover --tasks-pattern 'app/tasks/**/*.py'
    restart: unless-stopped

  studia-reconciler:
    image: studia-scraper:latest
    command: python -m app.tasks.reconciler
    restart: unless-stopped
    deploy:
      replicas: 1
```

Não existe mais `command: python scripts/scrape_lote.py ...` em serviço
permanente.

### 11.2 Restart policy

Usar `unless-stopped` ou `on-failure` para processos permanentes.

Não usar `restart_policy: any` para execução de lote.

### 11.3 Variáveis novas

```text
NATS_SERVERS=nats://nats:4222
TASKIQ_STUDIA_STREAM=TASKIQ_STUDIA
TASKIQ_RESULT_REDIS_URL=redis://redis:6379/2
TASKIQ_IDEMPOTENCY_REDIS_URL=redis://redis:6379/2
TC_PAGE_WORKERS=1
TC_IMAGE_WORKERS=5
TASKIQ_STUDIA_DEFAULT_PULL_BATCH=1
TASKIQ_STUDIA_DEFAULT_MAX_ACK_PENDING=1
TASKIQ_STUDIA_LOW_PULL_BATCH=16
TASKIQ_STUDIA_LOW_MAX_ACK_PENDING=64
TC_BLOCK_401_452_SECONDS=86400
TC_BLOCK_403_429_SECONDS=7200
```

---

## 12. Plano de implementação por fases

### Fase 1 - Base NATS e ledger (1-2 dias)

- [ ] adicionar dependências `taskiq-nats`, `nats-py`, Redis result backend no scraper;
- [ ] criar brokers `studia_default` e `studia_low`;
- [ ] criar facade `enqueue()` com `idempotency_key`;
- [ ] criar tabelas `tc_jobs`, `tc_caderno_units`, `tc_image_assets`, `tc_image_job_assets`;
- [ ] subir worker default e low em dev;
- [ ] smoke test: task dummy publica, consome e atualiza Postgres.

### Fase 2 - Cadernos por página/faixa (1-2 dias)

- [x] extrair `fetch_pagina` e upsert para task `coletar_pagina_caderno_tc`;
- [x] implementar planejamento/enqueue em `POST /enqueue/caderno`;
- [x] implementar unidade fixa por `(caderno_id, inicio, page_size)`;
- [x] implementar classificação 401/452/403/429 com cooldown;
- [x] garantir retry de `failed/blocked` sem criar novo job vazio;
- [ ] trocar `POST /api/q/coletar` para retornar `202 job_id`;
- [ ] manter endpoint antigo desabilitado ou protegido como fallback manual.

### Fase 3 - Imagens por UUID (1 dia)

- [ ] migrar state de imagens de SQLite para `tc_image_assets`;
- [ ] implementar `descobrir_imagens_pendentes`;
- [ ] implementar `baixar_imagem_tc`;
- [ ] implementar `reescrever_urls_imagens`;
- [ ] validar com batch limitado de 100 imagens.

### Fase 4 - DLQ e operação mínima (0.5-1 dia)

- [ ] criar DLQ básica;
- [ ] criar scripts inspect/replay;
- [ ] documentar comandos de pausa/retomada;
- [ ] atualizar `services/scraper/RUN-SSH.md`.

### Fase 5 - Cutover (0.5 dia)

- [ ] remover `scrape_lote.py` do serviço permanente;
- [ ] deixar script antigo apenas para emergência manual, sem restart automático;
- [ ] rodar smoke em produção com 1 caderno pequeno;
- [ ] rodar imagens com batch limitado;
- [ ] liberar batch completo.

---

## 13. Critérios de aceite

- `POST /api/q/coletar` retorna em menos de 1s com `job_id`.
- Reiniciar worker no meio de uma página não reinicia o caderno inteiro.
- Reenfileirar mesmo caderno não cria job ativo duplicado.
- Página já `done` não é coletada de novo.
- 401/452 pausa o caderno por cooldown, sem martelar TC.
- Imagem já `done` não é baixada de novo.
- Rewrite de imagens dispara por estado do job, não por fila vazia.
- Não há serviço Docker cujo comando principal seja `scrape_lote.py`.
- DLQ pode ser inspecionada por script.

---

## 14. Resposta operacional para agora

Não disparar `download_imagens.py` como job monolítico se o objetivo é corrigir
a base.

Opção aceitável apenas se houver urgência de produto:

```text
rodar manualmente, sem restart automático, com dry-run antes e log acompanhado
```

Mas a recomendação desta spec é:

1. manter scraper atual idle;
2. implementar Fase 1 e Fase 3 mínima;
3. baixar imagens pela fila NATS, uma task por UUID;
4. só depois fazer rewrite em batch controlado.

---

## 15. Decisões travadas

| # | Decisão | Motivo |
|---|---|---|
| 1 | Base primeiro, sem Control Center | Reduz escopo e entrega controle real rápido |
| 2 | `services/scraper` é worker NATS inicial | Já tem Playwright, proxy e código TC |
| 3 | Caderno vira job; página/faixa vira task | Retomada granular e controle de cap |
| 4 | TC começa com concorrência 1 | Evita anti-bot e respeita padrão humano |
| 5 | Imagem vira task por UUID | Paralelismo seguro e idempotente |
| 6 | Estado operacional em Postgres | Sobrevive a redeploy e não depende de volume local |
| 7 | Cooldown para 401/452/403/429 | Evita loop de requests inúteis |
| 8 | Rewrite depende do ledger, não da fila vazia | Evita race com outras tasks low |
| 9 | Redis broker legado não entra nesta migração | Escopo separado do `backend/worker.py` |

---

## 16. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| TC continuar bloqueando páginas profundas | Job fica `blocked` com `blocked_until`; não martela |
| Worker morrer durante upsert parcial | Upsert é idempotente; unidade volta a rodar e fecha estado |
| Duplicata de enqueue | Redis `idempotency_key` + unique constraints no Postgres |
| Imagem com extensão desconhecida | Detectar por `content-type`; se ausente, usar objeto sem extensão |
| MinIO com objeto já existente | `stat_object`/PUT idempotente antes de marcar `done` |
| Reconciler duplicado | Deploy com 1 réplica e lock Postgres advisory |

---

## 17. Próximo passo

Gerar um plano de implementação da Fase 1 com arquivos exatos e testes de
smoke. Depois implementar Fase 1 antes de tocar no download completo de imagens.
