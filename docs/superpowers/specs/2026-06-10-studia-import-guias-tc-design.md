# studIA — Importação de Guias TecConcursos (cascata guia → pasta → cadernos → questões)

**Status**: Design aprovada para implementação
**Owner**: Wital
**Data**: 2026-06-10
**Specs relacionadas**: [2026-06-08-studia-taskiq-nats-migration-design.md](2026-06-08-studia-taskiq-nats-migration-design.md)

---

## 1. Objetivo

Importar um **Guia de estudos** do TecConcursos ponta a ponta, recebendo apenas
a **URL base do guia** (ex.: `https://www.tecconcursos.com.br/guias/oab-2026`).

O sistema deve, em cascata:

1. resolver a URL do guia → `guiaId` do TC;
2. listar os cadernos-guia (disciplinas) do guia;
3. "salvar todos" os cadernos do guia (cria a pasta no TC) — ou reutilizar a
   pasta já salva;
4. para cada caderno da pasta, coletar as questões (via fluxo `/imprimir` já
   existente) e registrar **quais questões pertencem a cada caderno**;
5. materializar no studIA um `CadernoQuestoes` por caderno do TC, **com o mesmo
   nome** e contendo exatamente os `question_ids` daquele caderno;
6. exibir tudo numa UI **inspirada no TC** (`/q/guias`), com auditoria de
   progresso ponta a ponta (guia → cadernos → questões coletadas).

Meta secundária: permitir importar os **16 guias da OAB** começando pelo 46º Exame.

---

## 2. O que já existe (reuso)

- **Coleta de caderno** por faixas com ledger Postgres + TaskIQ/NATS
  (`tc_jobs`, `tc_caderno_units`, `coletar_pagina_caderno_tc`,
  `POST /enqueue/caderno`, `queue-supervisor`). Idempotente, com cooldown
  anti-bloqueio. **Reusado sem alteração de semântica.**
- **Upsert de questões** global por `id_externo` (`upsert_questao`). Questões são
  compartilhadas entre cadernos (armazenadas 1×).
- **CadernoQuestoes** (studIA): `id, nome, pasta, filtros, question_ids[], total`.
  Já alimenta `/q/caderno/{id}` (estudo). **Reusado como destino final.**
- **Sessão TC autenticada** (`storage_state.json`, `TcClient`, proxy residencial).
- **API TC do guia/pasta** descoberta (ver memória `tc-guia-pasta-api`):
  - `GET /guias/{slug}/{cargo}/-/-` (HTML) → `var jsonGuiaId`;
  - `GET /api/caderno-guia/listar-pelo-guia/{guiaId}`;
  - `POST /api/caderno-guia/salvar-todos-cadernos-do-guia/{guiaId}` → `{pastaCadernosQuestoes:{id}}`;
  - `GET /api/pastas-cadernos/{pastaId}/itens?...&pagina=N&paginar=true`.

---

## 3. Lacuna principal: membership questão ↔ caderno TC

Hoje a coleta persiste questões globalmente mas **não registra a que caderno do
TC cada questão pertence**. Para materializar um `CadernoQuestoes` com os
`question_ids` corretos e na ordem certa, precisamos capturar essa associação
durante o scraping.

**Solução**: tabela de membership preenchida pela task de coleta, na mesma
transação do upsert da página.

```sql
CREATE TABLE IF NOT EXISTS tc_caderno_questoes (
  caderno_id    BIGINT  NOT NULL,   -- id do caderno no TC (ex.: 96081460)
  questao_id    BIGINT  NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
  posicao       INTEGER NOT NULL,   -- 1-based, ordem dentro do caderno
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (caderno_id, questao_id)
);
CREATE INDEX IF NOT EXISTS idx_tc_caderno_questoes_caderno
  ON tc_caderno_questoes (caderno_id, posicao);
```

`posicao = inicio + offset_na_pagina + 1`. Upsert idempotente
(`ON CONFLICT (caderno_id, questao_id) DO UPDATE SET posicao = EXCLUDED.posicao`).
Como a coleta é UPSERT e re-rodável, a membership também é idempotente.

A task `execute_caderno_page_unit` já conhece `inicio`, a ordem das questões na
página e os `persisted_pks`. Passamos o `caderno_id` + offset e gravamos a
membership junto do `mark_caderno_unit_done`.

---

## 4. Modelo de dados do Guia (control-plane, no `backend`)

Tabelas no Postgres studIA, criadas via `migrate.py` (models SQLAlchemy):

```python
class Guia(Base):              # um guia importado
    id            int PK
    tc_guia_id    int  UNIQUE        # jsonGuiaId (6818)
    slug          str                # "oab-2026/nacional-unificado-oab"
    url           str                # URL base informada
    nome          str                # "OAB / 2026 — Nacional Unificado"
    banca         str | None         # "FGV"
    tc_pasta_id   int | None         # pasta criada por "salvar todos"
    status        str  = "pending"   # pending|resolving|saving|collecting|done|error
    total_cadernos int = 0
    created_at, updated_at

class GuiaCaderno(Base):       # um caderno-disciplina dentro do guia
    id              int PK
    guia_id         int FK Guia
    tc_caderno_id   int                # cadernoQuestaoRecenteId (96081460)
    tc_caderno_base int | None         # cadernoBaseId
    nome            str                # "Direito Administrativo - OAB 2026 - 46º Exame"
    disciplina      str
    total_questoes  int                # esperado (1804)
    ordem           int | None
    caderno_id      int | None FK CadernoQuestoes   # destino materializado no studIA
    status          str = "pending"    # pending|collecting|materialized|error
    UNIQUE (guia_id, tc_caderno_id)
```

`Guia.status` e `GuiaCaderno.status` são derivados/atualizados pela auditoria
(seção 7), que cruza com `tc_jobs`/`tc_caderno_units` e `tc_caderno_questoes`.

`CadernoQuestoes` ganha uma coluna nova opcional `tc_caderno_id` (int, index)
para idempotência da materialização (reusa a mesma linha em re-import).

---

## 5. Camada scraper (control-plane TC fica em `services/scraper`)

Mantém o padrão atual: o `backend` chama o scraper por HTTP curto; o scraper
fala com o TC e o Postgres.

### 5.1 Resolver guia por URL

`GET /guia/resolver?url=<url-base>` → resolve em cascata:

1. baixa HTML da URL; se for a base (`/guias/{slug}` sem `jsonGuiaId`), acha o
   link `/guias/{slug}/{cargo}/-/-` e segue;
2. extrai `jsonGuiaId` via regex;
3. extrai `nome`/`banca` do HTML (título/cabeçalho);
4. `GET /api/caderno-guia/listar-pelo-guia/{guiaId}`;
5. retorna `{tc_guia_id, nome, banca, cadernos:[{tc_caderno_id, caderno_base,
   nome, total_questoes, ordem, usuario_possui_salvo}]}`.

Novo módulo `app/scrapers/tc_guia.py` (funções puras `resolver_guia`,
`listar_cadernos_guia`, `salvar_todos_cadernos`, `listar_itens_pasta`).

### 5.2 Salvar todos os cadernos do guia

`POST /guia/salvar-cadernos` body `{tc_guia_id}` →
`POST /api/caderno-guia/salvar-todos-cadernos-do-guia/{tc_guia_id}` →
retorna `{pasta_id, itens:[...]}` (lê os itens paginando a pasta). Idempotente:
se já salvo, o TC só confirma; lemos a pasta do mesmo jeito.

### 5.3 Coleta com membership

`coletar_pagina_caderno_tc` passa a gravar `tc_caderno_questoes` na transação de
`mark_caderno_unit_done`, com `posicao = inicio + idx + 1`. Sem mudar a
semântica de faixas/cooldown.

---

## 6. Endpoints backend (`/api/q/guias/*`)

| Endpoint | Efeito |
|---|---|
| `POST /api/q/guias/importar` `{url}` | Resolve guia (chama scraper), faz upsert `Guia`+`GuiaCaderno`, dispara "salvar todos" e enfileira coleta de **todos** os cadernos (1 `enqueue/caderno` por caderno). Retorna `202` com `guia_id` + resumo. |
| `GET /api/q/guias` | Lista guias importados (cards estilo TC). |
| `GET /api/q/guias/{id}` | Detalhe do guia: cadernos + progresso de coleta (cruza `tc_jobs`/units/membership) + status de materialização. |
| `POST /api/q/guias/{id}/materializar` | Para cada caderno com coleta concluída, cria/atualiza `CadernoQuestoes` (mesmo nome, `question_ids` da membership ordenada). Idempotente por `tc_caderno_id`. |
| `GET /api/q/guias/{id}/auditoria` | Relatório ponta a ponta: esperado vs coletado vs materializado por caderno. |

A coleta dos cadernos do guia reusa **100%** o pipeline existente
(`enqueue/caderno` → `coletar_pagina_caderno_tc` → ledger → supervisor). O guia
apenas orquestra N cadernos e amarra os resultados.

A materialização pode rodar incrementalmente: cada caderno vira `CadernoQuestoes`
assim que sua coleta fecha (status `done` no `tc_jobs`), sem esperar o guia todo.

---

## 7. Auditoria ponta a ponta

Para cada `GuiaCaderno`, a auditoria cruza:

- **esperado**: `total_questoes` (do TC);
- **coletado**: `COUNT(*) FROM tc_caderno_questoes WHERE caderno_id = tc_caderno_id`;
- **ledger**: `tc_jobs.status` + `done_units/total_units` do `external_id = tc_caderno_id`;
- **materializado**: `CadernoQuestoes.total` quando `caderno_id` setado.

Status derivado do caderno:
`pending` → `collecting` (job running/blocked) → `collected` (coletado ≈ esperado)
→ `materialized` (CadernoQuestoes criado). Divergência coletado≪esperado =
sinalizada em vermelho (faixa bloqueada/cooldown).

Guia: `done` somente quando todos os cadernos estão `materialized`.

---

## 8. Frontend `/q/guias` (inspirado no TC)

- **`/q/guias`** — grid de cards estilo "Guias de Estudos" do TC (logo, nome,
  banca, nº de cadernos, barra de progresso global). Campo "Importar guia por
  URL" no topo. Botão por card → detalhe.
- **`/q/guias/[id]`** — cabeçalho do guia (estilo página de guia do TC:
  banca, data, total de questões) + lista "Cadernos por matéria" com, por
  caderno: nome, nº questões esperadas, **coletadas/esperadas**, status
  (Coletando / Em cooldown / Coletado / Materializado), e link para o
  `CadernoQuestoes` quando materializado. Botão "Salvar/Importar tudo" e
  "Materializar concluídos". Polling a cada 15s (igual `/q/coletar`).
- Reusa paleta/estética dark já existente; semântica de status alinhada ao TC
  ("Você já possui este caderno", "Coletado", contadores).
- Item no `Sidebar`: "Guias" (`/q/guias`, ícone `menu_book`).

---

## 9. Plano de implementação (fases)

1. **Scraper — descoberta do guia** (`tc_guia.py` + endpoints `/guia/resolver`,
   `/guia/salvar-cadernos`). Testável isolado contra o TC.
2. **Membership** — `tc_caderno_questoes` DDL no ledger + gravação em
   `coletar_pagina_caderno_tc`. Teste de execução de unidade já existe; estender.
3. **Backend modelos** — `Guia`, `GuiaCaderno`, coluna `tc_caderno_id` em
   `CadernoQuestoes`. `migrate.py` cria.
4. **Backend endpoints** — `/api/q/guias/*` (importar, listar, detalhe,
   materializar, auditoria). Testes com scraper fake (padrão `test_q_coletar_enqueue`).
5. **Frontend** — `/q/guias` + `/q/guias/[id]` + item no Sidebar.
6. **Import real OAB 46** — rodar ponta a ponta, auditar.

---

## 10. Invariantes / decisões travadas

| # | Decisão | Motivo |
|---|---|---|
| 1 | Guia só orquestra; coleta reusa pipeline de caderno existente | Não duplica anti-bot/cooldown/ledger |
| 2 | Membership `tc_caderno_questoes` é a fonte para `question_ids` | Permite materializar com nome+ordem corretos |
| 3 | Materialização idempotente por `CadernoQuestoes.tc_caderno_id` | Re-import não duplica cadernos |
| 4 | "Salvar todos" no TC reaproveita pasta já salva | Idempotente; não recria pasta |
| 5 | Coleta serial respeitando `max_ack_pending=1` | Mantém regra anti-bloqueio TC |
| 6 | UI faz polling, não acompanha task em tempo real | Igual `/q/coletar`; estado vive no Postgres |
| 7 | Resolver aceita URL base OU URL de cargo do guia | UX: usuário cola o que tiver |

---

## 10.1 Ajustes na implementação (as-built)

- **Fonte autoritativa dos cadernos**: `listar-pelo-guia` só traz o id do caderno
  de questões (`cadernoQuestaoRecenteId`) quando o usuário **já tinha salvo** o
  guia. Para guias novos, o id vem dos **itens da pasta** criada por "salvar
  todos" (`/api/pastas-cadernos/{pasta}/itens`, campo `id` + `quantidadeItens`).
  Por isso o import faz `resolver → salvar-todos → merge(itens_pasta, cadernos_guia)`
  (`_merge_cadernos`): a pasta dá id/nome/total; o guia enriquece capítulos/ordem.
- **Busca de guias**: `GET /api/guias/busca?busca={termo}&pagina={n}` retorna
  `list[].editalUrl` (slug do guia). Exposto como scraper `GET /guia/buscar` e
  backend `GET /api/q/guias/buscar-tc?termo=`, marcando quais já foram importados
  (match por prefixo do slug). A UI `/q/guias` busca e importa com um clique —
  os 16 guias da OAB aparecem para importar em lote.
- **Ordem de registro dos routers**: `guias_router` é incluído ANTES de `q_router`
  no `backend/main.py`, senão `/api/q/guias` cai no catch-all `/api/q/{questao_id}`.

## 11. Critérios de aceite

- Colar `https://www.tecconcursos.com.br/guias/oab-2026` cria um `Guia` com os 20
  cadernos do 46º Exame e dispara a coleta de todos.
- Cada caderno coletado materializa um `CadernoQuestoes` com **o mesmo nome** do
  TC e `total` ≈ `total_questoes` esperado.
- `/q/guias/[id]` mostra progresso por caderno (coletadas/esperadas) e link para
  o caderno de estudo quando materializado.
- Re-importar o mesmo guia não duplica `Guia`, `GuiaCaderno` nem `CadernoQuestoes`.
- Auditoria lista divergências (cadernos com faixa bloqueada/incompleta).
- Coleta nunca quebra a regra serial/cooldown do TC.
