# Fila serial de coleta de guias (batch import + cooldown)

**Data:** 2026-06-27
**Status:** aprovado (design)
**Escopo:** importar vários guias do TecConcursos de uma vez e garantir que a coleta
ocorra **1 guia por vez**, com **pausa mínima de 15 min entre guias**, valendo igual
para "colar todas as URLs de uma vez" e "colar uma de cada vez".

## Problema

Hoje (`/api/q/guias/importar` com `iniciar_coleta=true`) o backend enfileira **todos os
cadernos de todos os guias imediatamente**. O worker do scraper processa em série no
nível de *unidade* (faixa de 200 questões, `max_ack_pending=1`), mas:

- os guias **se intercalam** (caderno do guia A, depois do guia B, etc.);
- **não há pausa entre guias** para "esfriar" o tráfego contra o TC.

A garantia desejada — 1 guia por vez + 15 min de cooldown — **não existe**.

## Decisões (confirmadas com o usuário)

1. **Cooldown** = medido **entre** guias. O 1º guia da fila começa imediatamente;
   após cada guia terminar toda a coleta, espera `GUIA_COOLDOWN_SECONDS` (padrão 900s)
   antes de iniciar o próximo. Configurável por env.
2. **Resolver/salvar no TC** = **preguiçoso**: enviar a lista é instantâneo; cada guia
   só é resolvido (`/guia/resolver`) e salvo (`/guia/salvar-cadernos`) quando chega a
   vez dele de coletar — assim **todo** o tráfego no TC (inclusive os "salvar") fica
   espaçado.
3. **Guia travado** = **auto-pula após `GUIA_MAX_COLETA_SECONDS` (padrão 6h)**: marca a
   entrada como `skipped` (preserva o parcial já coletado) e a fila segue sozinha. Há
   também botão manual de "Pular".

## Arquitetura

A coleta de unidades **já é serial** no NATS (`max_ack_pending=1` no
`studia-scraper-worker-default`). A novidade é uma camada **acima**, no domínio do
studIA (que é quem conhece o conceito de "guia"): uma **fila FIFO de guias** e um
**supervisor** que só libera os cadernos do próximo guia depois que os do anterior
terminam. Durante o cooldown **não há job ativo** no scraper → o TC esfria de fato.

O scraper permanece genérico (coleta cadernos; não conhece guias).

### Invariantes garantidas pelo supervisor

- No máximo **1 entrada ativa** (`resolving` ou `collecting`) por vez.
- 1º guia inicia na hora; **≥ cooldown** entre o `finalizado_em` de um guia e o início
  do próximo.
- Independe de o admin colar N URLs juntas ou uma a uma (tudo entra na mesma fila).

## Dados — nova tabela `guia_fila` (model `GuiaFila`)

Uma linha por guia-a-coletar, em ordem de chegada. **Não altera a tabela `guias`** (a
"coleta completa" continua derivada como hoje; o cooldown vive em `guia_fila`).

| campo | tipo | uso |
|---|---|---|
| `id` | PK int | define a ordem FIFO (`ORDER BY id`) |
| `url` | str(512) | URL colada do guia (pode ser NULL em re-coleta com `guia_id`) |
| `status` | str(32) | `queued` → `resolving` → `collecting` → `done`/`skipped`/`error` |
| `guia_id` | FK `guias.id` nullable | preenchido após resolver (ou já na re-coleta) |
| `iniciado_em` | datetime nullable | quando virou ativo (mede o teto de 6h) |
| `finalizado_em` | datetime nullable | quando terminou — **referência do cooldown** (`MAX(finalizado_em)`) |
| `tentativas` | int default 0 | tentativas de resolver |
| `erro` | text nullable | última falha / motivo do skip |
| `requested_by` | str nullable | uid do admin que enfileirou |
| `created_at`, `updated_at` | datetime | padrão do projeto |

Índice em `status` (para varrer ativos/queued rápido).

### Migração

Revisão Alembic nova com `down_revision = 'd9f0a1b2c3e4'` (head atual,
`questao_tc_import`). `scripts/db_prepare.py` roda `alembic upgrade head` no startup do
backend, então o deploy aplica a tabela sozinho.

## Supervisor de guias (serviço novo `studia-guia-supervisor`)

CLI loop na **imagem do backend** (espelha o `studia-scraper-supervisor` que já existe),
ex.: `python -m scripts.guia_supervisor`, `replicas: 1`, intervalo
`GUIA_SUPERVISOR_INTERVAL` (padrão 30s).

### Lógica de cada tick — `guia_supervisor_tick(db, *, now, cfg, deps)`

Extraída para uma função **pura/injetável** (deps = cliente scraper + checador de
conclusão), para ser testável sem HTTP nem loop.

1. **Existe entrada ativa?** (`status in {resolving, collecting}`)
   - `collecting`: recalcula conclusão do guia (reusa `_jobs_por_caderno` +
     `_coletado_por_caderno`).
     - terminou → `status=done`, `finalizado_em=now` (dispara cooldown).
     - `now - iniciado_em > GUIA_MAX_COLETA_SECONDS` → `status=skipped`,
       `erro="timeout (parcial)"`, `finalizado_em=now`; segue.
     - senão → não faz nada (1 por vez).
   - `resolving` antigo (travado por crash): se `iniciado_em` muito velho, volta a
     `queued` (re-tenta) ou `error` se estourou tentativas.
2. **Nenhuma ativa?**
   - **Cooldown**: se `now - MAX(finalizado_em) < GUIA_COOLDOWN_SECONDS` → espera (loga
     "próximo em N min"). Sem `finalizado_em` (fila nova) → não espera.
   - Senão pega o próximo `queued` (menor `id`):
     - marca `resolving`, `iniciado_em=now`.
     - se `guia_id` vazio: chama `guia_service.resolver_e_salvar(url)` (lógica de hoje
       extraída de `importar_guia`: `/guia/resolver` + upsert `Guia`/`GuiaCaderno` +
       `/guia/salvar-cadernos` + merge). Liga `entry.guia_id`.
     - enfileira os cadernos do guia (`_enqueue_caderno` por caderno), `guia.status =
       'collecting'`, `entry.status = 'collecting'`.
     - falha ao resolver → `tentativas++`; `< GUIA_RESOLVE_MAX_TENTATIVAS` (3) volta a
       `queued`; senão `error` + `finalizado_em=now` (mantém o espaçamento mesmo em
       falha).

O supervisor é **o único** ponto que enfileira coleta de guia daqui pra frente.

## Endpoints (`backend/guias_router.py`)

- **`POST /api/q/guias/importar-lote`** (novo, admin): body `{ urls: string[] }`. Valida
  e normaliza (trim, dedup, descarta vazias), cria N entradas `queued`, retorna na hora.
- **`POST /api/q/guias/importar`** (alterado): com coleta → empurra 1 URL pra fila e
  retorna; `apenas_catalogar=true` → mantém o resolve+save imediato de hoje **sem**
  enfileirar coleta (`Guia.status='pending'`). (O campo `iniciar_coleta` é substituído
  por `apenas_catalogar`, default `false`.)
- **`POST /api/q/guias/{id}/coletar`** (alterado, "Retomar"): em vez de enfileirar
  direto, cria entrada na fila já com `guia_id` (supervisor pula o resolve, vai direto
  ao enqueue). Idempotente: não duplica se já houver entrada ativa/queued para o guia.
- **`GET /api/q/guias/fila`** (novo): lista a fila ordenada + `proximo_em_segundos`
  (countdown do cooldown; 0 se nada esperando). Cada item: `id`, `status`, `url`,
  `guia_id`, `guia_nome`, `posicao` (1-based entre os `queued`), progresso quando
  `collecting`.
- **`DELETE /api/q/guias/fila/{id}`** (admin): remove uma entrada `queued`.
- **`POST /api/q/guias/fila/{id}/pular`** (admin): pula a entrada ativa (`skipped` +
  `finalizado_em=now`) para liberar a fila manualmente.

**Fora de escopo:** o coletor avulso de 1 caderno (`/api/q/coletar`, `q_router.py`)
permanece como ferramenta manual. Continua não rodando 2 lotes simultâneos (graças ao
`max_ack_pending=1`), mas **não respeita** o cooldown de 15 min — comportamento aceito.

## Frontend (`fontend/app/q/coletar/GuiasPanel.tsx`)

- Input de URL único → **textarea** "Cole uma ou mais URLs (uma por linha)" + botão
  **"Adicionar à fila de coleta"** chamando `importar-lote`. O checkbox vira **"Apenas
  catalogar (não coletar agora)"**, default desligado.
- Nova seção **"Fila de coleta"** (acima de "Guias importados"): entradas em ordem com
  badge (`coletando` + nome/`%` do guia, link p/ `/q/guias/{id}` · `na fila #N` ·
  `concluído`/`pulado`/`erro`), indicador **"Esfriando — próximo guia em ~12 min"** com
  contagem regressiva (de `proximo_em_segundos`), e botões **Remover** (queued) /
  **Pular** (ativo). Poll de 15s via React Query enquanto houver entrada não-terminal.
  Query key nova em `lib/queryKeys.ts` (`qk.guiaFila()`).
- "GUIAS IMPORTADOS" permanece igual.

## Config (env)

| env | padrão | uso |
|---|---|---|
| `GUIA_COOLDOWN_SECONDS` | `900` | pausa entre guias |
| `GUIA_SUPERVISOR_INTERVAL` | `30` | segundos entre ticks |
| `GUIA_MAX_COLETA_SECONDS` | `21600` | teto p/ auto-skip (6h) |
| `GUIA_RESOLVE_MAX_TENTATIVAS` | `3` | tentativas de resolver antes de `error` |

## Deploy

- Novo serviço `studia-guia-supervisor` em `docker/stack.yml` (imagem do backend,
  `command: python -m scripts.guia_supervisor`, `replicas: 1`, mesma rede/env do
  `worker` + as envs acima) e no `docker-compose.dev.yml`.
- `build.sh` já faz `docker stack deploy`; nada novo no fluxo.

## Testes

- **Unit do tick** (`guia_supervisor_tick`) com `TEST_DATABASE_URL` (sqlite) e deps
  fakes (scraper + checador de conclusão):
  - 1º guia inicia imediatamente (sem `finalizado_em`);
  - **não** pega novo enquanto há `collecting`;
  - respeita cooldown (não inicia antes de `GUIA_COOLDOWN_SECONDS`);
  - inicia o próximo assim que o cooldown expira;
  - auto-skip após `GUIA_MAX_COLETA_SECONDS`;
  - falha de resolver → re-tenta e vira `error` após N tentativas.
- **Endpoints**: `importar-lote` cria N entradas e normaliza/dedup; `GET /fila`
  (formato + `proximo_em_segundos`); `DELETE`/`pular` mudam estado.

## Rollout / transição

Coletas já em andamento (importadas antes desta feature) seguem como hoje até terminar;
a fila governa as **novas** importações. (Opcional, fora do escopo base: supervisor
"adotar" guias atualmente em coleta para dentro da fila.)

## Fora de escopo (YAGNI)

- Reordenar a fila por drag-and-drop (basta remover/re-adicionar).
- Prioridades/pesos entre guias.
- Cooldown por banca/domínio TC (só global).
- Adoção automática de coletas legadas em andamento.
