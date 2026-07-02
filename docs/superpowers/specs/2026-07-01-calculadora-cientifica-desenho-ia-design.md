# Calculadora científica + reconhecimento de desenho por IA + painel de modelos

**Data:** 2026-07-01
**Escopo:** caderno de questões (`/q/caderno/[id]`), painel admin `/jobs`, backend FastAPI.

## Objetivo

Evoluir a calculadora do caderno de questões em três frentes:

1. **Calculadora completa** com modos Normal e Científica (toggle) e teclado expandido.
2. **Arrastável**: o usuário pega pelo cabeçalho e move o painel para qualquer canto da tela.
3. **Gaveta de desenho**: uma alça saliente na lateral abre um painel deslizante onde o
   usuário desenha a conta à mão; uma IA multimodal transcreve o desenho para a expressão
   da calculadora, que calcula na hora.

Junto, a tela `/jobs` ganha uma seção **"Modelos de IA"**: painel de controle admin onde se
escolhe qual modelo atende cada recurso de IA. A lista de modelos vem da **autoridade de
modelos** (`platform-api /api/v1/llm/models`) — nunca hardcoded (contrato canônico em
`witdev-platform-core/docs/agent-memory/llm-model-catalog-contract.md`).

## Decisões de produto (fechadas com o usuário)

| Decisão | Escolha |
|---|---|
| Reconhecimento do desenho | IA multimodal via LLM proxy; **modelo escolhido pelo admin** no painel |
| Painel /jobs | Seção "Modelos de IA" **no topo**, lista de jobs continua abaixo |
| Recursos controlados no painel | Calculadora (reconhecimento), Processamento de PDF, Chat de aula |
| UX da área de desenho | **Gaveta pull-out** com alça saliente na lateral (não é aba); switch **Auto** |
| Gatilho do reconhecimento | Auto ligado: delay (~1,5s) após parar de desenhar → envia sozinho. Auto desligado: botão "Reconhecer" |
| Modos da calculadora | Toggle **Normal \| Científica** |
| Acesso ao reconhecimento | **Só assinantes PRO** (e admin). Desenhar é livre; reconhecer tem cadeado no free |

## Arquitetura (Abordagem 1 — aprovada)

```text
Frontend (gaveta de desenho)
  └─ PNG base64 → POST /api/q/calculadora/reconhecer (backend studIA)
       └─ lê alias em app_settings["llm.calculadora_reconhecimento"]
       └─ POST {LITELLM_BASE_URL}/v1/chat/completions  (visão, alias canônico)
            └─ LiteLLM resolve o provider (Gemini/Claude/GPT/…)

Painel /jobs (admin)
  └─ GET /api/admin/llm/models (backend studIA)
       └─ proxy server-to-server → platform-api /api/v1/llm/models  (autoridade)
  └─ GET/PUT /api/admin/llm/settings → app_settings
```

- O browser **nunca** fala com o LiteLLM nem recebe key — invariante do contrato.
- A calculadora segue o contrato à risca: persiste e envia **apenas o alias canônico**;
  o LiteLLM resolve provider/upstream.
- **Exceção deliberada**: Processamento de PDF e Chat de aula continuam na genai SDK via
  passthrough `/gemini` do LiteLLM (para manter o **Batch API 50% off**). Seus dropdowns
  filtram o catálogo central para modelos Gemini e persistem o id Gemini derivado do alias
  (sufixo após o prefixo WitDev). Se um dia o Batch deixar de ser requisito, migram para
  `/v1` por alias como a calculadora.

## Componentes

### 1. Frontend — `ScientificCalculator.tsx` (refactor)

Arquivos em `fontend/app/q/caderno/[id]/components/`:

- **`ScientificCalculator.tsx`** — painel principal; ganha drag, toggle de modos e a gaveta.
- **`useDraggablePanel.ts`** (novo hook) — pointer events + `setPointerCapture` no
  cabeçalho; posição em `state` aplicada via `transform`; clamp ao viewport (inclusive em
  `resize`); persiste em `localStorage` (`studia:calc:pos`). Sem dependência nova.
- **`CalculatorDrawArea.tsx`** (novo) — a gaveta de desenho (detalhes na seção 2).
- **`math.ts`** (estender) — ver seção 3.

Modos:

- **Normal**: grid 4 colunas — `C ⌫ ( )`, `7 8 9 ÷`, `4 5 6 ×`, `1 2 3 −`, `0 . = +`,
  linha extra `% √`.
- **Científica**: mesmas teclas + linhas de função — `sin cos tan √`, `asin acos atan x!`,
  `log ln exp ^`, `π e x² 1/x` — e toggle **DEG/RAD** ao lado do seletor de modos.
- Teclas científicas inserem texto na expressão (`x²` → `^2`, `1/x` → `1/(`, `π` → `pi`).
- Modo e DEG/RAD persistem em `localStorage` (`studia:calc:mode`, `studia:calc:angle`).
- **Encadeamento a partir do resultado (ANS)**: após `=` (ou restaurar item do
  histórico), apertar uma tecla de **operador** (`+ − × ÷ ^ % ! x²`) continua a conta a
  partir do resultado (ex.: resultado `-70`, tecla `÷`, `5`, `=` → expressão `-70/5` →
  `-14`). Tecla de **dígito/função/parêntese** começa conta nova. Editar o campo
  manualmente desliga o encadeamento pendente. Motivação: usuário calculou
  `20*2.5-(40*3)` = -70 e digitou `/5` esperando -14, mas a precedência aplicou o `/5`
  só ao `(40*3)` (resultado 26, correto porém surpreendente).
- Histórico, salvamento por questão e input editável: **inalterados**.

### 2. Frontend — gaveta de desenho (`CalculatorDrawArea.tsx`)

- **Alça saliente** vertical centrada na borda lateral do painel (ícone `stylus`/lápis +
  ranhuras de pegador), sugerindo "segure e puxe". Clique (ou arrasto curto) alterna
  aberto/fechado; a gaveta desliza colada à lateral com `transition-transform`.
- **Lado de abertura**: o de maior espaço livre no viewport em relação à posição atual do
  painel (calc encostada à direita → abre à esquerda). Recalcula ao terminar um drag.
- **Canvas de desenho**: strokes capturados com pointer events (mesmo padrão de
  `QuestionCanvasOverlay`: array de pontos normalizados, `lineCap/lineJoin: round`).
  Traço claro na UI (tema dark); na exportação, redesenha **traço escuro sobre fundo
  branco** para a visão do modelo. Botões: desfazer traço, limpar tudo.
- **Switch "Auto"** (default ligado, persiste em `localStorage`):
  - Ligado: debounce de ~1,5s após o último `pointerup` → envia. Novo traço cancela o
    envio pendente. Não reenvia se nada mudou desde o último reconhecimento.
  - Desligado: só envia no clique de **"Reconhecer"** (botão sempre visível; serve também
    para re-tentar com Auto ligado).
- **Fluxo de reconhecimento**: canvas → PNG base64 → `POST /api/q/calculadora/reconhecer`
  → `{ expression }` → preenche o campo **Expressão** da calculadora → dispara o
  `calculate()` existente (resultado + histórico). Expressão fica editável como sempre.
- **Estados** (regra "dados não pulam na tela"):
  - Reconhecendo: `BrandLoader` compacto + "Reconhecendo…" em área reservada no rodapé da
    gaveta; traços permanecem visíveis; novo envio bloqueado enquanto pende.
  - Erro de leitura (`ERRO` do modelo): "Não entendi o desenho — ajuste e tente de novo",
    traços preservados.
  - IA indisponível (proxy fora / timeout): "IA indisponível no momento."
- **Gate PRO**: para free, o rodapé da gaveta troca switch+botão por cadeado + CTA
  "Recurso PRO — assine para reconhecer seu desenho" (link ao checkout). Desenhar continua
  liberado. O status PRO vem da sessão/endpoint de billing existente.

### 3. Frontend — `math.ts` (extensão do parser)

Mantém tokenizer + recursive descent e erros em português. Adições:

- **Funções**: `asin`, `acos`, `atan` (entrada [-1,1] onde aplicável; saída em DEG ou RAD
  conforme modo), `exp`.
- **Fatorial pós-fixo `!`**: inteiro não-negativo ≤ 170 (limite de `Number`); erro
  amigável fora disso.
- **Constantes**: `pi` e `e` como identificadores (mesma tokenização de letras já
  existente).
- **Assinatura**: `evaluateExpression(expr, { angleMode: "deg" | "rad" })` — default
  `"deg"` (compatível com o comportamento atual). Trig direta converte entrada; trig
  inversa converte saída.
- `%` , `^`, precedências e mensagens existentes: inalterados.

### 4. Backend — reconhecimento

`POST /api/q/calculadora/reconhecer` (novo, em `main.py` junto às rotas `/api/q/*`):

- **Auth**: sessão obrigatória (JWT cookie, fluxo existente) + gate **PRO ou admin** →
  403 `{ "detail": "pro_required" }` caso contrário.
- **Request**: `{ "image_base64": "<png b64, sem data-url>" }`. Limite ~2 MB decodificado
  → 413 acima disso.
- **Config**: lê `app_settings["llm.calculadora_reconhecimento"]` (alias canônico).
  Sem valor configurado → default seed `witdev_copilot/gemini-3-flash-preview` (ajustável
  no painel).
- **Chamada**: `httpx.AsyncClient` → `POST {LITELLM_BASE_URL}/v1/chat/completions`,
  `Authorization: Bearer {LITELLM_API_KEY}`, timeout 20s. Mensagens:
  - system: transcritor estrito — "devolva SOMENTE a expressão matemática na sintaxe da
    calculadora (dígitos, `+ - * / ^ % ! ( ) .`, funções `sin cos tan asin acos atan log
    ln exp sqrt`, constantes `pi` e `e`); converta `÷→/`, `×→*`, `√x→sqrt(x)`, frações
    verticais→`(a)/(b)`, potências→`^`; se ilegível ou não-matemático, devolva exatamente
    `ERRO`".
  - user: imagem (`image_url` com data-URL PNG).
- **Resposta**: `{ "expression": "..." }`. `ERRO`/vazio → 422 `{ "detail": "ilegivel" }`.
  A validação sintática final é do parser no frontend.
- **Fallback de degradação**: proxy indisponível (conexão/5xx) **e** alias configurado é
  Gemini → tenta Gemini direto via `GEMINI_API_KEY` (genai SDK, id upstream derivado do
  alias). Senão → 503 `{ "detail": "ia_indisponivel" }`.

### 5. Backend — `app_settings` + catálogo + endpoints admin

- **Tabela `app_settings`** (migração Alembic): `key TEXT PK`, `value TEXT NOT NULL`,
  `updated_at timestamptz`. Helper `get_setting(key, default)` / `set_setting(key, value)`.
- **Chaves**: `llm.calculadora_reconhecimento` (alias canônico completo),
  `llm.processamento_pdf` e `llm.chat_aula` (id Gemini upstream — ver exceção do Batch).
- **`GET /api/admin/llm/models`** (admin): proxy para `PLATFORM_LLM_CATALOG_URL`
  (env; default `http://platform-api:8000/api/v1/llm/models`), timeout 10s, cache
  in-memory 60s. Resposta normalizada:
  `{ "source": "central" | "local_fallback", "models": [{ value, label, provider, pricing?, capabilities? }] }`.
  - Central respondeu com ≥1 modelo → usa **só** a lista central (sem mesclar).
  - Central fora/vazio/inválido → fallback local (a lista `GEMINI_MODELS` atual
    reformatada), `source: "local_fallback"`.
- **`GET/PUT /api/admin/llm/settings`** (admin): lê/grava o mapa recurso→modelo.
  PUT valida que o valor veio da lista atualmente servida (central ou fallback).
- **`GET /api/modelos` (existente)**: deixa de ser hardcoded — passa a servir o catálogo
  central **filtrado a modelos Gemini** (mapeado ao shape atual `value/label/description/
  pricing/recommended`, `recommended` = setting `llm.processamento_pdf`), com o mesmo
  fallback local marcado. Consumidores (`ModelSelector`, upload, chat) não mudam de shape.
- **Env**: `PLATFORM_LLM_CATALOG_URL` adicionada a `docker-compose.dev.yml` e ao deploy
  (`build.sh` / stack), na rede interna compartilhada.

### 6. Frontend — painel `/jobs` (seção "Modelos de IA")

- Nova seção no **topo** da página (jobs continuam abaixo), admin-only como a rota já é.
- Três linhas — **Calculadora · reconhecimento de desenho** (catálogo completo, só
  modelos com visão quando `capabilities` disponível), **Processamento de PDF · Batch**
  e **Chat de aula** (ambos filtrados a Gemini) — cada uma com dropdown (label, provider,
  pricing quando houver), estado atual pré-selecionado e botão **Salvar** por linha com
  toast de confirmação.
- Badge de alerta quando `source: "local_fallback"`: "Catálogo central indisponível —
  usando lista local".
- Data fetching via React Query (`useQuery` catálogo + settings, `useMutation` no PUT),
  skeleton com a altura final reservada (regra de UI).

## Tratamento de erros (resumo)

| Cenário | Comportamento |
|---|---|
| Free tenta reconhecer | 403 `pro_required` → cadeado + CTA na gaveta |
| Modelo devolve `ERRO`/vazio | 422 `ilegivel` → "Não entendi o desenho…", traços preservados |
| Proxy fora, alias não-Gemini | 503 `ia_indisponivel` → "IA indisponível no momento." |
| Proxy fora, alias Gemini | fallback Gemini direto; se falhar, 503 |
| Catálogo central fora/vazio | fallback local marcado, badge no painel |
| Expressão reconhecida inválida | erro normal do parser, campo editável |
| Imagem > 2 MB | 413 → "Desenho grande demais — limpe e tente de novo." |

## Testes

- **Backend (pytest, `backend/tests/`)**: gate admin de `/api/admin/llm/*`; gate PRO de
  `/reconhecer`; proxy do catálogo com `httpx` mockado (central ok / fora / vazio →
  fallback marcado, sem mescla); PUT settings valida valor contra a lista; `/api/modelos`
  filtrado a Gemini; parsing da resposta do `/v1/chat/completions` (ok / `ERRO` / vazio);
  teste de drift de migrations continua verde com a migração nova.
- **Frontend**: `pnpm lint`; smoke manual — drag (limites do viewport, persistência),
  gaveta (lado de abertura, auto/manual, cancelamento do debounce), modos Normal/
  Científica, DEG/RAD, fatorial/constantes no parser, gate PRO visual.

## Entrega

Fluxo obrigatório do projeto: worktree `calc-cientifica-desenho-ia` → commits por
intenção → merge na `main` (checkout principal permanece na `main`) → `git push` →
`./build.sh` → `git worktree remove`.

## Fora de escopo

- Migrar PDF/chat para `/v1` por alias (fica para quando o Batch 50% off não for mais
  requisito).
- Limite diário de reconhecimentos para PRO (adicionar depois se houver abuso).
- Reconhecimento offline/client-side.
