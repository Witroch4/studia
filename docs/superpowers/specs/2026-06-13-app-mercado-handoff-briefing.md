# Briefing — App de Mercado (Engine + Screener · IBKR read-only) — handoff p/ outro agente

> Cole isto como prompt inicial para o agente que vai construir o app. Ele assume
> sem contexto prévio. Os arquivos referenciados estão na máquina do usuário e
> podem ser lidos pelos caminhos absolutos indicados.

## Sua missão

Projetar e implementar o **v1** de um app de **análise fundamentalista de ações**
(foco B3, extensível). O coração é um **engine de valuation determinístico**
portado de uma planilha já validada. v1 = **Engine + Screener**; integração
**IBKR somente leitura**. App **single-user**: 1 usuário comum + 1 admin (o dono).

## Repo

**Repo NOVO e separado.** Não tem ligação com o studIA — nasce limpo sob o padrão
WitDev single-user. Compartilha **só infra** (rede docker `minha_rede`).

## Padrão arquitetural OBRIGATÓRIO (WitDev single-user)

Leia na íntegra:
`/home/wital/studia/docs/superpowers/specs/2026-06-13-studia-padronizacao-arquitetural.md`

Resumo dos pontos não-negociáveis:

- **Backend:** FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + **Alembic** (única
  autoridade de schema; nada de auto-ALTER).
- **Banco:** PostgreSQL + pgvector — **database próprio** na instância
  compartilhada (`minha_rede`). Sem schemas multi-tenant.
- **Async:** TaskIQ sobre **NATS** (broker) + **Redis** (result/cache/locks/
  schedules). Prefixos por app.
- **Frontend:** Next 16 App Router + React 19 + Tailwind 4 + **React Query v5**.
- **Auth:** Better Auth (Next) + **handoff → JWT em cookie HttpOnly** no FastAPI.
  Validação **stateless, ZERO I/O no banco por request**. **SEM bearer/
  Authorization** (capturável → vira API de scraper). CSRF nas mutações. 1 admin
  = dono.
- **IA:** **só via LLM proxy WitDev** (LiteLLM). Proibido SDK de provider direto.
- **Backend organizado em `domains/`.** NÃO multi-tenant.

> O scaffolding pode usar a skill `witdev-project-setup` (Next 16 + Postgres/
> pgvector + Redis + Docker + scripts dev.sh/build.sh). **Atenção:** o ORM é
> SQLAlchemy + Alembic (não Prisma) — siga o spec, não o default da skill.

## O engine de valuation (coração — portar da planilha)

Modelo de **banco por valor patrimonial**. Entrada por ticker: VPA (BVPS), LPA
(EPS), ROE, payout, P/VP, preço, nº de ações (derivado do aporte). Projeção de N
anos (default 10) por **cenário** {Conservador, Base, Otimista}, cada um com
(ROE sustentável, payout, P/VP de saída):

```
VPA_t          = VPA_{t-1} × (1 + ROE×(1−payout))     # lucro retido compõe o PL
LPA_t          = ROE × VPA_{t-1}
DPA_t          = payout × LPA_t
dividendo_t    = DPA_t × ações
preço_saída    = P/VP_saída × VPA_ano_N
valor_final    = preço_saída × ações + Σ dividendo_t
retorno_total  = valor_final / aporte − 1
CAGR           = (valor_final / aporte)^(1/N) − 1
# decompor: dividendos/capital  e  valorização de preço
```

**Sensibilidade:** matriz de `valor_final` e `CAGR` variando **ROE × P/VP_saída**
(payout fixo). Tudo **nominal e bruto** (antes de IR; JCP sofre IRRF → registrar
como nota). Base **sem reinvestimento** de dividendos (deixar reinvestimento como
opção futura).

Valide o engine reproduzindo exatamente os números da planilha de referência
(cenário Base BAZA3: dividendos 10a ≈ R$74.090, valor final ≈ R$199.385,
CAGR ≈ 14,83%).

## Dados

- **Fundamentais:** scrapers de `dadosdemercado.com.br` e `visnoinvest.com.br`
  (fontes da planilha). **Persistir snapshot versionado por data.**
- **Dividendos/JCP:** histórico de eventos (tipo, valor/ação, data-com, data-ex,
  pagamento) — dadosdemercado.
- **Splits/grupamentos:** ajustar comparabilidade histórica.
- **Mercado (IBKR Web API REST, OAuth no backend, SOMENTE LEITURA):**
  `search_contracts` (resolver e **cachear** `contract_id`), `get_price_snapshot`
  (cotação), `get_price_history` (OHLCV). Opcional: `get_account_*` p/ sobrepor
  carteira real. **Respeitar rate limit 10 req/s** (token bucket + cache),
  keep-alive de sessão. **Sem criar ordens no v1.**
  - Atalho de prototipagem: já existe um conector MCP IBKR (16 ferramentas,
    `mcp__claude_ai_Interactive_Brokers_IBKR__*`) — útil pra validar leitura
    antes de montar OAuth próprio.

## Modelo de dados (sugerido)

`ticker` · `fundamentals_snapshot` (por data) · `valuation_run` (inputs +
cenários + resultados, versionado) · `scenario` · `sensitivity_grid` ·
`dividend_event` · `split_event` · `watchlist` · `alert` (data-ex) · `user`.

## Funcionalidades v1

- Cadastrar ticker → buscar fundamentos → rodar engine → telas **Resumo /
  Histórico / Valuation / Sensibilidade** (espelha a planilha, mas vivo e
  versionado por data).
- **Watchlist** multi-papel; ranking por **CAGR-base** e **margem de segurança**
  (P/VP atual vs P/VP justo implícito).
- **Alertas de data-ex** (cron via scheduler) — comprar pós-ex perde o provento.
- **Backtest** do engine contra o histórico realizado (a planilha já tem o real).

## Fora do v1 (fases seguintes)

- **Fase 2 — IA:** leitura fundamentalista gerada via LLM proxy, com números
  **cravados pelo engine** (não alucina valuation); RAG sobre RI/CVM/fatos
  relevantes.
- **Fase 3 — IBKR transacional:** camada de **instrução de ordem**
  human-in-the-loop (monta ordem → deep-link IBKR pra confirmar); carteira real.

## Materiais para ler (na máquina do usuário)

- Relatório IBKR: `/home/wital/studia/Relatório: Construindo uma Solução sobre a API da Interactive Brokers (IBKR).md`
- Planilha modelo: `/home/wital/studia/BAZA3_analise_fundamentalista_valuation.xlsx`
  (abas: Resumo, Inputs, Historico, Dividendos, Valuation 10a, Sensibilidade,
  Jul-2007 Boom, Fontes)
- Padrão arquitetural: `/home/wital/studia/docs/superpowers/specs/2026-06-13-studia-padronizacao-arquitetural.md`

## Workflow obrigatório

1. **brainstorming** skill — alinhar o escopo fino do v1 com o usuário (não pule).
2. Escrever **spec de design** em `docs/.../specs/`.
3. **witdev-project-setup** skill — bootstrapar o repo novo (com a ressalva do
   ORM acima).
4. **writing-plans** → implementar com **TDD**.
5. Respeitar o ciclo commit/push do projeto.

## Restrições duras

- **Não é recomendação financeira** — o app é modelo de cenários. Manter
  disclaimers (a planilha tem aba de limitações).
- **Human-in-the-loop** para qualquer ordem (fases futuras).
- Conta IBKR: **começar em paper**.
