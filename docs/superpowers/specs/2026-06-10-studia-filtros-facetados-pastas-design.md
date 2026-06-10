# Filtros facetados completos + hierarquia "Minhas pastas" (estilo TC)

**Data:** 2026-06-10
**Contexto:** `/q/filtrar` só renderiza "Matéria e assunto" e "Banca"; as demais
categorias mostram placeholder. Não existe navegação de cadernos criados —
usuário quer a hierarquia do TecConcursos: Estudo → Minhas pastas → Pasta →
Caderno → Questão, com acesso rápido aos cadernos.

## Realidade dos dados (verificada no banco, 69.851 questões)

| Categoria TC | Fonte disponível | Decisão |
|---|---|---|
| Órgão e cargo | Meili já indexa `orgao`, `cargo` | Só UI |
| Ano | Meili já indexa `ano` | Só UI |
| Área (Carreira) | `Cargo.area` (3169/4881 preenchidos) | Indexar `area` |
| Formação | `raw_json.concursoEspecialidade` (58+ valores) | Indexar como `formacao` |
| Escolaridade | Não vem na API de questões do TC (0 registros) | Indexar campo (null) + UI com estado vazio honesto |
| Região | Idem (Orgao.regiao = 0) | Idem |
| Favoritas | Não existe | Novo modelo + toggle |
| Enunciados | Meili `q` (searchable enunciado) já suportado | UI: busca textual |
| Opções | `status` indexado (ATIVA/ANULADA/DESATUALIZADA) | UI: remover anuladas/desatualizadas |

## Frente 1 — Filtros

### Backend
- `meili_index.py`: documento ganha `area` (Cargo.area, fallback
  `raw_json.concursoArea`), `formacao` (`raw_json.concursoEspecialidade`
  normalizado — remove aspas, descarta "Sem Especialidade"), `escolaridade`
  (Cargo.escolaridade), `regiao` (Orgao.regiao). `FILTERABLE` += os 4 campos.
- `q_router.py`:
  - `DEFAULT_FACETS` += os 4 campos.
  - `_to_meili_filter`: chave especial `status_excluir: ["ANULADA", ...]` vira
    `status != "ANULADA"`. Demais chaves seguem genéricas (OR dentro, AND entre).
  - `CountReq`/`SearchReq`/`GerarCadernoReq` ganham `favoritas: bool = False`;
    quando true, busca IDs favoritados no PG e injeta `id IN [...]` no filtro
    Meili (sem favoritas → curto-circuito com total 0). Abordagem por request
    (não indexa flag no Meili) — sempre consistente, sem reindex no toggle.
- `models.py`: `QuestaoFavorita(id, questao_id FK unique, created_at)` —
  single-tenant, sem usuario_id (padrão do projeto).
- Endpoints novos: `GET /api/q/favoritas` → `{ids: [...]}`;
  `POST /api/q/questoes/{id}/favoritar` → toggle, `{favorita: bool}`.
- Reindex completo via `sync_meili.py` após deploy.

### Frontend (`/q/filtrar`)
- Renderizador genérico de facetas por categoria: Banca→`banca`;
  Órgão e cargo→`orgao`+`cargo` (duas seções); Ano→`ano` (desc);
  Área→`area`; Escolaridade→`escolaridade`; Formação→`formacao`;
  Região→`regiao`. Busca local filtra itens; categoria sem dados mostra
  mensagem honesta ("sem dados na base atual").
- "Favoritas": toggle "apenas favoritas".
- "Enunciados": campo de palavras-chave → `q` do Meili.
- "Opções": checkboxes remover anuladas/desatualizadas (`status_excluir`);
  atalhos do painel direito ligados ao mesmo estado.
- Rádio do topo ligado: Objetivas→`tipo IN (MULTIPLA_ESCOLHA, CERTO_ERRADO)`,
  Discursivas→`tipo = DISCURSIVA` (inéditas tratado como todas por ora —
  flag não indexada).
- Chips do painel direito generalizados para todos os campos.
- Rodapé: campo "Pasta" (datalist com pastas existentes + texto livre) enviado
  no `POST /api/q/cadernos`.

## Frente 2 — Minhas pastas

`CadernoQuestoes.pasta` continua string (sem tabela Pasta — YAGNI; a
materialização de guias já grava `pasta = guia.nome`). Pasta null/vazia →
"Sem classificação", como no TC.

### Backend
- `GET /api/q/pastas` → `[{pasta, cadernos, total_questoes}]` (GROUP BY pasta).
- `GET /api/q/cadernos?pasta=X` → filtra por pasta (`""` → sem classificação).

### Frontend
- Nova página `/q/cadernos`: sem query param lista pastas (ícone, nome,
  N cadernos); com `?pasta=X` lista cadernos da pasta (nome, total, data,
  "Carregar desempenho" sob demanda via endpoint de estatísticas). Breadcrumb
  Estudo › Minhas pastas › {pasta}. Pasta via query string (não rota dinâmica)
  porque nomes contêm `/`.
- Sidebar: item "Minhas Pastas" → `/q/cadernos`, abaixo de Questões.
- `/q/caderno/[id]`: breadcrumb vira navegável — Minhas pastas → `/q/cadernos`,
  {pasta} → `/q/cadernos?pasta=...`; estrela ⭐ no header da questão para
  favoritar (estado inicial via `GET /api/q/favoritas`).

## Testes
- `_to_meili_filter` (status_excluir, IN, genérico) — unit.
- `GET /api/q/pastas` agrupamento + `GET /api/q/cadernos?pasta=` — via fixture
  sqlite existente.
- Toggle favoritar — via fixture.

## Fora de escopo
- Escolaridade/Região com dados reais (exige outra fonte TC — ex. API de
  concursos; campos já ficam indexados e a UI pronta).
- Tabela Pasta com CRUD (renomear/excluir) — string cobre a navegação.
- "Objetivas (inéditas)" real (`questaoAdaptadaOuInedita` não indexado).
