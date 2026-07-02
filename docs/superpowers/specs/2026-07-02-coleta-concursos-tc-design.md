# Coleta de concursos do TecConcursos (edital / provas / gabarito → MinIO)

**Data:** 2026-07-02 · **Status:** aguardando aprovação

## Objetivo

A busca avançada do TC (ex.: Banca=IDECAN + Formação=Engenharia Civil → 49
concursos) lista concursos com arquivos para download (edital, prova objetiva,
prova discursiva, gabarito). Queremos: disparar essa busca do studIA com
filtros genéricos, baixar todos os arquivos para o MinIO e listar tudo numa
tela admin nova `/q/concursos`, com link para a página do concurso no TC.

## Contrato TC (descoberto e validado em 2026-07-02)

- `GET /api/concursos/busca-avancada` — **exige sessão TC logada** + headers
  `X-Requested-With: XMLHttpRequest` e `Logado: true`. Parâmetros:
  `busca.geradorBuscaConcursoFiltros[i].id` + `...[i].tipo` (tipos: `BANCA`,
  `PROFISSAO`, `ORGAO`, `ANO`, `AREA_CONCURSO`, `ESCOLARIDADE`…) e
  `busca.pagina=N`. Resposta: `{list, resultCount, currentPage, pageSize,
  totalPages, ...}`; cada item = `{edital: {...}, concursos: [{concursoId,
  editalId, nomeCompleto, urlConcurso, dataAplicacao, escolaridade,
  arquivosPorTipo: {EDITAL: [{id, nomeArquivo, uuid}], ...}}]}`.
  IDECAN = banca id 95; Engenharia Civil = profissão id 6.
- `GET /api/concursos/busca-avancada/bancas|profissoes|orgaos|anos` — listas
  para os combos (mesma sessão/headers).
- **Download é público**: `https://cdn.tecconcursos.com.br/arquivos/{uuid}`
  (S3, sem login). Nome/extensão reais vêm no `content-disposition` — pode ser
  `.zip`, não só `.pdf`.
- A busca já devolve os arquivos de cada concurso; a página individual do
  concurso só é necessária como fallback (âncoras `icone-download-*` no HTML
  logado).

## Arquitetura

Segue os padrões já em produção: novo `kind` no ledger do scraper + endpoint
interno de import no backend + tela admin com React Query.

### Scraper (`services/scraper`)

1. **Ledger** (`app/tasks/ledger.py`): `kind='concursos'` em `tc_jobs`
   (índice único parcial `uq_tc_jobs_active_concursos` por `external_id` =
   hash dos filtros) + tabela nova `tc_concurso_units` (1 unit por
   `concurso_id` externo; colunas padrão: status, attempts, block_reason,
   blocked_until, leased_until + `payload JSONB` com o item da busca).
2. **Descoberta** — task `descobrir_concursos(job_id, filtros)`
   (`app/tasks/concursos.py`): pagina `busca.pagina=1..totalPages` com
   `TcClient` (throttle humano, relogin automático em `SessionExpired`,
   cooldowns padrão 401/452). Para cada `concursos[]` de cada item, upsert de
   unit com payload (edital + concurso + arquivosPorTipo). Conta TC: task
   nova `concurso` em `TC_ACCOUNT_TASKS` (`auth.py`).
3. **Download** — task `coletar_arquivos_concurso(job_id, concurso_id)`:
   para cada arquivo do payload, se o objeto ainda não existe no MinIO,
   baixa de `cdn.tecconcursos.com.br/arquivos/{uuid}` **sem sessão TC**
   (httpx cru + pequeno delay 1–3 s), sobe para o bucket **`studia-pdfs`**
   (privado, mesmo do backend) com chave **`concursos/{uuid}{ext}`** (chave
   por uuid ⇒ arquivos compartilhados entre concursos são armazenados uma
   única vez); extensão/content-type do `content-disposition`. Depois `POST
   {backend}/api/q/concursos/importar` com `X-Internal-Token` (metadados +
   object keys). Retry/blocked/done como `tc_comentario_units`.
4. **Endpoints**: `POST /enqueue/concursos {filtros: [{id, tipo}]}`;
   `GET /tc/concursos/filtros` (bancas + profissões via sessão, para os
   combos da UI); tick no supervisor (`_queue_supervisor_loop`) para
   auto-alimentar as units.

### Backend (`backend/`)

1. **Models** (`models.py` + migration Alembic):
   - `TcConcurso`: `id`, `concurso_id_externo` (unique), `edital_id_externo`,
     `nome_completo`, `url_concurso`, `banca_nome`, `orgao_sigla`,
     `orgao_nome`, `edital_nome`, `ano`, `data_aplicacao`, `escolaridade`,
     `raw_json`, `criado_em`, `atualizado_em`.
   - `TcConcursoArquivo`: `id`, `concurso_id` (FK), `tipo` (string do TC:
     `EDITAL`, `PROVA_OBJETIVA`, …), `arquivo_id_externo`, `uuid`,
     `nome_arquivo`, `minio_object_key`, `content_type`, `tamanho_bytes`,
     `baixado_em`; `UniqueConstraint(concurso_id, arquivo_id_externo)`.
2. **Endpoints** (`q_router.py`, admin exceto onde indicado):
   - `POST /api/q/concursos/coletar {filtros}` → proxy `POST
     {SCRAPER_URL}/enqueue/concursos` (202, timeout curto).
   - `GET /api/q/concursos/jobs` → progresso agregando `tc_jobs` +
     `tc_concurso_units` (padrão de `GET /api/q/coletar/jobs`).
   - `GET /api/q/concursos/filtros` → proxy do scraper (combos).
   - `GET /api/q/concursos` → lista coletados (+ arquivos, busca textual).
   - `GET /api/q/concursos/arquivo/{arquivo_id}` → **stream** do MinIO com
     `content-disposition` do nome original (padrão imagem do fórum; nunca
     redirect pro host interno `minio:9000`).
   - `POST /api/q/concursos/importar` → `Depends(require_user_or_service)`
     (aceita `X-Internal-Token`); upsert idempotente de concurso + arquivos.

### Frontend (`fontend/app/q/concursos/page.tsx`)

- Guarda de admin (padrão `/q/coletar`), React Query obrigatório.
- **Coleta**: combos Banca e Formação (dados de `/api/q/concursos/filtros`,
  operação lenta ⇒ `BrandLoader`), botão "Coletar" → card de progresso com
  polling condicional 15 s (padrão `/q/coletar`, pausar/retomar).
- **Listagem**: tabela dos concursos coletados (`Skeleton` no formato final
  durante `isPending`; nada de estado-vazio enquanto job ativo): nome
  completo, órgão, banca, ano, data de aplicação; chips por arquivo
  (Edital / Prova objetiva / Prova discursiva / Gabarito) → clique baixa via
  `GET /api/q/concursos/arquivo/{id}`; ícone de link externo →
  `https://www.tecconcursos.com.br/concursos/{urlConcurso}`.
- Proibido "TC"/"tec" visível na UI (regra do projeto) — rotular como
  "Concursos" / "fonte externa".

## Casos de borda e decisões

- **Concurso sem arquivo** (ex.: ALECE/2026 só tem edital): unit conclui com
  o que houver; chips ausentes não renderizam.
- **Arquivo compartilhado** entre concursos (mesmo uuid): chave MinIO por
  uuid deduplica o binário; cada concurso mantém sua linha de metadados.
- **ZIP vs PDF**: guardar `content_type`/extensão reais; o chip baixa
  qualquer formato.
- **Recoleta**: reenfileirar os mesmos filtros atualiza (upsert) concursos e
  baixa apenas arquivos novos (objeto já existente no MinIO é pulado).
- **Sessão TC**: só a descoberta consome sessão (1 request/página de busca,
  ~10 páginas para 49 concursos); downloads não tocam a conta.
- **Anti-bloqueio**: throttle humano do `TcClient` na descoberta; delay
  1–3 s entre downloads do CDN.

## Testes

- Backend (pytest): upsert idempotente do `/importar` (dedup por
  `arquivo_id_externo`), stream do arquivo, drift Alembic.
- Scraper (pytest): parse da resposta da busca (fixture JSON real),
  montagem de units, chave MinIO por uuid.
- Smoke real: coletar IDECAN + Engenharia Civil (49 concursos) em prod e
  conferir contagem de arquivos no MinIO e na tela.
