# Cronograma de Estudo por Caderno — Design

**Data:** 2026-06-15
**Status:** Aprovado (brainstorming) → pronto para plano de implementação
**Modelo de referência:** `docs/cronograma_ALECE_engenharia_civil_IDECAN_876_questoes.xlsx`

## 1. Contexto e objetivo

O studIA já tem cadernos de questões do TecConcursos (TC), com progresso real
do usuário rastreado por questão (tabela `Resolucao`: questão, acerto, tempo,
data). A planilha ALECE é um cronograma de estudos muito completo (8 abas:
Painel de KPIs, Cronograma diário, Controle_Questoes, Discursivas, Simulados,
Resumo_Semanal, Pesos, Referencias) — porém **manual**: exige preencher 876
linhas à mão para saber se está adiantado ou atrasado.

**Objetivo:** uma feature nativa no app que gera, a partir de um caderno, um
cronograma de estudos **vivo** — o plano dia-a-dia cruzado automaticamente com
o progresso real do usuário — e que também permite **exportar uma planilha
`.xlsx`** no estilo do modelo ALECE.

## 2. Decisões (brainstorming)

| Tema | Decisão |
|---|---|
| Entregável | Feature integrada no app studIA (não script avulso). |
| Consumo | **Página viva** no app **+ botão de export `.xlsx`**. |
| Ritmo | **Automático pela data da prova** (buffer de reta final, dias de folga configuráveis). |
| Blocos além do núcleo | Revisão espaçada das erradas (auto), Discursivas (temas via IA), Simulados. |
| Arquitetura/persistência | **A) Config enxuta + cálculo sob demanda.** Salva só a config; metas/saldo/revisões são calculados na hora a partir da config + `Resolucao`. Persiste à parte só o que não recalcula: discursivas (IA) e resultados de simulado. |
| Dias de folga | Cada dia da semana é um **toggle**; default = só domingo de folga (sábado conta como dia útil). |
| Carga | **Uniforme** entre os dias ativos (sem reforço forçado no sábado). |
| Recalcular | Botão **"Recalcular automático"**: redistribui as questões **restantes** (não resolvidas) pelos dias úteis que sobram até a prova (rebaseline a partir de hoje). |

**Fora de escopo (YAGNI):** composição por matéria + pesos do edital; edição
manual dia-a-dia; notificações/lembretes; mais de um cronograma por caderno.

## 3. Núcleo: algoritmo do plano (determinístico, no backend)

Entradas: `data_inicio`, `data_prova`, `total` (= `CadernoQuestoes.total`),
`dias_folga` (lista de weekdays, ex. `[6]` = domingo), `buffer_dias`.

1. Enumera os dias de `data_inicio` até `data_prova`. Dias cujo weekday está em
   `dias_folga` recebem carga 0.
2. `fim_1volta = data_prova − buffer_dias`. Os dias **úteis** (não-folga) entre
   `data_inicio` e `fim_1volta` formam a fase **"1ª volta – resolver questões"**.
3. Distribui as `total` questões uniformemente pelos dias úteis da 1ª volta:
   `carga = floor(total / n)`, e o resto (`total mod n`) é somado +1 nos
   primeiros/últimos dias até fechar exatamente `total`.
4. Dias da fase **buffer** (entre `fim_1volta` e `data_prova`): questões novas =
   0, fase "Buffer – revisão, erradas e simulados". O último dia é **"PROVA"**.
5. `meta_acumulada[d] = Σ carga até o dia d`.

### Saldo vivo (lido do progresso real)

- `acumulado_real[d]` = `COUNT(DISTINCT questao_id)` em `Resolucao` filtrado por
  `caderno_id` + `usuario_uid`, agrupado por `date(created_at)`, acumulado.
- `saldo = acumulado_real_até_hoje − meta_acumulada_até_hoje`
  (positivo = adiantado, negativo = atrasado).

### KPIs do Painel (espelham a aba Painel do modelo)

`total`, `resolvidas` (distinct), `acertos`, `erros`, `% conclusão`,
`% acerto`, `questões restantes`, `dias úteis restantes`,
`questões/dia necessárias` (`ceil(restantes / dias_uteis_restantes)`),
`saldo vs meta`.

### Recalcular automático (rebaseline)

`PUT` que ancora o plano em **hoje**: `questoes_restantes = total − resolvidas`,
redistribui essas restantes pelos dias úteis de hoje até `fim_1volta`. Guarda
`rebaseline_em` (Date) na config; o cálculo passa a usar `rebaseline_em` como
ponto de partida da curva de meta para os dias futuros (os dias passados mantêm
a meta original já cumprida/perdida). Útil ao atrasar ou mudar a data da prova.

## 4. Modelo de dados (3 tabelas — Alembic, padrão do projeto)

**`cronogramas`**
- `id` PK; `usuario_uid` (String 64, index); `caderno_id` (FK
  `cadernos_questoes.id`, CASCADE)
- `data_inicio` (Date), `data_prova` (Date), `rebaseline_em` (Date, nullable)
- `dias_folga` (JSON, ex. `[6]`), `buffer_dias` (Integer, default 21)
- `incluir_revisao` / `incluir_discursivas` / `incluir_simulados` (Boolean)
- `discursivas_por_semana` (Integer, default 2)
- `created_at`, `updated_at`
- **Unique(`usuario_uid`, `caderno_id`)** — um cronograma por caderno por usuário.

**`cronograma_discursivas`**
- `id` PK; `cronograma_id` (FK CASCADE); `data` (Date)
- `tema` (Text), `tipo` (String, ex. "Treino 20 linhas"/"Simulado discursivo"),
  `qtd` (Integer)
- `status` (String: Pendente/Feita/Rever/Reescrita), `nota` (Numeric, nullable),
  `reescrita` (Boolean), `observacoes` (Text, nullable)

**`cronograma_simulados`**
- `id` PK; `cronograma_id` (FK CASCADE); `data` (Date)
- `tipo` (String), `objetivas_planejadas` (Integer), `meta_objetiva` (Integer)
- `resultado_objetiva` (Integer, nullable), `discursiva_planejada` (Integer)
- `resultado_discursiva` (Numeric, nullable), `observacoes` (Text, nullable)

> **Revisão espaçada não vira tabela.** É derivada de `Resolucao`: cada questão
> errada (`acertou = false`) em `created_at` gera revisões em D+1, D+7, D+21.
> "Revisar hoje" = revisões vencendo hoje cuja questão não foi re-acertada depois.

## 5. Endpoints (em `backend/q_router.py`, prefixo `/api/q`)

| Método | Path | Função |
|---|---|---|
| `POST` | `/cadernos/{id}/cronograma` | Cria config; dispara geração de discursivas (IA) e marcos de simulado. |
| `GET` | `/cadernos/{id}/cronograma` | Config + plano calculado + KPIs + saldo + "revisar hoje" + discursivas + simulados. |
| `PUT` | `/cadernos/{id}/cronograma` | Reconfigura/recalcula (inclui o "Recalcular automático" / rebaseline). |
| `DELETE` | `/cadernos/{id}/cronograma` | Remove o cronograma. |
| `PATCH` | `/cadernos/{id}/cronograma/discursivas/{did}` | Atualiza status/nota/reescrita. |
| `PATCH` | `/cadernos/{id}/cronograma/simulados/{sid}` | Registra resultado. |
| `POST` | `/cadernos/{id}/cronograma/discursivas/regenerar` | Novos temas via IA. |
| `GET` | `/cadernos/{id}/cronograma/export.xlsx` | Baixa a planilha. |

Autorização: o cronograma pertence ao `usuario_uid` do dono da sessão (mesmo
padrão de `Resolucao`/`CadernoSalvo`). Validações: `data_prova > data_inicio`;
`data_prova` no futuro; total > 0; avisar quando `questões/dia` ficar muito alto.

## 6. IA — discursivas (usa `backend/gemini_service.py`, já existente)

Na criação (se `incluir_discursivas` e a prova tiver discursiva), uma chamada
Gemini recebe as **matérias/assuntos reais do caderno** (derivados das questões
via `materia_id`/`assuntos`) e devolve ~15–20 temas de caso prático. Os temas
são distribuídos nos dias configurados para treino (ex. terças/quintas, conforme
`discursivas_por_semana`) e persistidos em `cronograma_discursivas`, editáveis.
**Falha graciosa:** Gemini indisponível → o cronograma é criado sem discursivas e
o usuário regenera depois pelo botão (não bloqueia a criação).

## 7. Export `.xlsx` (openpyxl — nova dependência no backend)

Endpoint `GET …/export.xlsx` monta um workbook reproduzindo as abas
**Painel, Cronograma, Discursivas, Simulados, Resumo_Semanal** com fórmulas e
estilo no padrão do modelo ALECE. Bônus além do modelo: aba **Controle_Questoes**
preenchida com as **questões reais do caderno** e o `Status`/`Resultado` já
marcados a partir de `Resolucao` (a planilha manual exige digitar isso).
Adicionar `openpyxl` ao `backend/requirements.txt`.

## 8. Frontend

**Página nova:** `fontend/app/q/caderno/[id]/cronograma/page.tsx`.
- **Sem cronograma:** tela de criação — data da prova (obrigatória), data início
  (default hoje), 7 toggles de dias da semana (default: domingo desligado),
  buffer (default 21 dias) e toggles dos blocos.
- **Com cronograma:** dashboard reusando o DS (`StatCard`, `ProgressBar`, tokens,
  padrão de cards/tabs). Seções:
  - faixa de **KPIs** (% conclusão, saldo adiantado/atrasado, questões/dia, dias até a prova);
  - **timeline diária** (data · fase · meta · feitas reais · saldo, com "hoje" destacado);
  - painel **"Revisar hoje"** (erradas agendadas);
  - **Discursivas** (lista com status/nota editáveis);
  - **Simulados** (marcos + registrar resultado);
  - botões **Baixar .xlsx**, **Recalcular automático** e **Reconfigurar**.

**Pontos de entrada:**
- Botão **"Cronograma"** no player do caderno (`/q/caderno/[id]`).
- Item **"Planejamento"** da sidebar (hoje → `/em-breve`) passa a listar os
  cadernos com cronograma ativo.

Chamadas via `apiFetch()` (`fontend/lib/api.ts`), padrão JWT/CSRF existente.

## 9. Edge cases

- `data_prova` ≤ `data_inicio` ou no passado → erro de validação na criação.
- Total alto / poucos dias → carga/dia alta; UI avisa mas permite.
- Caderno sem matéria definida → IA recebe fallback genérico de temas.
- Prova sem discursiva → usuário desliga o bloco `incluir_discursivas`.
- Mesma questão resolvida várias vezes → conclusão usa `COUNT(DISTINCT questao_id)`.
- Gemini fora do ar → cria sem discursivas, regenerar depois.

## 10. Entrega (workflow obrigatório do projeto)

Migrations Alembic + `db_prepare` no startup; ao final: commit + push +
`./build.sh` (deploy prod) + worktree limpo, conforme `CLAUDE.md`.
