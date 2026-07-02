# Mapa da Aprovação — Design

**Data:** 2026-07-02
**Status:** Aprovado pelo usuário (brainstorming em sessão)

## Visão

O Mapa da Aprovação fecha o ciclo completo do concurseiro dentro do studIA:
**edital → cargo → matérias → questões da banca → cronograma até a prova →
revisão espaçada**. O usuário escolhe um concurso já coletado do TC (ex:
IDECAN), a IA lê o edital em PDF, apresenta os cargos encontrados, o usuário
escolhe o seu (ex: Engenheiro Civil) e nasce o Mapa: timeline de eventos do
edital, edital verticalizado (checklist matéria → assunto), cadernos
automáticos com questões da banca e data da prova alimentando o gerador de
cronograma existente.

## Decisões de produto (fixadas com o usuário)

| Decisão | Escolha |
|---|---|
| Acesso | Catálogo de concursos visível a todo usuário logado; **criar Mapa é PRO** (`acesso_pro_ativo`). Coleta continua admin-only. |
| Escopo v1 | Mapa completo **incluindo match de questões** (cadernos automáticos) e integração com o cronograma. |
| Interação IA | **Wizard com extração estruturada** (não chat). Uma extração por concurso, cacheada e compartilhada. |
| Nome | **Mapa da Aprovação**. |
| LLM | **Padrão: proxy LiteLLM da WitDev** (passthrough `/gemini`, mesmo caminho de `gemini_service._get_client()`). Batch API é exceção (só aulas) — aqui usa `generate_content` normal, pois o usuário espera na tela. |

## Abordagem escolhida

**Extração compartilhada por concurso.** O edital é extraído uma única vez e
cacheado em tabela; todos os usuários reusam. O primeiro usuário espera ~1-2
min (BrandLoader), os demais têm resposta instantânea. Custo: centavos por
concurso, uma vez.

Alternativa descartada: pré-extração automática na coleta (pagaria LLM por
centenas de editais sem uso). Pode virar botão admin "pré-extrair" no futuro.

## Modelo de dados (3 tabelas novas, via Alembic)

### `edital_extracao` — 1 por concurso
- `id` PK
- `concurso_id` FK → `tc_concursos.id` (**unique**, ondelete CASCADE)
- `status`: `pendente | processando | concluido | erro`
- `dados` JSON (schema abaixo)
- `modelo_usado` (alias do catálogo LLM)
- `prompt_versao` (int) — permite re-extração quando o prompt evoluir ou o
  edital for retificado
- `erro_msg` nullable
- `criado_em` / `atualizado_em`

### `mapa_aprovacao` — por usuário
- `id` PK
- `usuario_uid` (Better Auth "user".id, index)
- `concurso_id` FK → `tc_concursos.id`
- `extracao_id` FK → `edital_extracao.id`
- `cargo_nome` (string)
- `cargo_dados` JSON — snapshot do cargo escolhido (vagas, salário,
  requisitos, etapas, distribuição de questões)
- `criado_em`
- Unique `(usuario_uid, concurso_id, cargo_nome)`

### `mapa_item` — verticalização (1 linha por assunto)
- `id` PK
- `mapa_id` FK → `mapa_aprovacao.id` (ondelete CASCADE)
- `materia_nome` (do edital), `assunto_texto`, `ordem`
- `status`: `nao_visto | estudando | dominado`
- `materia_id` FK → `materias.id` nullable (resultado do match)
- `caderno_id` FK → `cadernos_questoes.id` nullable (caderno automático da
  matéria; repetido nos itens da mesma matéria)

## Schema JSON da extração (structured output do Gemini)

```json
{
  "concurso": {
    "orgao": "...", "banca": "...", "taxa_inscricao": "...",
    "data_prova": "YYYY-MM-DD"
  },
  "eventos": [
    {"titulo": "...", "data_inicio": "YYYY-MM-DD", "data_fim": null,
     "tipo": "inscricao|isencao|prova|recurso|resultado|homologacao|outro"}
  ],
  "cargos": [
    {"nome": "...", "escolaridade": "...", "vagas": 0, "salario": "...",
     "requisitos": "...", "jornada": "...",
     "conteudo_programatico": [
       {"materia": "...", "assuntos": ["...", "..."]}
     ],
     "etapas": [{"nome": "...", "carater": "eliminatorio|classificatorio|ambos"}],
     "distribuicao_questoes": [{"materia": "...", "quantidade": 0, "peso": 1}]
    }
  ]
}
```

Campos ausentes no edital ficam `null` — o prompt instrui a nunca inventar.

## Fluxo LLM (2 chamadas, ambas via proxy WitDev)

1. **Extração do edital** — task Taskiq no `worker.py` (padrão de
   `processar_aula`): baixa o PDF do MinIO (`minio_object_key` do
   `TcConcursoArquivo` tipo `EDITAL`), chama nova função
   `gemini_service.extrair_edital_estruturado(pdf_bytes, modelo)` com
   `generate_content` + `response_schema` (JSON). PDF inline se couber no
   limite; senão upload via `client.files` (também pelo passthrough).
   Nova setting `llm.mapa_edital` no `llm_registry` (aparece no painel admin
   "Modelos de IA"), default `gemini-3-flash-preview`.
2. **Match de matérias** — na criação do Mapa, chamada curta só-texto:
   entrada = matérias do conteúdo programático do cargo + lista de
   `Materia.nome` existentes no banco; saída = de-para
   `materia_edital → materia_banco | null`. Determinística o suficiente para
   JSON schema simples.

## Cadernos automáticos (match de questões)

Após o match, para cada matéria com correspondência:
1. Resolver `banca_id` pelo nome da banca do concurso (`bancas.nome` ~ilike
   `banca_nome` do `TcConcurso`).
2. Contar/selecionar `Questao` com `banca_id` + `materia_id` (excluindo
   anuladas, mesmo critério do cronograma), ordenadas das mais recentes para
   as mais antigas (por prova/ano), com **cap de 500 questões por caderno** —
   o preview mostra o total encontrado e o quanto entrou.
3. Criar `CadernoQuestoes` reusando a lógica interna do `POST /cadernos`
   (`owner_uid` = usuário, `question_ids`, `filtros` documentando origem),
   nome "🗺️ {orgao_sigla} — {matéria}", `pasta` = nome do concurso.
4. Gravar `caderno_id` nos `mapa_item` da matéria.

Matéria sem match ou sem questões: fica na verticalização sem caderno — o
fluxo nunca quebra por falta de questões.

## Endpoints

| Rota | Descrição |
|---|---|
| `GET /api/q/concursos/catalogo` | Usuário logado (não-admin): concursos **com arquivo EDITAL**, busca + paginação. Reusa `concursos_router`. |
| `POST /api/q/mapas/extrair` `{concurso_id}` | 202; idempotente (se `concluido`, retorna direto; se `processando`, informa). Dispara task no worker. Qualquer usuário logado pode disparar (o resultado é compartilhado). |
| `GET /api/q/mapas/extracao/{concurso_id}` | Polling de status + dados quando concluído. |
| `POST /api/q/mapas` `{concurso_id, cargo_nome}` | **Gate PRO.** Cria mapa + itens + match + cadernos. |
| `GET /api/q/mapas` | Meus mapas (para `/q/mapa` e para o pré-preenchimento do cronograma). |
| `GET /api/q/mapas/{id}` | Detalhe completo (eventos, verticalização, cadernos, data da prova). |
| `PATCH /api/q/mapas/{id}/itens/{item_id}` | Atualiza `status` do checklist. |
| `DELETE /api/q/mapas/{id}` | Remove o mapa (cadernos criados permanecem — são do usuário). |
| `POST /api/q/mapas/extracao/{concurso_id}/reextrair` | Admin: força re-extração (edital retificado / prompt novo). |

Router novo: `backend/mapa_router.py`, prefixo `/api/q/mapas` (catálogo fica
no `concursos_router`). Auth pelo padrão cookie-JWT existente.

## UX / Frontend

- **Sidebar:** entrada "Mapa da Aprovação" → `/q/mapa`.
- **`/q/mapa`** — lista dos meus mapas (cards com countdown) + CTA "Criar
  Mapa". Skeleton na carga (React Query v5, `isPending`).
- **Wizard `/q/mapa/novo`:**
  1. Buscar/escolher concurso no catálogo (busca com debounce, Skeleton).
  2. Extração: `BrandLoader` "studIA está lendo o edital…" com polling de
     `GET /extracao/{id}` (regra rígida de UI: operação lenta = BrandLoader;
     espaço reservado, nada pula na tela).
  3. "Li o edital e encontrei N cargos" — cards de cargo (vagas, salário,
     escolaridade, requisitos).
  4. Preview do Mapa: matérias do cargo, timeline de eventos, "encontrei X
     questões da banca em Y matérias" → botão **Criar meu Mapa** (PRO;
     usuário grátis vê paywall aqui — funil de conversão).
- **Página `/q/mapa/[id]`:** hero com countdown para a prova; timeline
  vertical dos eventos do edital; edital verticalizado (accordion matéria →
  checklist de assuntos com 3 estados, PATCH otimista); coluna/aba com os
  cadernos automáticos e atalho "gerar cronograma".
- Todo data fetching com React Query v5 (`qk.*` novos em
  `fontend/lib/queryKeys.ts`); zero `fetch` cru em `useEffect`.

## Integração com o cronograma

Acoplamento mínimo: o `ConfigForm` do cronograma, quando o caderno pertence a
um Mapa (lookup via `GET /api/q/mapas`), **pré-preenche `data_prova`** com a
data extraída do edital (fallback: `data_aplicacao` do `TcConcurso`). O motor
`cronograma_core.py` não muda.

## Erros e casos-limite

- Extração falha (PDF corrompido, LLM indisponível) → `status=erro` +
  `erro_msg`; wizard mostra estado de erro com retry.
- Edital retificado → re-extração admin; mapas existentes mantêm snapshot
  (`cargo_dados`) — não são reescritos silenciosamente.
- Concurso sem arquivo `EDITAL` → fora do catálogo.
- Edital escaneado (imagem) → Gemini lê nativamente (OCR embutido).
- `data_prova` ausente no edital e no `TcConcurso` → Mapa nasce sem countdown;
  cronograma continua pedindo data manual.
- Usuário grátis → paywall no passo 4 (extração pode acontecer antes — é
  compartilhada e barata).

## Testes

- `backend/tests/test_mapa_router.py` — CRUD, gate PRO, idempotência da
  extração, catálogo (só concursos com edital), permissões.
- Match de matérias com `gemini_service` mockado (fixtures de JSON de
  extração).
- Criação de cadernos automáticos (banca + matéria, exclusão de anuladas).
- Teste de drift de migration continua passando (`test_alembic_no_drift.py`).

## Fora de escopo (fases futuras)

- Priorização inteligente (pesos do edital × incidência histórica da banca).
- Chat "Pergunte ao edital" (RAG sobre o texto extraído).
- Alertas/notificações de prazos (inscrição fechando).
- Pré-extração em massa na coleta (botão admin).
