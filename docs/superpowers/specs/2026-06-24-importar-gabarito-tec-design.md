# Importar desempenho (gabarito) do TecConcursos por caderno

## Problema

Ao importar um caderno do TEC para o studIA, só vêm as **questões** — não o
**desempenho do usuário** (o que ele acertou/errou/deixou em branco lá). O
endpoint de coleta (`ajaxCarregarQuestoesImpressao`) não traz resposta do usuário.

Objetivo: dado um caderno studIA vinculado a um caderno TEC, importar para a
tabela `resolucoes` o histórico de respostas do usuário no TEC, refletindo no
studIA as mesmas estatísticas (resolvidas/acertos/erros) da aba "Gabarito".

## Descoberta da API (confirmada em produção, caderno 94947327)

Endpoint **`GET /api/cadernos/{tc_caderno_id}/gabarito?pagina=N`** (autenticado,
mesma sessão httpx do scraper). Paginado: **30 itens/página fixos** (params de
tamanho são ignorados); a resposta traz `totalPages`, `resultCount`, `currentPage`.

Cada item da `list`:

```json
{"posicaoCaderno":1, "idQuestao":3643888, "alternativa":1, "acertou":true,
 "data":"24/05/2026 00:00:00", "tipoQuestao":"MULTIPLA_ESCOLHA",
 "anulada":false, "favorita":false, "anotada":false}
```

- `idQuestao` ⇒ `Questao.id_externo` no studIA.
- `alternativa` 1–5 ⇒ A–E. Em `CERTO_ERRADO`: 1=CERTO, 2=ERRADO.
- `acertou` bool. **Ausente** (junto com `alternativa`/`data`) ⇒ "Não resolvida".
- `data` "DD/MM/AAAA HH:MM:SS" ⇒ `Resolucao.created_at`.

Notas operacionais:
- Browser headless bate no AWS WAF; **só o caminho httpx** (cookies +
  proxy residencial) passa — por isso a coleta vive no scraper.
- `404 + HTML` = rota inexistente; `401 vazio` = rota real com sessão expirada
  (foi assim que a rota foi confirmada). Sessão expira → `login --headless` do
  próprio scraper renova.

## Componentes

### 1. Scraper — `GET /caderno/{caderno_id}/gabarito`
`app/scrapers/tc_gabarito.py::fetch_gabarito(client, caderno_id)` pagina de 1 até
`totalPages`, agrega e retorna `{caderno_id, total, itens:[...]}`. Exposto em
`app/main.py` via `_with_tc_client(...)` (relogin automático em `SessionExpired`).

### 2. Backend — `POST /api/q/cadernos/{caderno_id}/importar-gabarito`
Body: `{ tc_caderno_id?: int }`. Fluxo:
1. `_caderno_acessivel` (404/403 conforme regra existente).
2. `tc_cid = cad.tc_caderno_id or body.tc_caderno_id`; se ambos nulos → 422.
   Se o caderno é do usuário e não tinha `tc_caderno_id`, grava (vincula p/ re-import).
3. `GET {SCRAPER_URL}/caderno/{tc_cid}/gabarito` (timeout de leitura generoso).
4. Mapa `idQuestao → Questao.id` via `id_externo IN (...)`.
5. Conjunto de `questao_id` já resolvidas pelo usuário neste caderno (qualquer
   origem) → **dedup**: não duplica nem sobrescreve resposta manual. Re-import é
   incremental (insere só as novas resolvidas no TEC).
6. Para cada item resolvido (`acertou` não nulo) e mapeado: insere `Resolucao`
   (usuario_uid, caderno_id, resposta, acertou, created_at da data do TEC).
7. Retorna resumo: `importadas, acertos, erros, ja_tinha, nao_resolvidas_no_tec,
   nao_mapeadas, total_no_tec`.

**Sem migração**: dedup por `(usuario_uid, caderno_id, questao_id)`; idempotente.

### 3. Frontend — botão "Importar do TEC"
Em `app/q/cadernos/page.tsx`, ao lado de "Carregar desempenho": pede ID/URL do
caderno TEC (se ainda não vinculado), chama o endpoint, mostra resumo e recarrega
o desempenho.

## Fora de escopo (v1)
- `favorita`/`anotada` do gabarito (poderiam popular `questoes_favoritas`).
- `tempo_segundos` por questão (o gabarito não fornece; fica `NULL`).
- Job assíncrono: ~30 páginas (<30 s) → chamada síncrona basta.
