# Relatório: Construindo uma Solução sobre a API da Interactive Brokers (IBKR)

**Data:** 13 de junho de 2026
**Escopo:** (1) Documentar tudo o que o conector IBKR já faz no seu sistema e (2) apresentar um blueprint técnico para você construir/expandir sua própria solução sobre a API oficial da IBKR.

---

## 1. Sumário executivo

O conector da Interactive Brokers que já existe no seu sistema expõe **16 ferramentas** organizadas em quatro grupos: **dados de conta** (saldo, posições, ordens, trades, resumo financeiro), **dados de mercado** (cotação em tempo real e histórico OHLCV), **pesquisa e inteligência de empresas/temas** (concorrentes, produtos, geografia, setores, peers) e **instruções de ordem** (criar/listar/excluir instruções que o usuário confirma na plataforma da IBKR).

Um ponto de design importante: o conector **não envia ordens ao mercado automaticamente**. Ele cria uma "instrução" e devolve um link que leva o usuário à plataforma da IBKR para revisar e confirmar. Isso é uma decisão de segurança deliberada — e você deve manter esse padrão na sua própria solução.

**Recomendação de API:** comece pela **IBKR Web API (Client Portal / REST)** com autenticação **OAuth 2.0** (`private_key_jwt`). É a base mais provável do conector atual, é REST/HTTP (fácil de integrar em qualquer linguagem ou backend web) e a IBKR está consolidando todos os produtos web nela. Use a **TWS API** apenas se precisar de trading algorítmico de baixíssima latência ou de tipos de ordem/instrumentos avançados; use **FIX** apenas em volume institucional.

---

## 2. O que o conector da IBKR faz hoje (as 16 ferramentas)

### 2.1 Dados da conta (somente leitura)

| Ferramenta | O que retorna |
|---|---|
| `get_account_balances` | Saldos em caixa e valor de mercado, separados por moeda (uma entrada por moeda). |
| `get_account_summary` | Métricas financeiras da conta: net liquidation value, equity with loan value, fundos disponíveis, poder de compra (buying power), margem inicial e de manutenção, status de day trading. |
| `get_account_positions` | Todas as posições abertas: quantidade, preço, valor de mercado, P&L e custo (cost basis). |
| `get_account_orders` | Lista de ordens ativas: ID, símbolo, lado (compra/venda), tipo, status, quantidade, preço e informação de execução (fills). |
| `get_account_trades` | Snapshot de negócios executados em um período (HOJE, 7/30/60/90 dias, mês/ano até a data, trimestres anteriores). Cada trade traz ID, símbolo, lado, tamanho, preço, comissão e horário. Datas em UTC. |

### 2.2 Dados de mercado

| Ferramenta | O que retorna |
|---|---|
| `get_price_snapshot` | Snapshot em tempo real de um instrumento. Permite pedir muitos campos numa chamada: bid/ask, último preço, variação, fechamento anterior, mark price, dividend yield, volume, open interest (opções/futuros), volatilidade implícita/histórica, performance acumulada (1d/1s/1m/YTD/1a/3a/5a), máximas/mínimas, etc. |
| `get_price_history` | Barras históricas OHLCV (abertura/máxima/mínima/fechamento/volume) por período (1 dia a 5 anos) e granularidade (30s a 1 mês). Pode incluir eventos corporativos e dados fora do horário regular (RTH). |
| `search_contracts` | Busca instrumentos por ticker, nome ou palavra-chave e devolve o `contract_id`, bolsa, símbolo e tipos de ativo disponíveis. É o ponto de partida — você precisa do `contract_id` para quase tudo. |

### 2.3 Inteligência de empresas e temas de investimento

| Ferramenta | O que retorna |
|---|---|
| `get_company_connections` | Perfil de negócio de uma empresa: concorrentes, produtos, exposição geográfica (países/regiões), setores/tendências — com evidências explicando cada conexão. |
| `get_company_themes` | Setores, tendências e indústrias a que a empresa pertence, e para cada um os principais peers ranqueados por relevância. |
| `search_investment_topics` | Busca temas/setores/tendências por palavra-chave (ex.: "battery", "solar") e devolve pares `{key, name}`. |
| `get_theme_details` | Perfil completo de um tema: descrição, empresas ranqueadas por relevância e, opcionalmente, ETFs/fundos com exposição. |

### 2.4 Instruções de ordem (o coração transacional)

| Ferramenta | O que faz |
|---|---|
| `create_order_instruction` | Cria uma **instrução** (não uma ordem viva). Devolve um URL que leva o usuário à plataforma IBKR para revisar e enviar. Só suporta ações (STK), tipos MARKET ou LIMIT, lado BUY/SELL, quantidade, preço limite e time-in-force (DAY, GTC, OVT, OND, OPG). |
| `get_order_instructions` | Lista todas as instruções salvas da conta (ID, descrição, contract_id, lado, quantidade, tipo, preço, TIF, data de criação). |
| `delete_order_instruction` | Exclui uma instrução pelo ID. |
| `provide_customer_feedback` | Envia feedback/solicitação de funcionalidade para a IBKR. |

> **Insight de arquitetura:** o fluxo de trading é deliberadamente "human-in-the-loop". A automação prepara a ordem; a pessoa confirma na IBKR. Isso reduz risco regulatório e de execução acidental. **Mantenha esse padrão** na sua solução, principalmente em estágio inicial.

---

## 3. O cenário de APIs da Interactive Brokers (2026)

A IBKR oferece quatro caminhos. Eles se diferenciam por protocolo, latência, cobertura de funcionalidades e esforço de operação.

### 3.1 IBKR Web API (Client Portal / "CP API") — REST  ✅ recomendada

- **Protocolo:** REST sobre HTTPS; WebSocket para streaming de cotações.
- **Autenticação:** OAuth 2.0 com `private_key_jwt` (RFC 7521/7523) para a Web API consolidada; OAuth 1.0a ainda é o caminho aprovado para *terceiros* (third-party vendors). Há também o modo CP Gateway (um pequeno gateway Java que mantém a sessão).
- **Vantagens:** sem instalar software pesado; integra em qualquer backend (Node, Python, Java, .NET...); a IBKR está **consolidando** Client Portal Web API + Digital Account Management + Flex Web Service numa única Web API com autenticação unificada.
- **Limitações:** limite global de **10 requisições/segundo** (HTTP 429 + "penalty box" de 10 min se exceder); a sessão de brokerage precisa ser mantida viva (re-autenticação/keep-alive).
- **Endpoints típicos:** `/iserver/secdef/search` (busca de contrato), `/iserver/marketdata/snapshot` (cotação, até 100 conids e 50 campos por chamada), `/iserver/marketdata/history` (histórico), `/portfolio/{accountId}/positions`, `/portfolio/{accountId}/summary`, `/iserver/account/{accountId}/orders` (ordens).

### 3.2 TWS API (Trader Workstation / IB Gateway) — socket

- **Protocolo:** socket com a aplicação TWS ou IB Gateway rodando localmente.
- **Linguagens:** C++, C#, Java, Python, ActiveX, RTD/DDE.
- **Vantagens:** a mais completa e madura — todos os tipos de ordem, instrumentos, dados; latência muito baixa; ótima para trading algorítmico.
- **Limitações:** exige um processo TWS/Gateway sempre de pé (com re-login periódico); mais difícil de operar como serviço em nuvem 24/7; o modelo é assíncrono (mensagens/callbacks), com curva de aprendizado maior.

### 3.3 FIX (Financial Information eXchange)

- Para fluxo institucional de alto volume. Exige acordo, infraestrutura dedicada e normalmente conta de maior porte. **Provavelmente excessivo** para o seu caso.

### 3.4 Excel/RTD

- Integração via planilha. Útil para análise manual, não para uma solução de produto.

### Tabela comparativa

| Critério | Web API (REST) | TWS API (socket) | FIX |
|---|---|---|---|
| Esforço de integração | Baixo | Médio/Alto | Alto |
| Precisa de software local rodando | Não (ou CP Gateway leve) | Sim (TWS/Gateway) | Infra dedicada |
| Latência | Boa | Muito baixa | Muito baixa |
| Cobertura de funcionalidades | Ampla e crescente | Máxima | Execução institucional |
| Bom para backend web/SaaS | ✅ Ótimo | ⚠️ Possível, mais trabalhoso | ❌ |
| Ideal para | Apps, dashboards, automação supervisionada | Trading algorítmico, baixa latência | Institucional/alto volume |

**Conclusão:** comece na **Web API REST**. Migre módulos específicos para a TWS API só se encontrar um limite real (latência, tipo de ordem, instrumento não suportado).

---

## 4. Mapa: ferramentas do conector → endpoints da API real

Isto mostra o que você precisaria implementar para replicar o conector na API oficial.

| Ferramenta do conector | Endpoint(s) da IBKR Web API (aprox.) |
|---|---|
| `search_contracts` | `GET /iserver/secdef/search` |
| `get_price_snapshot` | `GET /iserver/marketdata/snapshot` (conids + fields) |
| `get_price_history` | `GET /iserver/marketdata/history` |
| `get_account_balances` | `GET /portfolio/{accountId}/ledger` |
| `get_account_summary` | `GET /portfolio/{accountId}/summary` + `/iserver/account/pnl/partitioned` |
| `get_account_positions` | `GET /portfolio/{accountId}/positions/{page}` |
| `get_account_orders` | `GET /iserver/account/orders` |
| `get_account_trades` | `GET /iserver/account/trades` |
| `create_order_instruction` | `POST /iserver/account/{accountId}/orders` (com etapa de confirmação `/reply/{id}`) |
| `get_order_instructions` / `delete_order_instruction` | Camada própria (instruções são um conceito do conector, não da API); ordens vivas usam `/orders` e `DELETE /iserver/account/{accountId}/order/{orderId}` |
| `get_company_connections` / `get_company_themes` / `search_investment_topics` / `get_theme_details` | Dados de "fundamentals/company connections" da IBKR (produto de research; nem todo plano expõe via REST pública) |
| `provide_customer_feedback` | Camada própria (não é endpoint de trading) |

> Note que **"instrução de ordem"** é uma camada de segurança que o conector adicionou por cima da API. Na API crua, o equivalente é: você faz `POST .../orders`, a IBKR responde pedindo confirmação de mensagens de risco, e só então a ordem vai a mercado. O conector troca a confirmação automática por um **deep-link** que devolve a decisão final ao humano.

---

## 5. Blueprint de construção da sua solução

### 5.1 Arquitetura recomendada

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Front-end  │────▶│   Seu Backend (API)  │────▶│  IBKR Web API   │
│ (web/app)   │◀────│  - Auth/OAuth        │◀────│  (REST + WS)    │
└─────────────┘     │  - Cache             │     └─────────────────┘
                    │  - Rate limiter      │
                    │  - Camada "instrução"│
                    │  - Auditoria/logs    │
                    └──────────────────────┘
                              │
                        ┌─────────────┐
                        │  Banco de   │  (instruções, cache de
                        │  dados      │   contratos, auditoria)
                        └─────────────┘
```

Princípios:
- **Nunca** exponha as credenciais IBKR no front-end. Todo acesso passa pelo seu backend.
- O backend é o único que fala OAuth com a IBKR e mantém a sessão viva.
- Implemente um **rate limiter** próprio (token bucket) para respeitar os ~10 req/s e evitar a "penalty box".
- Faça **cache** do que muda pouco (resolução de `contract_id`, dados de empresa/temas) para economizar chamadas.

### 5.2 Passo a passo

**Passo 0 — Conta e onboarding.** Tenha uma conta IBKR (comece em conta paper/demo). Para a Web API consolidada, configure OAuth 2.0 `private_key_jwt`. Se for atuar como **terceiro** integrando contas de outros usuários, inicie o processo de aprovação enviando o formulário de onboarding para `webapionboarding@interactivebrokers.com` (terceiros hoje usam OAuth 1.0a).

**Passo 1 — Autenticação e sessão.** Implemente o fluxo OAuth, obtenha o token, e a abertura da *brokerage session*. Crie um keep-alive (ex.: `tickle`/`reauthenticate`) para não cair.

**Passo 2 — Resolução de contratos.** Implemente a busca (`/iserver/secdef/search`) e **persista** o `contract_id` por símbolo/bolsa. Quase todo endpoint depende disso.

**Passo 3 — Leitura de dados (baixo risco, comece por aqui).** Posições, saldos, resumo, ordens, trades, cotações e histórico. São somente-leitura — ideais para validar a integração sem risco de mover dinheiro.

**Passo 4 — Camada de "instrução de ordem".** Replique o padrão seguro do conector: seu backend monta a ordem, grava como *instrução* no banco com status `pendente`, e gera um link/etapa de confirmação. A ordem só vai a mercado após aprovação humana explícita. Trate a etapa de *reply/confirmação* de mensagens de risco da IBKR.

**Passo 5 — Streaming (opcional).** Para cotações ao vivo no dashboard, use o WebSocket da Web API em vez de fazer polling no snapshot (poupa o orçamento de 10 req/s).

**Passo 6 — Observabilidade e auditoria.** Logue toda chamada, toda instrução criada/confirmada/excluída e todo erro 429. Em trading, trilha de auditoria não é opcional.

### 5.3 Stack sugerida

- **Backend:** Node.js/TypeScript ou Python (FastAPI). Ambos têm libs comunitárias para a IBKR.
- **Banco:** PostgreSQL (instruções, auditoria, cache de contratos).
- **Fila/agendador:** para keep-alive da sessão e tarefas periódicas.
- **Libs de referência (comunidade):** clientes IBKR Web API com suporte a OAuth (há projetos open-source maduros); para TWS API, `ib_insync`/`ib_async` (Python) é o padrão de fato.

---

## 6. Riscos e cuidados

- **Rate limiting (10 req/s global):** projete cache + WebSocket + backoff desde o início. Exceder coloca seu IP em penalty box por 10 minutos.
- **Gestão de sessão:** sessões de brokerage expiram. Sem keep-alive, sua solução "cai" silenciosamente.
- **Risco financeiro:** mantenha o humano no loop para envio de ordens, especialmente no MVP. Comece em conta **paper**.
- **Aprovação de terceiros:** se você integra contas de clientes (não só a sua), há processo formal de onboarding e revisão da IBKR.
- **Cobertura de instrumentos:** o conector atual só cria instruções para **ações (STK)**. Opções, futuros, FX etc. exigem trabalho adicional e cuidados de margem.
- **Consolidação da API:** a IBKR está unificando seus produtos web. Acompanhe o changelog para não usar endpoints que serão depreciados.
- **Conformidade/jurídico:** trading automatizado tem implicações regulatórias que variam por jurisdição. Isto é informação técnica, não aconselhamento jurídico ou financeiro — vale revisar com um especialista antes de ir a produção.

---

## 7. Próximos passos sugeridos

1. Criar conta **paper** na IBKR e configurar OAuth na Web API.
2. Implementar Passos 1–3 (auth + leitura de dados) como prova de conceito.
3. Validar o orçamento de requisições com cache + WebSocket.
4. Construir a camada de instrução de ordem (Passo 4) replicando o padrão seguro do conector.
5. Só então avaliar TWS API para necessidades específicas.

---

## Fontes

- [Trading Web API | IBKR Campus](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/)
- [Web API Documentation | IBKR Campus](https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/)
- [Web API v1.0 Documentation | IBKR Campus](https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/)
- [Introduction / Getting Started | IBKR Campus](https://www.interactivebrokers.com/campus/ibkr-api-page/getting-started/)
- [Client Portal API Documentation (GitHub Pages)](https://interactivebrokers.github.io/cpwebapi/)
- [IBKR Trading API Solutions | Interactive Brokers LLC](https://www.interactivebrokers.com/en/trading/ib-api.php)
- [What is IBKR's Client Portal API? | Trading Lesson](https://www.interactivebrokers.com/campus/trading-lessons/what-is-ibkrs-client-portal-api/)
- [Placing Orders | IBKR Campus](https://www.interactivebrokers.com/campus/trading-lessons/placing-orders/)
- [Requesting Market Data | Traders' Academy](https://www.interactivebrokers.com/campus/trading-lessons/requesting-market-data/)
- [TWS API — Historical Market Data](https://interactivebrokers.github.io/tws-api/historical_data.html)