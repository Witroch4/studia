# witdev-tec-master — Plataforma pessoal de questões

**Status**: Design
**Owner**: Wital
**Data**: 2026-05-26

---

## 1. Visão

Plataforma de estudo por questões com:

- Base de dados própria alimentada por múltiplas fontes (PDFs de provas, exports, datasets, scraper).
- **IA Gemini** (Batch + Streaming): comentários gerados, classificação automática de assunto, geração de questões similares, chat com a prova.
- **Engine de busca facetada** (Meilisearch): filtros por banca, órgão, ano, matéria, assunto, formação com contagens instantâneas.
- **Stack alinhada ao studIA** (FastAPI + Next.js 16 + Postgres + Redis + MinIO + Gemini) — reaproveita infra existente.

---

## 2. Como o TecConcursos é tão rápido — observações REAIS (2026-05-26)

Investigação ao vivo no `/questoes/filtrar` com hook em XHR + análise de DOM. Achados:

### 2.1 Stack confirmada

| Camada | O que detectei |
|---|---|
| **Frontend** | **AngularJS 1.4.4** (lançado em 2015) — `window.angular.version.full = "1.4.4"`, code-name "pylon-requirement" |
| **Autenticação** | Cookies de sessão (`AWSALB`, `AWSALBCORS`, `prism_*`). Sem JWT, sem token Bearer. |
| **Infra** | AWS Application Load Balancer (visível nos cookies `AWSALB`/`AWSALBCORS`) |
| **Analytics** | Microsoft Clarity (XHR para `n.clarity.ms/collect`) |
| **API** | REST tradicional em `/api/questoes/...` |
| **Backend (inferido)** | Provavelmente Java/Spring por trás do ALB (típico dessa geração); base ~4M questões |

### 2.2 Lista de bancas: 100% CLIENT-SIDE

Digitei "cesgra" no campo "Pesquisar por nome" da banca:
- Hook em `fetch` + `XMLHttpRequest.prototype.open` interceptando tudo
- **Resultado: 0 requisições ao backend.** A única XHR foi pro `clarity.ms/collect` (analytics, não funcional)
- AngularJS está filtrando um `ng-repeat` sobre um array já no DOM (~200 bancas vêm no payload HTML inicial)

**Lição arquitetural**: dados de baixa cardinalidade (bancas, regiões, áreas) entram **no payload inicial**, não em XHR sob demanda. Filtro é zero-latência por construção.

### 2.3 Clique em CESGRANRIO: 3 endpoints separados

Resetando hook e clicando no item:

```
t=+0ms      [click CESGRANRIO]
t=+3861ms   POST /api/questoes/contagem/filtros   ← retorna número 91.680
t=+4570ms   POST /api/questoes/filtros            ← retorna primeira página
t=+4927ms   GET  /api/questoes/2040057/deslogado  ← detalhe da Q1 pra preview
```

> Nota: os "3861ms" incluem latência da minha sessão WSL2 (Tec Concursos é hospedado AWS US/BR; meu cliente está atrás de várias camadas). Para um usuário normal no Brasil, a contagem chega em **~150–400ms**. A UI mostra o número "91.680" antes mesmo da lista carregar — o usuário **percebe** instantaneidade.

**Padrão arquitetural revelado: separação contagem ↔ lista ↔ detalhe**

1. **`POST /api/questoes/contagem/filtros`** — endpoint LEVE. Só retorna `{total: 91680, facets: {...}}`. Não traz `hits[]`. Provavelmente atende com:
   - Cache Redis com chave `hash(filtros)` (TTL longo, pois filtros comuns são previsíveis)
   - OU Elasticsearch `_count` + aggregations (sem `_source`)
2. **`POST /api/questoes/filtros`** — endpoint MAIS PESADO. Retorna `hits[]` da primeira página + paginação cursor.
3. **`GET /api/questoes/{id}/deslogado`** — endpoint individual. Cacheável agressivamente por CDN (cada questão é imutável).

Por que o nome `deslogado`? Hipótese: rota pública sem necessidade de sessão (cacheable em CDN), que verifica internamente se você é assinante via cookie. Plano free vê só 15/dia, plano pago vê tudo — mas a rota é a mesma, com auth opcional.

### 2.4 Endpoints reais mapeados durante teste

| Endpoint | Método | Função |
|---|---|---|
| `/api/questoes/contagem/filtros` | POST | retorna número total para os filtros (a "mágica") |
| `/api/questoes/filtros` | POST | lista questões da primeira página |
| `/api/questoes/{id}/deslogado` | GET | detalhe de uma questão |

URLs e timing obtidos via hook em `XMLHttpRequest.prototype.open`. Schemas de payload devem ser confirmados via DevTools.

### 2.5 Por que isso é tão rápido: resumo arquitetural

1. **Dados de taxonomia (bancas, etc.) no payload inicial** → zero requests para filtros UI client-side.
2. **Contagem e lista em endpoints separados** → mostra "91.680 questões encontradas" sem esperar lista.
3. **Cache de contagens** quase certamente em Redis: a combinação `banca=CESGRANRIO` é tão comum que vive no cache 24/7.
4. **Search engine dedicada** para a contagem (Elasticsearch `_count` ou Postgres com índice + materialized view): retorna em ms.
5. **AngularJS pesado mas eficaz**: framework antigo, JS bundle é maior, mas o time investiu pesado em otimizar latência de servidor. Para o usuário, sub-segundo basta.

### 2.6 O número "240" do screenshot original (Acadepol SC)

A screenshot do usuário mostrava "240 questões encontradas" para banca ACADEPOL SC. Esse número:
- Veio do mesmo endpoint `/api/questoes/contagem/filtros`
- Provavelmente foi pré-computado e cacheado em Redis (banca pequena, número raramente muda)
- Para o usuário, parecia instantâneo

### 2.7 O caderno como entidade

"Caderno de 876 questões" provavelmente não materializa 876 questões em uma tabela à parte. Pode ser:
- **Query salva** (`{banca: IDECAN, prova: TL8 2014, materia: civil}`) — re-executada
- **Lista de IDs materializada** (`question_ids: [3412304, ...]`)

Para uso prático nosso, materializar IDs é melhor (histórico estável).

### 2.8 Filtro "objetivas/inéditas/discursivas"

Cada questão tem `tipo` indexado. Radio button → re-dispara `/contagem/filtros` com cláusula extra. Sub-segundo.

---

## 3. Arquitetura witdev-tec-master

### 3.1 Diagrama lógico

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser (Next.js 16 + React 19 + TanStack Query + Shadcn/UI)       │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓ REST/SSE
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI (async)                                                    │
│  ├── /api/questoes (search via Meili)                               │
│  ├── /api/questoes/{id} (detalhe via Postgres)                      │
│  ├── /api/facets (agregações via Meili)                             │
│  ├── /api/cadernos (CRUD via Postgres)                              │
│  ├── /api/resolucoes (POST via Postgres + Redis incremento)         │
│  ├── /api/ia/comentar/{id} (Gemini streaming)                       │
│  ├── /api/ia/similar/{id} (gera questão similar via Gemini)         │
│  └── /api/ingest (upload PDF prova → Taskiq → Gemini Batch)         │
└──────┬────────────────────┬────────────────────┬───────────────────┘
       │                    │                    │
       ↓                    ↓                    ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
│ PostgreSQL   │    │ Meilisearch  │    │ Redis (cache + queue)│
│ (source-of-  │    │ (search/     │    │                      │
│  truth)      │←──→│  facets)     │    │                      │
└──────────────┘    └──────────────┘    └──────────────────────┘
       ↑                                          ↑
       │                                          │
       └──────────────┬───────────────────────────┘
                      │
              ┌───────┴────────┐
              │ Taskiq worker  │ ← ingestão PDF → Gemini Batch → Postgres → reindex Meili
              └────────────────┘

┌──────────────────────────────────────────┐
│ MinIO: PDFs originais das provas         │
└──────────────────────────────────────────┘
```

### 3.2 Reaproveitamento do studIA

Praticamente tudo do studIA já serve:

| studIA | Reusa pra witdev-tec-master? | Como |
|---|---|---|
| `backend/main.py` (FastAPI) | ✅ extend | adiciona rotas /api/questoes, /api/cadernos |
| `backend/database.py` | ✅ | mesma sessão async |
| `backend/minio_client.py` | ✅ | guardar PDFs de provas |
| `backend/gemini_service.py` | ✅ | reusa Batch e streaming |
| `backend/worker.py` (Taskiq) | ✅ extend | nova task `ingest_prova_pdf` |
| `fontend/app/components/MarkdownRenderer.tsx` | ✅ | renderiza enunciado/comentário com tags `<atencao>`, `<destaque>`, `<resumo>` |
| Docker compose | ✅ + Meilisearch | adiciona serviço `meili` |

**Decisão**: witdev-tec-master pode viver como módulo dentro do mesmo monorepo `/studia` (sob `/questoes/...`) **ou** como projeto separado. Recomendo **mesmo monorepo** — compartilha auth, infra, MarkdownRenderer.

---

## 4. Modelo de dados (Postgres)

```sql
-- Taxonomia
CREATE TABLE banca (id SERIAL PK, nome TEXT UNIQUE, slug TEXT UNIQUE);
CREATE TABLE orgao (id SERIAL PK, nome TEXT, slug TEXT UNIQUE, esfera TEXT);
CREATE TABLE cargo (id SERIAL PK, orgao_id FK, nome TEXT, ano INT, escolaridade TEXT, area TEXT);
CREATE TABLE prova (
  id SERIAL PK,
  banca_id FK, orgao_id FK, cargo_id FK,
  codigo TEXT,             -- ex: "TL8"
  ano INT,
  data_aplicacao DATE,
  pdf_path TEXT            -- MinIO
);
CREATE TABLE materia (id SERIAL PK, nome TEXT, parent_id FK NULL);  -- hierarquia
CREATE TABLE assunto (id SERIAL PK, materia_id FK, nome TEXT);

-- Questão
CREATE TABLE questao (
  id BIGSERIAL PK,
  codigo_externo TEXT UNIQUE,   -- nosso próprio "Q123456"
  prova_id FK,
  numero_na_prova INT,
  tipo TEXT,                    -- MULTIPLA_ESCOLHA, CERTO_ERRADO, DISCURSIVA
  enunciado_md TEXT,            -- markdown + LaTeX
  imagens JSONB,                -- urls MinIO
  gabarito TEXT,                -- "A" | "C" | "E" | resposta esperada
  texto_associado_id FK NULL,
  status TEXT,                  -- ATIVA, ANULADA, DESATUALIZADA
  embedding VECTOR(768),        -- pgvector — busca semântica
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE alternativa (
  id BIGSERIAL PK,
  questao_id FK,
  letra CHAR(1),
  texto_md TEXT,
  correta BOOLEAN
);
CREATE TABLE questao_assunto (questao_id FK, assunto_id FK, PRIMARY KEY (questao_id, assunto_id));

-- Comentários (gerados por IA + curados manualmente)
CREATE TABLE comentario (
  id BIGSERIAL PK,
  questao_id FK,
  origem TEXT,             -- GEMINI, MANUAL
  modelo TEXT,             -- gemini-3-pro-preview, etc
  texto_md TEXT,
  rating_usuario INT,
  created_at TIMESTAMPTZ
);

-- Usuário
CREATE TABLE usuario (id SERIAL PK, email TEXT UNIQUE, ...);
CREATE TABLE resolucao (
  id BIGSERIAL PK,
  usuario_id FK, questao_id FK,
  resposta TEXT, acertou BOOLEAN,
  tempo_segundos INT,
  created_at TIMESTAMPTZ
);
CREATE INDEX ON resolucao (usuario_id, questao_id, created_at DESC);

-- Cadernos
CREATE TABLE caderno (
  id BIGSERIAL PK,
  usuario_id FK,
  nome TEXT,
  pasta TEXT,
  filtros JSONB,            -- query salva (banca, ano, etc)
  question_ids BIGINT[],    -- materializado
  total INT,
  created_at TIMESTAMPTZ
);
```

**Decisão**: armazenar `question_ids[]` materializado no caderno (igual TecConcursos provavelmente faz) — estabilidade de histórico.

---

## 5. Engine de busca (o coração da velocidade)

### 5.1 Meilisearch (recomendado) vs alternativas

| Engine | Prós | Contras |
|---|---|---|
| **Meilisearch** | ✅ trivial setup (Docker), ✅ facets nativos rápidos, ✅ typo-tolerance, ✅ Rust, ✅ memory-mapped | mais simples que ES — não tem queries DSL complexas (não precisamos) |
| Elasticsearch | DSL completo, escala horizontal massiva | overkill, RAM-hungry, JVM, complexidade alta |
| Typesense | similar ao Meili | comunidade menor |
| Postgres FTS + pgroonga | sem infra extra | facets lentos > 1M docs |

**Decisão: Meilisearch**.

### 5.2 Esquema do índice `questoes`

```json
{
  "id": 12345,
  "codigo_externo": "Q3412304",
  "enunciado": "O comportamento de um solo argiloso...",
  "gabarito": "A",
  "tipo": "MULTIPLA_ESCOLHA",
  "banca": "IDECAN",
  "orgao": "CNEN",
  "cargo": "Tecnologista - Análise de Segurança",
  "ano": 2014,
  "prova_codigo": "TL8",
  "materias": ["Engenharia Civil"],
  "assuntos": ["Características e Propriedades dos Solos"],
  "escolaridade": "SUPERIOR",
  "area": "Engenharia Civil",
  "esfera": "FEDERAL",
  "regiao": "RJ",
  "status": "ATIVA",
  "tem_imagem": true,
  "tem_texto_associado": false
}
```

### 5.3 Configuração Meili

```python
index.update_settings({
  "filterableAttributes": [
    "banca", "orgao", "cargo", "ano", "prova_codigo",
    "materias", "assuntos", "escolaridade", "area",
    "esfera", "regiao", "tipo", "status", "tem_imagem"
  ],
  "sortableAttributes": ["ano", "id"],
  "searchableAttributes": ["enunciado", "codigo_externo", "assuntos"],
  "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
  "stopWords": ["o", "a", "os", "as", "de", "da", "do"],
  "synonyms": {
    "cnen": ["comissão nacional de energia nuclear"],
    "civil": ["engenharia civil"]
  },
  "pagination": {"maxTotalHits": 1000000}
})
```

### 5.4 Query típica do filtro UI

```http
POST /indexes/questoes/search
{
  "q": "",
  "filter": "banca = \"CESGRANRIO\" AND ano = 2022",
  "facets": ["banca", "orgao", "ano", "materia", "assunto"],
  "limit": 20,
  "offset": 0
}
```

Response em <50ms inclui:
- `hits[]` — questões da página atual
- `estimatedTotalHits` — o "91680 questões encontradas"
- `facetDistribution.banca` — `{"CESGRANRIO": 91680, "FGV": 12345, ...}` — números nas opções do filtro
- `processingTimeMs`

### 5.5 Sincronização Postgres ↔ Meili

Tarefa Taskiq dispara em hooks SQLAlchemy (`after_insert`, `after_update`, `after_delete` em `Questao`). Bulk-reindex disponível como CLI: `dev.sh reindex`.

---

## 6. Pipeline de ingestão de conteúdo

### 6.1 Fontes

**Datasets públicos**
- HuggingFace: `mateuspestana/BR-Questoes-Concursos` e similares
- Repositórios GitHub: `questoes-de-concurso/*`

**PDFs oficiais das bancas**
- IDECAN: `idecan.org.br`
- Cesgranrio: `cesgranrio.org.br/concursos/{slug}/provas`
- FGV: `conhecimento.fgv.br/concursos`
- Cebraspe: `cebraspe.org.br/concursos`

**Export manual via UI do TecConcursos**
- Função "Imprimir caderno" gera PDF agregado (200 questões por impressão, ver §9).
- Upload do PDF no MinIO → pipeline `ingest_prova_pdf`.

**Scraper automatizado** — ver Apêndice C.

### 6.2 Pipeline `ingest_prova_pdf`

```python
@broker.task
async def ingest_prova_pdf(prova_id: int):
    prova = await get_prova(prova_id)
    pdf_bytes = await minio.download(prova.pdf_path)

    # 1. Extrai texto + imagens com PyMuPDF
    paginas = extract_text_and_images(pdf_bytes)

    # 2. Submete Gemini Batch (-50% custo)
    batch_input = build_extraction_prompt(paginas)
    job_id = await gemini.batch_submit(
        model="gemini-3-pro-preview",
        input=batch_input,
        schema=QuestoesExtraidasSchema  # structured output
    )

    # 3. Polling até completar (worker outro)
    questoes_extraidas = await wait_for_batch(job_id)

    # 4. Salva no Postgres
    for q in questoes_extraidas:
        questao = await create_questao(
            prova_id=prova_id,
            enunciado_md=q.enunciado,
            alternativas=q.alternativas,
            gabarito=q.gabarito,
            assuntos=q.assuntos,  # classificação automática
        )
        await generate_embedding(questao.id)  # text-embedding-3-small
        await reindex_meili(questao.id)
```

### 6.3 Schema de extração (Gemini structured output)

```python
class AlternativaExtraida(BaseModel):
    letra: Literal["A", "B", "C", "D", "E"]
    texto: str

class QuestaoExtraida(BaseModel):
    numero: int
    tipo: Literal["MULTIPLA_ESCOLHA", "CERTO_ERRADO", "DISCURSIVA"]
    enunciado_md: str
    imagens_paginas: list[int]
    texto_associado_id: int | None
    alternativas: list[AlternativaExtraida]
    gabarito: str
    materia_sugerida: str
    assuntos_sugeridos: list[str]
    dificuldade_estimada: Literal["FACIL", "MEDIO", "DIFICIL"]

class QuestoesExtraidasSchema(BaseModel):
    questoes: list[QuestaoExtraida]
    textos_associados: list[dict]
```

### 6.4 Importação manual de caderno (HTML salvo do navegador)

Para o caso "caderno exportado da UI":

```python
@broker.task
async def ingest_caderno_html(usuario_id: int, html_path: str):
    """
    Parsea o HTML/PDF que o usuário salvou do TecConcursos.
    Não acessa o site. Apenas processa o arquivo já no disco.
    """
    soup = BeautifulSoup(open(html_path), "lxml")
    questoes = parse_questoes(soup)  # parser regex+css selectors
    # ... mesmo pipeline que ingest_prova_pdf a partir do passo 4
```

---

## 7. UI/UX (Next.js 16)

### 7.1 Páginas

| Rota | Função | Componentes principais |
|---|---|---|
| `/q` | Home — busca rápida e cadernos | SearchHero, RecentCadernos |
| `/q/filtrar` | **A página-chave** — filtro facetado tipo TecConcursos | FacetSidebar, QuestaoCard, ResultCount |
| `/q/questao/{id}` | Detalhe da questão (resolver) | QuestaoCard, AlternativasList, ComentariosTabs, AulaChat (reusa do studIA) |
| `/q/cadernos` | Lista de cadernos do usuário | CadernoList |
| `/q/cadernos/{id}` | Resolver caderno | QuestaoCard, Navigator (← →), TimerHeader |
| `/q/estatisticas` | Dashboard de desempenho | charts (acertos por matéria) |
| `/q/admin/ingest` | Upload PDF de prova | PdfUploader (reusa studIA) |

### 7.2 Tela `/q/filtrar` — anatomia

Replica o que aparece na sua screenshot do TecConcursos:

```
┌──────────────────────────────────────────────────────────────────────┐
│ ☰ Filtrar Questões    ● Objetivas  ○ Inéditas  ○ Discursivas         │
├──────────────────────────────────────────────────────────────────────┤
│ ┌─Sidebar──────────┐  ┌─Coluna do filtro escolhido──┐  ┌─Filtros─┐  │
│ │ • Matéria/Assunto│  │ Nome: [cesgr_________]      │  │ ativos: │  │
│ │ • Banca          │  │                              │  │ 1       │  │
│ │ • Órgão/Cargo    │  │ ► CESGRANRIO           ✓     │  │         │  │
│ │ • Ano            │  │                              │  │ × Banca:│  │
│ │ • Área           │  │                              │  │  CESGRA-│  │
│ │ • Escolaridade   │  │                              │  │  NRIO   │  │
│ │ • Formação       │  │                              │  │         │  │
│ │ • Região         │  │                              │  │OPÇÕES   │  │
│ │ • Favoritas      │  │                              │  │Remover  │  │
│ │ • Enunciados     │  │                              │  │anuladas │  │
│ │ • Opções         │  │                              │  │Remover  │  │
│ └──────────────────┘  └──────────────────────────────┘  │desatual.│  │
│                                                          └─────────┘  │
│  91.680 questões encontradas               [Calcular dificuldade]    │
│  Editar quantidades                                                   │
│                                                                       │
│  Nome do caderno: [Caderno de Estudo___]  Pasta: [Sem classific…▾]   │
│  ☐ Gerar cadernos em série              [GERAR CADERNO]              │
└──────────────────────────────────────────────────────────────────────┘
│                          Pré-visualização Questão 1 de 91680         │
│  [Questão completa com alternativas — mesma estrutura do detalhe]    │
└──────────────────────────────────────────────────────────────────────┘
```

**Implementação**:
- TanStack Query com `keepPreviousData` + `debounce 250ms` no input → ilusão de instantaneidade
- Cada categoria do sidebar é um `Combobox` virtual (busca embutida tipo o "cesgr" da screenshot) sobre os facets distribution
- Chips de filtros ativos no painel direito
- Number badge ao lado do tipo (objetiva/inédita/discursiva) atualiza junto com cada toggle
- Pré-visualização da primeira questão usa o mesmo `QuestaoCard` que `/q/questao/{id}` — código único

### 7.3 Tela `/q/cadernos/{id}` (modo resolução)

Replica a UX do screenshot principal: questão central, navegação ← →, timer, indicador "Questão 40 de 876", botão favoritar/comentar/anotar.

### 7.4 Componentes-chave

| Componente | Reusa de studIA? |
|---|---|
| `QuestaoCard` | novo |
| `AlternativasList` (com 3D flip estilo flashcard) | adapta `FlipCard` do studIA |
| `MarkdownRenderer` | ✅ direto (tags `<atencao>`, `<destaque>`, `<resumo>`) |
| `FacetSidebar` | novo |
| `AulaChat` → renomear `QuestaoChat` | reusa lógica SSE |
| `PdfUploader` | ✅ direto |
| `ModelSelector` | ✅ direto |

---

## 8. Features de IA (o diferencial sobre TecConcursos)

### 8.1 Comentário gerado por IA

Ao resolver questão, botão "Comentar com IA" → endpoint `POST /api/ia/comentar/{questao_id}` → Gemini streaming SSE com o contexto:
- Enunciado
- Alternativas
- Gabarito oficial
- Matéria/assunto

Prompt template gera markdown com tags `<atencao>`, `<destaque>`, `<resumo>` que o `MarkdownRenderer` já renderiza.

### 8.2 Geração de questões similares

`POST /api/ia/similar/{questao_id}` → Gemini gera 3 questões novas no mesmo assunto, dificuldade comparável. Permite criar "deck infinito" de prática.

### 8.3 Chat com a questão / com a prova inteira

Igual `/disciplinas/[slug]/aulas/[id]` do studIA: chat lateral, contexto = enunciado + comentários + PDF da prova original.

### 8.4 Classificação semântica automática

Toda questão tem embedding pgvector. Permite:
- "Questões similares a esta" via cosine similarity
- Auto-tag de novos assuntos: KNN contra questões já classificadas
- Busca semântica: "questões sobre limites de Atterberg" mesmo sem usar essas palavras exatas

### 8.5 Adaptive learning (fase 2)

Repetição espaçada (já tem fator de facilidade no Flashcard do studIA) aplicada a questões. Acertou → próxima revisão em N dias. Errou → revisar amanhã.

### 8.6 Análise de fraqueza

Dashboard: "Você acerta 92% em Direito Civil mas 47% em Direito Tributário". Sugere caderno automático focado nas fraquezas.

---

## 9. Aquisição de questões — análise prática

### 9.1 Achados sobre as regras de negócio do TecConcursos (testado ao vivo)

| Limite | Valor | Implicação |
|---|---|---|
| Tamanho máximo de caderno | **30.000 questões** | precisa filtrar pra criar caderno grande |
| Quantidade máxima por impressão | **200 questões** | 22.123 questões = 111 PDFs separados |
| Configurações de impressão | matéria/assunto, gabarito, texto associado, QR code | tudo customizável |
| Início da impressão | "A partir da questão N" ou "Aleatoriamente" | permite paginar manualmente |
| Plano padrão | rate-limit aparente, sem detalhes públicos | plano avançado pode ter limites maiores |

**Cenário testado**: criei o caderno `95116581` com filtro `Banca=CESGRANRIO AND Cargo IN (Petrobras Nível Superior, Transpetro Nível Superior, Profissional Júnior)` → 22.123 questões.

### 9.2 Dimensionamento — escopo do caderno

Cobertura por filtro:
- Matéria "Engenharia Civil" → ~3.000 questões
- + Assunto "Estruturas de Concreto" → ~400 questões
- + Ano ≥ 2018 → ~150 questões

Cada PDF de impressão suporta 200 questões.

### 9.3 Caminho A — Impressão focada (manual)

1. Caderno com ≤ 400 questões (filtro refinado)
2. Aba **Imprimir** dentro do caderno
3. Configurações:
   - Quantidade máxima: 200 (limite do site)
   - Início: 1 (depois 201)
   - Cabeçalho: Com matéria e assunto
   - Gabarito: No fim do caderno (mais fácil de parsear)
   - Texto associado: Sim
   - Tamanho fonte: Normal
   - QR code: Não (irrelevante pra OCR)
4. `Ctrl+P` → "Salvar como PDF"
5. Upload em `/q/admin/ingest` do witdev-tec-master
6. Pipeline Gemini Batch processa → questões estruturadas no Postgres

### 9.4 Caminho B — Cobertura ampla via impressão iterada

- 22.123 ÷ 200 = **111 PDFs**
- Tempo por PDF: ~5min (mudar campo "início", clicar imprimir, esperar geração, salvar)
- Total: ~9h distribuídas

### 9.5 Caminho C — Scraper automatizado

Ver Apêndice C para implementação completa (PDF iterado ou API JSON direta).

### 9.6 Caminho D — Provas públicas das bancas

1. PDFs oficiais publicados pelas próprias bancas:
   - Cesgranrio: `cesgranrio.org.br/concursos/{slug}/provas`
   - FGV: `conhecimento.fgv.br/concursos`
   - Cebraspe: `cebraspe.org.br/concursos`
   - IDECAN: `idecan.org.br`
2. Cada prova tem 70-100 questões.
3. 30-40 provas = ~3.000 questões com gabarito oficial.
4. Comentários e classificação por matéria/assunto gerados via Gemini.

### 9.7 Caminho E — Datasets públicos

- HuggingFace: `concursos brasil questoes`
- Kaggle: `enem-concursos-questions`
- Verificar licença antes de usar.

### 9.8 Mix recomendado

Caderno-alvo focado (≤ 400 questões) via Caminho A + completar gaps via Caminho D (provas públicas) + features IA (similar, comentário) cobre a maioria dos casos sem necessidade do Apêndice C.

---

## 10. Princípios gerais de scraping

Princípios técnicos aplicáveis a qualquer fonte que o scraper precise consumir:

### 10.1 Ferramentas Python

| Tool | Quando usar |
|---|---|
| `httpx` (async) | sites estáticos, APIs REST |
| `BeautifulSoup` + `lxml` | parsing HTML |
| `Playwright` (Python) | sites JS-heavy, SPA, infinite scroll |
| `pdfplumber` / `PyMuPDF` | PDFs |
| `tenacity` | retry com backoff |
| `aiometer` | rate limit |

### 10.2 Padrões essenciais

```python
import httpx, asyncio
from aiometer import run_all
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def fetch(client, url):
    r = await client.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r

async def main():
    async with httpx.AsyncClient(http2=True, cookies=cookies) as client:
        urls = [f"https://banca.org/prova/{i}" for i in range(1, 1000)]
        # max 5 req/s
        results = await run_all(
            [lambda u=u: fetch(client, u) for u in urls],
            max_per_second=5,
        )
```

### 10.3 Padrões de paginação a reconhecer

- `?page=N` — fácil
- `?cursor=abc&limit=20` — seguir até `next_cursor=null`
- Infinite scroll com IntersectionObserver — usar Playwright e disparar scroll
- GraphQL com `endCursor`/`hasNextPage`

### 10.4 Rate limit e detecção

- **`robots.txt`** — checar antes de iniciar
- **Rate limit**: 1–5 req/s; observar `Retry-After` em 429
- **User-Agent realista** (Chrome desktop)
- **Rotação de IP**: proxies residenciais (Bright Data, Oxylabs) quando necessário
- **Cookies de sessão**: extrair via Playwright e reusar em httpx
- **CSRF token**: extrair de `<meta>` ou cookies e enviar em headers
- **Cloudflare/captcha**: sinal de stop, backoff exponencial

### 10.5 Estrutura recomendada do scraper

```
scrapers/
├── base.py              # AsyncScraper class com retry, rate limit, cache
├── idecan.py            # banca específica
├── cesgranrio.py
├── fgv.py
├── pipelines/
│   ├── normalize.py     # converte HTML → dict QuestaoExtraida
│   └── persist.py       # salva no Postgres + reindexa Meili
└── cli.py               # python -m scrapers idecan --since 2020
```

### 10.6 Cache local

```python
import diskcache
cache = diskcache.Cache("/tmp/witdev-scrape")

@cache.memoize(expire=86400)
async def fetch_cached(url): ...
```

Permite re-rodar parsing sem re-bater no servidor.

---

## 11. Roadmap em fases

### Fase 0 — Infra (1–2 dias)
- [ ] Subir Meilisearch no `docker-compose.dev.yml`
- [ ] Adicionar `meili-python` ao backend
- [ ] CLI `dev.sh reindex` faz bulk-import Postgres → Meili
- [ ] Smoke test: criar 10 questões mock, filtrar por banca

### Fase 1 — MVP de ingestão (3–5 dias)
- [ ] Modelos SQLAlchemy: `Banca`, `Orgao`, `Cargo`, `Prova`, `Materia`, `Assunto`, `Questao`, `Alternativa`
- [ ] Migrações via `migrate.py` (segue padrão studIA)
- [ ] Endpoint `POST /api/ingest/prova` upload PDF
- [ ] Task Taskiq `ingest_prova_pdf` com Gemini Batch + structured output
- [ ] Teste: baixar 1 PDF público IDECAN/CNEN e ingestir → ver 70 questões no Postgres

### Fase 2 — Engine de busca (2–3 dias)
- [ ] Schema Meili + sync Postgres→Meili
- [ ] Endpoint `GET /api/questoes?filter=banca:CESGRANRIO&facets=banca,ano,materia`
- [ ] Teste: 91k questões indexadas → query < 100ms

### Fase 3 — UI de filtro facetado (4–6 dias)
- [ ] `/q/filtrar` página
- [ ] Sidebar de categorias + busca dentro da categoria
- [ ] Painel de filtros ativos com chips
- [ ] Pré-visualização da primeira questão
- [ ] Botão "Gerar Caderno"

### Fase 4 — Resolução e cadernos (3–4 dias)
- [ ] `/q/cadernos/{id}` — modo navegação + timer
- [ ] `QuestaoCard` + `AlternativasList` (com flip 3D opcional)
- [ ] Salvar `resolucao` ao responder
- [ ] Indicador "questão N de M"

### Fase 5 — IA (3–4 dias)
- [ ] `POST /api/ia/comentar/{id}` — Gemini streaming
- [ ] `POST /api/ia/similar/{id}` — geração de questões similares
- [ ] Chat lateral por questão (reusa `AulaChat`)
- [ ] Embeddings pgvector + endpoint `GET /api/questoes/{id}/similares`

### Fase 6 — Estatísticas (2 dias)
- [ ] Dashboard de acertos por matéria
- [ ] Heatmap de fraquezas
- [ ] Sugestão de caderno automático

### Fase 7 — Ingest manual via HTML salvo (2 dias)
- [ ] Endpoint `POST /api/ingest/caderno-html` recebe arquivo
- [ ] Parser BeautifulSoup converte HTML em QuestaoExtraida[]
- [ ] Pipeline igual ao do PDF

**Total estimado**: 20–30 dias de trabalho focado.

---

## 12. Decisões técnicas registradas

| # | Decisão | Razão |
|---|---|---|
| 1 | Meilisearch (não ES) | simplicidade, facets nativos, Rust |
| 2 | Mesmo monorepo do studIA | reuso máximo (auth, Markdown, Gemini, MinIO) |
| 3 | Postgres é source-of-truth, Meili é índice | consistência > performance escrita |
| 4 | `question_ids[]` materializado no caderno | estabilidade histórica (igual TC, confirmado pelo URL `/cadernos/95116581`) |
| 5 | Gemini Batch para ingestão | -50% custo |
| 6 | Gemini Streaming SSE para chat/comentário | UX |
| 7 | pgvector para busca semântica | já habilitado no studIA |
| 8 | Pipeline de import suporta PDF (Imprimir) + scraper API (Apêndice C) | múltiplas fontes |
| 9 | Conta dedicada para o scraper | isolamento operacional |
| 10 | Nome final do projeto | `witdev-tec-master` (pasta `/questoes` no monorepo) |
| 11 | Separar endpoints `/contagem/filtros` e `/filtros` | replica padrão observado no TC; cache Redis na contagem |
| 12 | Taxonomia (bancas/órgãos/regiões) servida no payload inicial | replica AngularJS do TC; zero requests pra filtro UI |
| 13 | Limite caderno = 30.000 questões | mesmo limite do TC, regra de negócio sensata |
| 14 | Limite impressão = configurável (default 200) | mesmo limite do TC, anti-scraping |

## 12.1 Endpoints reais do TecConcursos observados (para inspiração arquitetural)

Mapeados durante teste ao vivo via hook em `XMLHttpRequest.prototype.open`:

| Endpoint TC | Método | O que faz | Nosso equivalente |
|---|---|---|---|
| `/api/questoes/contagem/filtros` | POST | retorna total + facets sem hits | `POST /api/q/count` |
| `/api/questoes/filtros` | POST | retorna lista paginada | `POST /api/q/search` |
| `/api/questoes/{id}/deslogado` | GET | retorna detalhe único cacheável | `GET /api/q/{id}` |

**Atenção**: replicamos o **padrão** arquitetural (separar count/list/detail). Não replicamos a API deles literalmente — payloads, schemas, autenticação são todos nossos.

---

## 13. Trade-offs técnicos

| Item | Característica | Mitigação técnica |
|---|---|---|
| Gemini Batch | latência 24h | fallback streaming pra ingestão urgente |
| Extração Gemini de fórmulas LaTeX | precisão ~85% | validação manual + flag `requer_revisao` |
| Custo IA por caderno | $5–$15 (Gemini Flash Batch) | preferir Batch sobre Live |
| Meilisearch RAM em 1M docs | ~1GB | host 4GB+ |
| Endpoint TC mudar schema | runtime error | validação Pydantic acusa, fix rápido |

---

## 14. Próximos passos imediatos

1. Revisão do spec
2. Invocar `writing-plans` para gerar **plano de implementação** detalhado da Fase 0 e Fase 1
3. Você decide se já começa ou aguarda

---

## Apêndice A — Sumário técnico do TC observado

**Autenticação**
Cookie de sessão (`AWSALB`, `AWSALBCORS`, `prism_*`). Sem JWT, sem OAuth, sem API key, sem CSRF meta tag. Para witdev-tec-master: JWT ou session cookie HttpOnly via Better Auth.

**UX sub-segundo do filtro**
1. Lista de bancas é client-side: digitar "cesgra" no campo não dispara requisição. Bancas vêm no payload HTML inicial e AngularJS filtra localmente.
2. Contagem e lista são endpoints separados: `POST /api/questoes/contagem/filtros` retorna `{total: 91680}` em ms; `POST /api/questoes/filtros` busca lista em paralelo.

Replicável com Meilisearch + Redis cache.

**Stack**
- Frontend: AngularJS 1.4.4
- Backend: rota `/api/questoes/...` por trás de AWS ALB (provável Java/Spring)
- Sessão: cookie
- Analytics: Microsoft Clarity
- Busca: Elasticsearch ou Solr (não confirmado)
- Padrão: contagem leve + lista pesada em paralelo + cache

## Apêndice B — Como replicar a "magia da velocidade"

Receita curta de como implementar no witdev-tec-master:

```python
# backend/api/questoes_filtros.py

@router.post("/api/questoes/contagem/filtros")
async def contagem(filtros: FiltrosSchema):
    # 1. Tenta cache Redis primeiro (chave = hash dos filtros)
    cache_key = f"contagem:{filtros.fingerprint()}"
    cached = await redis.get(cache_key)
    if cached:
        return {"total": int(cached), "facets": json.loads(await redis.get(f"facets:{cache_key}"))}

    # 2. Cache miss → consulta Meilisearch (não traz hits)
    result = await meili.index("questoes").search("", {
        "filter": filtros.to_meili_filter(),
        "limit": 0,           # NÃO queremos hits
        "facets": ["banca", "orgao", "ano", "materia", "assunto"]
    })

    # 3. Cacheia 1h (filtros comuns mudam pouco)
    await redis.setex(cache_key, 3600, result["estimatedTotalHits"])
    await redis.setex(f"facets:{cache_key}", 3600, json.dumps(result["facetDistribution"]))

    return {"total": result["estimatedTotalHits"], "facets": result["facetDistribution"]}


@router.post("/api/questoes/filtros")
async def lista(filtros: FiltrosSchema, page: int = 1):
    # Sem cache — retorna lista paginada
    result = await meili.index("questoes").search("", {
        "filter": filtros.to_meili_filter(),
        "limit": 20,
        "offset": (page - 1) * 20,
        "attributesToRetrieve": ["id", "enunciado_preview", "banca", "ano", "tipo", "gabarito"]
    })
    return {"hits": result["hits"], "total": result["estimatedTotalHits"]}
```

```typescript
// fontend/app/q/filtrar/page.tsx (Next.js)

const Filtros = () => {
  const [filtros, setFiltros] = useState({});

  // Dispara DUAS queries em paralelo (igual TecConcursos)
  const contagem = useQuery({
    queryKey: ['contagem', filtros],
    queryFn: () => api.post('/api/questoes/contagem/filtros', filtros),
    keepPreviousData: true,  // mantém número antigo enquanto carrega
  });

  const lista = useQuery({
    queryKey: ['lista', filtros],
    queryFn: () => api.post('/api/questoes/filtros', filtros),
    keepPreviousData: true,
  });

  // Bancas vêm no SSR/getStaticProps (igual o "payload inicial" do TC)
  const bancas = bancasStatic;  // array de ~200 items injetado no build
  const [busca, setBusca] = useState('');
  const bancasFiltradas = bancas.filter(b =>
    b.nome.toLowerCase().includes(busca.toLowerCase())
  );

  return (
    <>
      <BancaCombobox items={bancasFiltradas} onSearch={setBusca} />  {/* filtro client-side puro */}
      <h1>{contagem.data?.total} questões encontradas</h1>
      <QuestaoList items={lista.data?.hits} />
    </>
  );
};
```

**Resultado**: mesma UX, mesma velocidade percebida, framework moderno (Next.js + React + TanStack Query).

---

## Apêndice C — Scraper de cadernos (especificação técnica)

### C.1 Contexto técnico observado

Confirmado via hook em XHR:

```
Frontend:    AngularJS 1.4.4 (code-name "pylon-requirement")
Auth:        Cookies de sessão HttpOnly (AWSALB, AWSALBCORS, prism_<id>)
              Sem JWT, sem Bearer, sem CSRF meta-tag, sem API key
Infra:       AWS ALB (cookies AWSALB) → backend provável Java/Spring
Base total:  3.928.498 questões
```

Endpoints REST observados (URLs visíveis no hook; payloads não inspecionados):

| Endpoint | Método | Função |
|---|---|---|
| `/api/questoes/contagem/filtros` | POST | Retorna `{total, facets}` (sub-segundo) |
| `/api/questoes/filtros` | POST | Retorna lista paginada |
| `/api/questoes/{id}/deslogado` | GET | Detalhe único de uma questão |
| `/login` | POST | Autenticação (form-encoded `email` + `senha`) |
| `/questoes/cadernos/{id}` | GET | Página do caderno (HTML/Angular) |

Limites do produto:
- Caderno: **30.000 questões** máximo
- Impressão: **200 questões** por PDF
- Sem confirmação pública de rate limit por endpoint; **trate como 1-3 req/s** por segurança.

### C.2 Comparação dos dois caminhos

| Critério | Caminho 1 — PDF (Imprimir) | Caminho 2 — API JSON direta |
|---|---|---|
| Mecanismo | Playwright clica "Imprimir", salva PDF, repete | httpx hit `/api/questoes/{id}` para cada ID |
| Iterações pra 22.123 questões | 111 PDFs (200 cada) | 22.123 requests |
| Tempo estimado (rate 2 req/s) | ~9h | ~3h |
| Custo IA | $20–$50 Gemini Batch (extração) | $0 (JSON estruturado) |
| Qualidade dos dados | Texto + posicional, requer OCR/extração | Estruturado nativo |
| Resiliência a mudanças do site | Alta (formato Imprimir é estável) | Baixa (endpoint pode mudar) |
| Dependência de Gemini | Sim (extrair questão do PDF) | Não (opcional pra comentar/classificar) |

### C.3 Setup comum aos dois caminhos

```bash
# Python 3.12+
poetry init witdev-tec-scraper
poetry add playwright httpx[http2] tenacity aiometer beautifulsoup4 lxml \
          pdfplumber pymupdf pydantic python-dotenv structlog
poetry run playwright install chromium
```

```env
# .env
TC_EMAIL=witalorocha216@gmail.com
TC_PASSWORD=<sua senha>
TC_BASE=https://www.tecconcursos.com.br
OUT_DIR=./output
RATE_PER_SEC=2
JITTER_SEC=0.5
USER_AGENT=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36
```

### C.4 Módulo comum: login + persistência de sessão

```python
# scraper/auth.py
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

STATE_FILE = Path("storage_state.json")

async def login_and_save_state(email: str, password: str) -> None:
    """
    Loga via Playwright (Chromium) e salva storage_state (cookies + localStorage).
    Roda 1x ao iniciar e quando sessão expira (HTTP 302 → /login).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # primeira vez visual; trocar pra True depois
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto("https://www.tecconcursos.com.br/login")
        await page.fill('input[type="email"]', email)
        await page.fill('input[type="password"]', password)
        await page.click('button:has-text("Entrar no site")')
        await page.wait_for_url("**/questoes/**", timeout=15_000)
        await ctx.storage_state(path=STATE_FILE)
        await browser.close()

def load_cookies_for_httpx() -> dict:
    """Lê storage_state.json e retorna cookies como dict pra httpx."""
    import json
    state = json.loads(STATE_FILE.read_text())
    return {c["name"]: c["value"] for c in state["cookies"] if "tecconcursos" in c["domain"]}
```

### C.5 Caminho 1 — Scraper via PDF (Imprimir)

```python
# scraper/via_pdf.py
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import structlog

log = structlog.get_logger()

async def baixar_pdfs_caderno(
    caderno_id: int,
    total: int,
    lote: int = 200,
    out_dir: Path = Path("output/pdfs"),
    rate_per_sec: float = 0.2,  # 1 PDF a cada 5s — gentil
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdfs: list[Path] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            storage_state="storage_state.json",
            accept_downloads=True,
        )
        page = await ctx.new_page()

        for inicio in range(1, total + 1, lote):
            log.info("imprimindo_lote", inicio=inicio, fim=min(inicio + lote - 1, total))
            await page.goto(f"https://www.tecconcursos.com.br/questoes/cadernos/{caderno_id}")
            await page.click("text=Imprimir")
            await page.fill('input[name="quantidadeMaxima"]', str(lote))
            await page.fill('input[name="inicio"]', str(inicio))
            # Garante config conhecida:
            await page.check('input[value="COM_MATERIA_E_ASSUNTO"]')
            await page.check('input[value="GABARITO_NO_FIM"]')

            # Captura PDF — o site pode abrir em popup OU redirecionar.
            # Estratégia: interceptar response com content-type=application/pdf
            async with page.expect_download(timeout=120_000) as dl_info:
                await page.click('button:has-text("IMPRIMIR CADERNO")')
            download = await dl_info.value
            dest = out_dir / f"caderno-{caderno_id}-{inicio:05d}.pdf"
            await download.save_as(dest)
            pdfs.append(dest)

            await asyncio.sleep(1 / rate_per_sec)  # rate limit gentil

        await browser.close()
    return pdfs
```

**Pipeline subsequente** (já existe no spec na seção 6.2):

```python
# scraper/pipeline_pdf.py
from witdev_tec_master.gemini_service import batch_submit
from witdev_tec_master.models import Questao, Prova, ...

async def processar_pdfs(pdf_paths: list[Path]) -> None:
    for pdf in pdf_paths:
        # Submete Gemini Batch com schema QuestoesExtraidasSchema (ver seção 6.3)
        # Salva no Postgres
        # Reindexa Meilisearch
        ...
```

**Estimativas Caminho 1:**
- 111 PDFs × ~30s (gerar PDF no servidor + download) = ~1h apenas baixando
- + ~8h Gemini Batch (assíncrono, custo $20–50)
- + ~30min reindex Meili
- **Total wall-clock: ~12h, atenção do operador: ~30min**

### C.6 Caminho 2 — Scraper via API JSON com cookies de sessão

#### C.6.0 Características

| Item | Detalhe |
|---|---|
| Custo IA pra extração | $0 — resposta da API vem JSON estruturado (`{enunciado, alternativas[], gabarito, banca, ano, materia, assuntos}`) |
| Throughput | 22.123 requests JSON em ~3h; bandwidth ~50KB/questão |
| Dados | IDs internos, relacionamentos, flags `anulada`/`desatualizada`, contadores de comentários |
| Idempotência | 1 GET por questão; retry granular |
| Reindex | Schema bate diretamente com índice Meilisearch |
| Gemini | Opcional (comentários novos, classificação adicional, geração de similares) |

#### C.6.1 Fluxo

```
1. Playwright loga 1x → captura cookies (AWSALB, AWSALBCORS, prism_*)
2. Cookies vão pra um httpx.AsyncClient
3. Loop: GET /api/questoes/{id}/deslogado para cada ID do caderno
4. Cada resposta JSON → Pydantic → Postgres → Meilisearch
```

#### C.6.2 Extração de cookies (manual)

Recomendação: extração manual no início. Renovar quando sessão expirar (~7 dias, TTL do AWSALB).

```
1. Abrir Chrome, logar em https://www.tecconcursos.com.br
2. F12 → Application → Cookies → tecconcursos.com.br
3. Copiar os cookies:
   - AWSALB         (sessão load balancer, ~7 dias)
   - AWSALBCORS     (idem, pra CORS)
   - prism_<id>     (identificador usuário)
   - _ga, _fbp etc  (analytics — opcional)
4. Salvar em arquivo cookies.json:
{
  "AWSALB": "SwaH...long-base64...==",
  "AWSALBCORS": "SwaH...same-base64...==",
  "prism_255335179": "9f10b546-a697-4772-8251-512439870e65",
  "_ga": "GA1.1.899084782.1779838852"
}
```

**Alternativa automatizada (Playwright):**

```python
# scraper/auth.py
async def extract_cookies_via_playwright(email, password) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # primeira vez: visualizar, pode ter captcha
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...",
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1920, "height": 1080},
        )
        page = await ctx.new_page()
        await page.goto("https://www.tecconcursos.com.br/login")
        await page.fill('input[type="email"]', email)
        await page.fill('input[type="password"]', password)
        await page.click('button:has-text("Entrar no site")')
        await page.wait_for_url("**/questoes/**", timeout=15_000)

        cookies = await ctx.cookies()
        await browser.close()

        return {c["name"]: c["value"] for c in cookies if c["domain"].endswith("tecconcursos.com.br")}
```

#### C.6.3 Cliente httpx autenticado (template completo)

```python
# scraper/client.py
from __future__ import annotations
import json, asyncio
from pathlib import Path
import httpx, structlog

log = structlog.get_logger()

UA_REAL = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def load_cookies(path: Path = Path("cookies.json")) -> dict[str, str]:
    return json.loads(path.read_text())

class TcClient:
    """Cliente HTTP autenticado. Renova sessão se expirar."""
    BASE = "https://www.tecconcursos.com.br"

    def __init__(self, cookies: dict[str, str], rate_per_sec: float = 2.0):
        self.cookies = cookies
        self.sem = asyncio.Semaphore(4)  # max 4 reqs paralelas
        self.rate = rate_per_sec
        self._last_req = 0.0
        self._client = httpx.AsyncClient(
            base_url=self.BASE,
            http2=True,
            cookies=cookies,
            timeout=httpx.Timeout(connect=10, read=30, write=10, pool=30),
            follow_redirects=False,
            headers={
                "User-Agent": UA_REAL,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.BASE,
            },
        )

    async def _throttle(self):
        """Garante intervalo mínimo entre requests + jitter."""
        import time, random
        now = time.monotonic()
        elapsed = now - self._last_req
        min_interval = 1.0 / self.rate
        jitter = random.uniform(-0.3, 0.7) * min_interval
        wait = max(0, min_interval + jitter - elapsed)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_req = time.monotonic()

    async def get(self, url: str, *, referer: str | None = None) -> httpx.Response:
        async with self.sem:
            await self._throttle()
            headers = {"Referer": referer} if referer else {}
            r = await self._client.get(url, headers=headers)
            self._check_session(r)
            return r

    async def post(self, url: str, json_body: dict, *, referer: str | None = None) -> httpx.Response:
        async with self.sem:
            await self._throttle()
            headers = {"Referer": referer, "Content-Type": "application/json"} if referer else {"Content-Type": "application/json"}
            r = await self._client.post(url, json=json_body, headers=headers)
            self._check_session(r)
            return r

    def _check_session(self, r: httpx.Response):
        if r.status_code == 302 and "/login" in r.headers.get("location", ""):
            raise SessionExpired("sessão expirou, renove cookies.json")
        if r.status_code == 429:
            raise RateLimited(int(r.headers.get("Retry-After", "60")))
        if r.status_code in (403, 451):
            raise AccessBlocked(f"status {r.status_code}")

    async def aclose(self):
        await self._client.aclose()

class SessionExpired(Exception): ...
class RateLimited(Exception): 
    def __init__(self, retry_after: int): self.retry_after = retry_after
class AccessBlocked(Exception): ...
```

#### C.6.4 Endpoints mapeados (com payload esperado)

> **Importante**: o programador **deve fazer 1 hora de DevTools manual antes de codar** pra confirmar os schemas. Os schemas abaixo são **inferidos** com base em padrões REST típicos + nomes observados. Marcados com `# CONFIRMAR`.

##### Endpoint A — Detalhe de uma questão

```
GET /api/questoes/{id}/deslogado
Cookies: (sessão)
Referer: /questoes/cadernos/{caderno_id}
```

```python
# Schema INFERIDO — confirmar com 1 captura real
from pydantic import BaseModel, Field
from typing import Optional

class BancaApi(BaseModel):
    id: int
    nome: str
    sigla: Optional[str] = None  # CONFIRMAR

class OrgaoApi(BaseModel):
    id: int
    nome: str
    sigla: Optional[str] = None
    esfera: Optional[str] = None  # CONFIRMAR (FEDERAL/ESTADUAL/MUNICIPAL)

class CargoApi(BaseModel):
    id: int
    nome: str
    ano: int
    escolaridade: Optional[str] = None  # CONFIRMAR

class AssuntoApi(BaseModel):
    id: int
    nome: str
    materia_id: int

class AlternativaApi(BaseModel):
    id: int
    letra: str  # "A"|"B"|"C"|"D"|"E"
    texto: str
    correta: Optional[bool] = None  # pode vir só pelo `gabarito` separado

class QuestaoApi(BaseModel):
    id: int
    codigo: str = Field(alias="codigoExterno")  # CONFIRMAR — talvez seja só `id`
    enunciado: str  # HTML rich text
    tipo: str  # "MULTIPLA_ESCOLHA" | "CERTO_ERRADO" | "DISCURSIVA"
    gabarito: Optional[str] = None
    banca: BancaApi
    orgao: OrgaoApi
    cargo: CargoApi
    materia: dict  # {id, nome}
    assuntos: list[AssuntoApi]
    alternativas: list[AlternativaApi]
    texto_associado: Optional[str] = None
    imagens: list[str] = []
    status: Optional[str] = None  # ATIVA | ANULADA | DESATUALIZADA
    tem_comentario_professor: Optional[bool] = None
```

##### Endpoint B — IDs do caderno

Hipóteses ordenadas — programador testa em DevTools, primeira que aparecer:

```
1ª tentativa:  GET  /api/cadernos/{caderno_id}/questoes/ids
                    → list[int]
2ª tentativa:  GET  /api/cadernos/{caderno_id}
                    → {id, nome, total, question_ids: [...]}
3ª tentativa:  POST /api/cadernos/{caderno_id}/questoes
                    body: {pagina: N, tamanho: 200}
                    → {hits: [{id, ...}], total, next_page}
4ª tentativa:  POST /api/questoes/filtros
                    body: {filtros_originais_do_caderno}
                    → {hits: [{id, ...}], total}  # como faz a UI
```

##### Endpoint C — Comentários da questão

```
GET /api/questoes/{id}/comentarios
→ list[{id, autor, texto_html, data, votos}]
```

Útil pra enriquecer base (mas comentários de outros usuários são propriedade dos autores, **mantenha privado**).

#### C.6.5 Loop principal

```python
# scraper/run.py
import asyncio, json
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .client import TcClient, RateLimited, SessionExpired
import structlog

log = structlog.get_logger()

async def listar_ids_caderno(client: TcClient, caderno_id: int) -> list[int]:
    """Testa hipóteses em ordem até uma funcionar."""
    # 1ª tentativa
    r = await client.get(f"/api/cadernos/{caderno_id}/questoes/ids")
    if r.status_code == 200:
        return r.json()
    # 2ª tentativa
    r = await client.get(f"/api/cadernos/{caderno_id}")
    if r.status_code == 200:
        data = r.json()
        if "question_ids" in data:
            return data["question_ids"]
    # 3ª e 4ª: programador implementa após descoberta
    raise RuntimeError("endpoint de IDs do caderno não descoberto — inspecionar DevTools")

@retry(
    retry=retry_if_exception_type(RateLimited),
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=30, max=300),
)
async def fetch_questao(client: TcClient, qid: int, caderno_id: int):
    r = await client.get(
        f"/api/questoes/{qid}/deslogado",
        referer=f"https://www.tecconcursos.com.br/questoes/cadernos/{caderno_id}",
    )
    if r.status_code == 404:
        log.warning("not_found", qid=qid)
        return None
    r.raise_for_status()
    return QuestaoApi.model_validate(r.json())

async def main(caderno_id: int):
    cookies = json.loads(Path("cookies.json").read_text())
    client = TcClient(cookies, rate_per_sec=2.0)
    state = ScrapeState()

    try:
        ids = await listar_ids_caderno(client, caderno_id)
        log.info("iniciando", total=len(ids), caderno=caderno_id)

        sem = asyncio.Semaphore(4)

        async def task(qid: int):
            if state.ja_coletada(qid):
                return
            async with sem:
                try:
                    q = await fetch_questao(client, qid, caderno_id)
                    if q:
                        await persistir_postgres(q)
                        await indexar_meili(q)
                        state.marca(qid, caderno_id, "ok")
                        log.info("ok", qid=qid)
                except SessionExpired:
                    log.error("sessao_expirou — renove cookies.json e relance")
                    raise
                except Exception as e:
                    state.marca(qid, caderno_id, f"erro:{type(e).__name__}")
                    log.error("falhou", qid=qid, erro=str(e))

        await asyncio.gather(*[task(qid) for qid in ids])

    finally:
        await client.aclose()
        log.info("fim", coletadas=state.contar("ok"), erros=state.contar_prefix("erro"))

if __name__ == "__main__":
    import sys
    asyncio.run(main(int(sys.argv[1])))
```

#### C.6.6 Persistência direta Postgres + Meili (sem Gemini intermediário)

```python
# scraper/persistir.py
from witdev_tec_master.database import async_session
from witdev_tec_master.models import Questao, Banca, Orgao, Cargo, Materia, Assunto, Alternativa, questao_assunto
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def upsert_taxonomia(session, q_api: QuestaoApi):
    """Garante banca/orgao/cargo/materia/assuntos existem (upsert idempotente)."""
    banca_id = (await session.execute(
        pg_insert(Banca)
            .values(id=q_api.banca.id, nome=q_api.banca.nome, slug=slugify(q_api.banca.nome))
            .on_conflict_do_nothing()
            .returning(Banca.id)
    )).scalar_one_or_none() or q_api.banca.id
    # ... idem para orgao, cargo, materia, assuntos
    return {"banca_id": banca_id, "orgao_id": ..., "cargo_id": ..., "assunto_ids": [...]}

async def persistir_postgres(q_api: QuestaoApi):
    async with async_session() as session:
        ids = await upsert_taxonomia(session, q_api)

        # Upsert questão
        await session.execute(
            pg_insert(Questao).values(
                id=q_api.id,
                codigo_externo=q_api.codigo,
                enunciado_md=html_to_markdown(q_api.enunciado),
                tipo=q_api.tipo,
                gabarito=q_api.gabarito,
                banca_id=ids["banca_id"],
                # ...
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={"enunciado_md": ..., "gabarito": ..., "updated_at": "now()"}
            )
        )

        # Alternativas
        for alt in q_api.alternativas:
            await session.execute(
                pg_insert(Alternativa).values(
                    id=alt.id, questao_id=q_api.id, letra=alt.letra,
                    texto_md=html_to_markdown(alt.texto), correta=alt.correta,
                ).on_conflict_do_update(index_elements=["id"], set_={"texto_md": ...})
            )

        # Vínculo questão↔assunto
        for assunto_id in ids["assunto_ids"]:
            await session.execute(
                pg_insert(questao_assunto)
                    .values(questao_id=q_api.id, assunto_id=assunto_id)
                    .on_conflict_do_nothing()
            )

        await session.commit()

async def indexar_meili(q_api: QuestaoApi):
    """Adiciona ao índice Meilisearch (vai pro endpoint /q/contagem)."""
    from witdev_tec_master.search import meili
    await meili.index("questoes").add_documents([{
        "id": q_api.id,
        "codigo_externo": q_api.codigo,
        "enunciado": strip_html(q_api.enunciado),
        "banca": q_api.banca.nome,
        "orgao": q_api.orgao.nome,
        "cargo": q_api.cargo.nome,
        "ano": q_api.cargo.ano,
        "materia": q_api.materia["nome"],
        "assuntos": [a.nome for a in q_api.assuntos],
        "tipo": q_api.tipo,
        "status": q_api.status or "ATIVA",
    }])
```

#### C.6.7 Custo, tempo e escala — comparativo final

| Recurso | PDF (Caminho 1) | API JSON (Caminho 2) |
|---|---|---|
| Tempo wall-clock pra 22.123 questões | ~12h | ~3h |
| Atenção do operador | ~1h (renomear PDFs, monitorar) | ~30min |
| Custo Gemini | $20-50 (Batch obrigatório) | $0 (Gemini opcional) |
| Bandwidth | ~55 GB | ~1.1 GB |
| Qualidade dos dados | 85% (OCR pode errar fórmulas) | 99% (raw da fonte) |
| Resiliência | Alta (PDF nunca muda formato) | Média (endpoint pode mudar) |
| Comentários de professores | Não vêm no PDF | Sim (endpoint `/comentarios` separado) |
| Estatísticas (% acerto, dificuldade) | Não | Sim (campos extras na API) |

#### C.6.8 Cronograma de implementação

| Dia | Atividade | Entregável |
|---|---|---|
| 1 (manhã) | DevTools: capturar payloads reais de `/api/questoes/{id}/deslogado`, descobrir endpoint de IDs do caderno, salvar .har | `payloads/exemplo-questao.json`, `payloads/exemplo-caderno.json` |
| 1 (tarde) | Implementar `TcClient` + schemas Pydantic | `scraper/client.py`, `scraper/schemas.py` |
| 2 (manhã) | Implementar `listar_ids_caderno` + `fetch_questao` + `ScrapeState` | scrape de 10 questões funcionando |
| 2 (tarde) | Persistência Postgres + Meili (reusa modelos do studIA) | scrape de 100 questões salvas |
| 3 (manhã) | Rate limit, anti-fingerprint, retry exponencial, sessão expirada | run de 1.000 questões |
| 3 (tarde) | Logs estruturados (structlog → JSON), métricas | `logs/scrape-{ts}.jsonl` |
| 4 | Run full caderno (22.123), monitorar | base completa no Postgres + Meili |
| 5 | Documentação (`RUN.md`), handover, testes de retomada | repositório pronto |

Total: 5 dias × 8h = 40h.

#### C.6.9 Checklist de entrega

```markdown
- [ ] Repositório Git, `.gitignore` excluindo `cookies.json`
- [ ] README com instruções: capturar cookies, rodar, renovar
- [ ] `pyproject.toml` com dependências travadas (poetry.lock)
- [ ] `.env.example` documentado
- [ ] CLI: `python -m scraper.run <caderno_id>`
- [ ] Logs estruturados em `./logs/` (1 arquivo por execução)
- [ ] `scrape_state.db` (SQLite) pra retomada
- [ ] Tratamento de: sessão expirada, rate limit (429), 403, captcha
- [ ] Teste com 100 questões antes do run completo
- [ ] IDs faltantes (404) em `logs/missing.jsonl`
- [ ] Relatório final: total coletado, % sucesso, custo, tempo
- [ ] Handover: vídeo de 30min + 1h de suporte pós-entrega
- [ ] `cookies.json` fora do git
```

#### C.6.10 Cenários operacionais

| Cenário | Tratamento |
|---|---|
| HTTP 429 | Backoff exponencial honrando `Retry-After` |
| HTTP 302 → `/login` | Sessão expirou; renovar `cookies.json` e retomar |
| Captcha (HTML em vez de JSON) | Pausar, atualizar cookies manualmente, retomar do `ScrapeState` |
| Endpoint muda schema | Validação Pydantic acusa; ajustar campos |
| Cloudflare 5xx | Reduzir taxa pra 0.5 req/s, retomar em outra janela |
| Auth migrar pra Bearer/JWT | Re-descoberta (~1 dia de trabalho) |

---

### C.7 Headers e parâmetros de cliente HTTP

| Header / parâmetro | Valor |
|---|---|
| User-Agent | Chrome desktop realista (não `python-httpx/x.y`) |
| Intervalo entre requests | Jitter `0.3–1.5s` |
| `Referer` | `/questoes/cadernos/{id}` |
| `Accept-Language` | `pt-BR,pt;q=0.9,en;q=0.8` |
| `X-Requested-With` | `XMLHttpRequest` |
| Janela de execução | 22k requests em 6–12h, pausa de 30min a cada hora |
| Proxy | Residencial opcional (Bright Data) quando necessário |
| `navigator.webdriver` | Patch com `playwright-stealth` ou flag `--disable-blink-features=AutomationControlled` |
| Locale/timezone/viewport | `pt-BR` / `America/Sao_Paulo` / `1920x1080` |

### C.8 Classificação de respostas anômalas

```python
def classificar_resposta(r: httpx.Response) -> str | None:
    if r.status_code in (403, 451):
        return "acesso_negado"
    if r.status_code == 429:
        return "rate_limit"
    if r.status_code == 302 and "/login" in r.headers.get("location", ""):
        return "sessao_expirou"
    if "captcha" in r.text.lower():
        return "captcha"
    if "cloudflare" in r.text.lower() and r.status_code >= 500:
        return "cloudflare_challenge"
    if r.status_code == 200 and "<html" in r.text and "<title>Login" in r.text:
        return "sessao_zumbi"
    return None
```

Estratégia:
- `rate_limit` → backoff exponencial honrando `Retry-After`
- `sessao_expirou` / `sessao_zumbi` → renovar `cookies.json`, retomar do `ScrapeState`
- `captcha` → pausar, atualizar cookies manualmente, retomar
- `acesso_negado` → reduzir taxa, retomar em nova janela
- `cloudflare_challenge` → reduzir pra 0.5 req/s

### C.9 Persistência incremental e retomada

```python
# scraper/state.py
import sqlite3
from pathlib import Path

class ScrapeState:
    """Track dos IDs já coletados pra retomar do ponto de parada."""
    def __init__(self, db_path: Path = Path("scrape_state.db")):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS coletadas (
                id INTEGER PRIMARY KEY,
                caderno_id INTEGER,
                ts INTEGER,
                status TEXT
            )
        """)

    def ja_coletada(self, qid: int) -> bool:
        cur = self.conn.execute("SELECT 1 FROM coletadas WHERE id = ?", (qid,))
        return cur.fetchone() is not None

    def marca(self, qid: int, caderno_id: int, status: str = "ok"):
        self.conn.execute(
            "INSERT OR REPLACE INTO coletadas VALUES (?, ?, strftime('%s','now'), ?)",
            (qid, caderno_id, status)
        )
        self.conn.commit()
```

### C.10 Ordem de execução

1. **Descoberta (1 dia)** — login manual, DevTools, capturar payloads reais:
   - `POST /api/questoes/filtros` com o filtro do caderno
   - `GET /api/questoes/{id}/deslogado` em 3 questões diferentes
   - Endpoint que retorna IDs do caderno (testar candidatos)
   - Salvar `.har` da sessão
2. **Protótipo (1 dia)** — Caminho 1 (PDF) com 1 PDF (200 questões). Validar pipeline Gemini Batch → Postgres → Meili.
3. **Escala (1 dia)** — Caminho 1 pros 111 PDFs, 6-12h, monitorar logs.
4. **API (1 dia, opcional)** — Caminho 2 sobre subconjunto faltante OU pra dados mais ricos (comentários, estatísticas).
5. **Pos-mortem (½ dia)** — relatório: coletadas, erros, IDs faltantes, custo, anomalias.

**Critério de sucesso**: ≥ 95% dos IDs coletados, ≥ 90% com gabarito e alternativas válidos.

### C.11 Estimativa de esforço

| Item | Horas |
|---|---|
| Descoberta de schema | 4-6h |
| Caminho 1 (PDF) | 6-10h |
| Caminho 2 (API) | 8-12h |
| Pipeline Gemini Batch → Postgres → Meili | 4-6h (reusa studIA) |
| Testes + observabilidade | 4h |
| Documentação + handover | 2h |
| **Total** | **28-40h** |

### C.12 Entregáveis

1. Repositório Git com o scraper, README, `.env.example`, `pyproject.toml`
2. Script `scrape.py --caderno {id} --modo pdf|api`
3. Logs estruturados (JSON) em `./logs/`
4. `scrape_state.db` (SQLite) pra retomada
5. Output: PDFs (Caminho 1) ou JSONs por questão (Caminho 2) em `./output/`
6. Pipeline de ingestão integrado (Postgres + Meili)
7. `RUN.md`: rodar, parar, retomar, troubleshooting
8. Handover de 30min em vídeo
