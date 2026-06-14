# Plano 04 — IA via LLM proxy (LiteLLM passthrough Gemini) (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidar toda a IA do studIA no **LLM proxy compartilhado** (`platform-litellm`) sem perder o **Gemini Batch (50% off)**, roteando a SDK `google-genai` pelo **passthrough `/gemini` do LiteLLM** com uma **virtual key** própria do studIA — em vez de falar direto com a API do Gemini usando `GEMINI_API_KEY`.

**Architecture:** A descoberta (jun/2026) provou que a `google-genai` SDK funciona apontada para `http://platform-litellm:4000/gemini` com uma virtual key `sk-...`: `generate_content` retornou OK **e um Batch inline foi PENDING→RUNNING→SUCCEEDED** pelo proxy. Portanto a migração é cirúrgica: trocar **apenas o `_get_client()`** do `gemini_service.py` para construir o `genai.Client` apontando no passthrough quando `LITELLM_API_KEY` estiver setado; caso contrário, cair no Gemini direto com `GEMINI_API_KEY` (fallback — dev sem proxy, ou contingência). Todo o resto (chat streaming, Batch inline/JSONL, polling, extração) permanece idêntico e passa a fluir pelo proxy. Comunicação 100% por **rede interna docker** (`minha_rede`); só o LiteLLM faz egress externo. A virtual key é provisionada uma vez via API admin do LiteLLM e guardada no `.env` (local → `/opt/studia/.env` via `build.sh`, igual ao `GEMINI_API_KEY`).

**Tech Stack:** Python 3.12, `google-genai` (mantida), LiteLLM proxy (OpenAI-compat + passthrough Google AI Studio), FastAPI, Docker Swarm/Compose, `build.sh`.

---

## Contexto descoberto (não repetir descoberta)

- **Proxy:** `http://platform-litellm:4000` (rede `minha_rede`). Passthrough Gemini: `http://platform-litellm:4000/gemini` → encaminha para `generativelanguage.googleapis.com` usando a `GEMINI_API_KEY` da plataforma. Exige **virtual key** `sk-...` (não o master).
- **Validado** (com virtual key temporária, do container `studia_backend`):
  - `genai.Client(api_key=sk-..., http_options=HttpOptions(base_url="http://platform-litellm:4000/gemini"))` → `models.generate_content("...")` → **OK** ("PONG").
  - **Batch inline** via essa client → `batches.create(model="gemini-3-flash-preview", src=[...inline...])` → poll → **JOB_STATE_SUCCEEDED**, `inlined_responses` retornou o texto. ✅
- **Embeddings:** o LiteLLM **não** expõe modelos de embedding em `/v1/embeddings` (`text-embedding-004`/`gemini-embedding-001` → 400). MAS `generate_embeddings.py` usa a `genai` SDK (`embed_content`), que pelo passthrough `/gemini` deve encaminhar igual ao `generate_content` — **validar na execução**; é script CLI manual, baixo risco.
- **Key admin:** `LITELLM_MASTER_KEY` (no env do container `platform-litellm`) é admin; `/key/generate` e `/key/delete` funcionam.
- **build.sh:** monta `/opt/studia/.env` no servidor lendo segredos do `.env` **local** (ex.: `GEMINI_API_KEY` em build.sh:109 e emitido em build.sh:191). Vamos espelhar para `LITELLM_API_KEY` e adicionar `LITELLM_BASE_URL`.
- **Surface de IA:** `backend/gemini_service.py` (`_get_client()` em :74-75; chat `chat_stream` :375; Batch `process_pdf_chunks` :201; sync :353) e `backend/generate_embeddings.py` (CLI). Único ponto a mudar p/ chat+batch: `_get_client()`.

### Risco residual conhecido
O caminho **JSONL/Files API** (`_process_jsonl_file`, usado só quando o lote estimado ≥ 20MB) faz `client.files.upload(...)` num endpoint de upload distinto. O passthrough foi validado p/ `generate_content` e Batch **inline**; o upload de arquivo pelo passthrough **não** foi validado. PDFs típicos de aula (chunks de 10 págs) caem no caminho **inline** (<20MB). Mitigação: validar o JSONL na execução; se o upload pelo passthrough falhar, manter esse ramo raro no Gemini direto (a função pode usar `GEMINI_API_KEY` quando presente) e registrar. Não bloqueia o plano.

---

## File Structure

- **Modify** `backend/gemini_service.py` — `_client_config()` (novo, puro, lê env) + `_get_client()` (passa a usar o passthrough quando `LITELLM_API_KEY` setado; fallback Gemini direto). Adicionar `from dataclasses import dataclass`.
- **Create** `backend/tests/test_gemini_proxy.py` — testes da escolha proxy vs direto (puro, env-driven; sem rede).
- **Modify** `backend/generate_embeddings.py` — usar o mesmo `_get_client()` do `gemini_service` (consolida embeddings no proxy quando disponível; fallback direto).
- **Modify** `build.sh` — ler `LITELLM_API_KEY` do `.env` local, propagar via ssh, emitir `LITELLM_API_KEY` + `LITELLM_BASE_URL` no `/opt/studia/.env` remoto (espelho do `GEMINI_API_KEY`).
- **Provisionamento (execução, via SSH):** mintar a virtual key `studia` no LiteLLM e gravar `LITELLM_API_KEY=sk-...` no `.env` local.
- **No-op proposital:** `docker/stack.yml` e `docker-compose.dev.yml` não precisam mudar — backend/worker já carregam `env_file: /opt/studia/.env` (prod) e em dev `LITELLM_API_KEY` fica ausente → fallback Gemini direto.

Contrato de env (lido em `gemini_service._client_config()`):

| Env | Default | Efeito |
|---|---|---|
| `LITELLM_API_KEY` | `""` | se setado → roteia pelo proxy (passthrough). Vazio → Gemini direto |
| `LITELLM_BASE_URL` | `http://platform-litellm:4000` | base do proxy; o código anexa `/gemini` |
| `GEMINI_API_KEY` | `""` | usado no fallback direto (e na contingência do ramo JSONL) |

---

### Task 1: `_get_client()` roteando pelo passthrough do LiteLLM — TDD

**Files:**
- Test: `backend/tests/test_gemini_proxy.py`
- Modify: `backend/gemini_service.py` (topo: imports + constantes :9-13; `_get_client` :74-75)

- [ ] **Step 1: Escrever o teste falho**

Criar `backend/tests/test_gemini_proxy.py`:

```python
"""Escolha de transporte da IA: LiteLLM passthrough vs Gemini direto.

_client_config() é puro (lê env), então testa sem rede.
"""
import pytest

from gemini_service import _client_config, _get_client


def test_config_proxy_quando_litellm_key_setada(monkeypatch):
    monkeypatch.setenv("LITELLM_API_KEY", "sk-abc123")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://platform-litellm:4000")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-direct")
    cfg = _client_config()
    assert cfg.via_proxy is True
    assert cfg.api_key == "sk-abc123"
    assert cfg.base_url == "http://platform-litellm:4000/gemini"


def test_config_proxy_normaliza_barra_final(monkeypatch):
    monkeypatch.setenv("LITELLM_API_KEY", "sk-abc123")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://platform-litellm:4000/")
    cfg = _client_config()
    assert cfg.base_url == "http://platform-litellm:4000/gemini"


def test_config_direto_sem_litellm_key(monkeypatch):
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-direct")
    cfg = _client_config()
    assert cfg.via_proxy is False
    assert cfg.api_key == "AIza-direct"
    assert cfg.base_url is None


def test_get_client_constroi_nos_dois_modos(monkeypatch):
    from google import genai
    monkeypatch.setenv("LITELLM_API_KEY", "sk-abc123")
    assert isinstance(_get_client(), genai.Client)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-direct")
    assert isinstance(_get_client(), genai.Client)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/wital/studia && ./dev.sh test backend/tests/test_gemini_proxy.py`
Expected: FAIL no import (`cannot import name '_client_config'`).

- [ ] **Step 3: Implementar em `gemini_service.py`**

No topo de `backend/gemini_service.py`, ajustar imports e constantes. Trocar o bloco atual:
```python
import os
import json
import tempfile
import time
import base64
import pathlib
from typing import AsyncIterator

from google import genai
from google.genai import types


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
```
por:
```python
import os
import json
import tempfile
import time
import base64
import pathlib
from dataclasses import dataclass
from typing import AsyncIterator

from google import genai
from google.genai import types


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LITELLM_BASE_URL_DEFAULT = "http://platform-litellm:4000"


@dataclass(frozen=True)
class ClientConfig:
    api_key: str
    base_url: str | None  # None = Gemini direto; senão = passthrough /gemini do proxy
    via_proxy: bool


def _client_config() -> ClientConfig:
    """Decide o transporte da IA: LiteLLM passthrough (consolidado) vs Gemini direto.

    Em prod `LITELLM_API_KEY` está setado → roteia TUDO (chat + Batch) pelo proxy
    interno (`<base>/gemini`), por rede docker. Sem ela (dev sem proxy / contingência)
    cai no Gemini direto com `GEMINI_API_KEY` — comportamento original preservado.
    """
    litellm_key = os.getenv("LITELLM_API_KEY", "")
    if litellm_key:
        base = os.getenv("LITELLM_BASE_URL", LITELLM_BASE_URL_DEFAULT).rstrip("/")
        return ClientConfig(api_key=litellm_key, base_url=f"{base}/gemini", via_proxy=True)
    return ClientConfig(api_key=os.getenv("GEMINI_API_KEY", ""), base_url=None, via_proxy=False)
```

Depois, trocar `_get_client()` (atual :74-75):
```python
def _get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)
```
por:
```python
def _get_client() -> genai.Client:
    cfg = _client_config()
    if cfg.base_url:
        return genai.Client(
            api_key=cfg.api_key,
            http_options=types.HttpOptions(base_url=cfg.base_url),
        )
    return genai.Client(api_key=cfg.api_key)
```

Não mudar mais nada no arquivo — `chat_stream`, `process_pdf_chunks`, `_process_inline`, `_process_jsonl_file`, `process_pdf_chunk_sync` e o polling usam `_get_client()` e passam a fluir pelo proxy automaticamente.

- [ ] **Step 4: Rodar os testes do proxy e ver passar**

Run: `cd /home/wital/studia && ./dev.sh test backend/tests/test_gemini_proxy.py`
Expected: PASS (4 testes).

- [ ] **Step 5: Suíte inteira**

Run: `cd /home/wital/studia && ./dev.sh test`
Expected: tudo verde.

- [ ] **Step 6: Commit**

```bash
git add backend/gemini_service.py backend/tests/test_gemini_proxy.py
git commit -m "feat(ia): roteia google-genai pelo passthrough do LiteLLM (chat + Batch) com fallback Gemini direto"
```

---

### Task 2: Embeddings (CLI) pelo mesmo client

**Files:** Modify `backend/generate_embeddings.py` (imports + construção do client)

- [ ] **Step 1: Usar o `_get_client()` consolidado**

Em `backend/generate_embeddings.py`, trocar a construção direta do client. Onde hoje há (em `gerar()`):
```python
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não definido")
    client = genai.Client(api_key=GEMINI_API_KEY)
```
por:
```python
    from gemini_service import _get_client, _client_config
    if not _client_config().api_key:
        raise RuntimeError("Nem LITELLM_API_KEY nem GEMINI_API_KEY definidos")
    client = _get_client()
```
Manter o resto do arquivo igual (o `import` de `genai` pode permanecer; se ficar sem uso, removê-lo). Não remover `GEMINI_API_KEY` do módulo se ainda referenciado em outro ponto do arquivo.

- [ ] **Step 2: Sanidade de import (sem rodar embeddings reais)**

Run:
```bash
cd /home/wital/studia && docker compose -f docker-compose.dev.yml run --rm backend python -c "import generate_embeddings; print('import ok')"
```
Expected: `import ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/generate_embeddings.py
git commit -m "chore(ia): generate_embeddings usa o client consolidado (proxy quando disponível)"
```

---

### Task 3: `build.sh` propaga `LITELLM_API_KEY` + `LITELLM_BASE_URL`

**Files:** Modify `build.sh` (leitura ~:109, env do ssh ~:140, heredoc remoto ~:191)

- [ ] **Step 1: Ler a chave do `.env` local (espelho do GEMINI)**

Em `build.sh`, junto das outras leituras (após a linha que define `gemini="$(grep -E '^GEMINI_API_KEY=' ...)"`, ~:109), adicionar:
```bash
  litellm_key="$(grep -E '^LITELLM_API_KEY=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
```
E junto dos avisos (perto de build.sh:121), adicionar:
```bash
  [[ -n "$litellm_key" ]] || log_warn "LITELLM_API_KEY ausente no .env local (IA cairá no Gemini direto via GEMINI_API_KEY)"
```

- [ ] **Step 2: Propagar via ssh**

Na linha que monta o ambiente do `ssh ... bash -s` (a longa, build.sh:140 — começa com `"$PROD_SSH_HOST" "GEMINI_API_KEY='$gemini' ...`), inserir, logo após `GEMINI_API_KEY='$gemini'`:
```
LITELLM_API_KEY='$litellm_key'
```
(É uma string única separada por espaços; manter as aspas no mesmo padrão dos demais.)

- [ ] **Step 3: Emitir no `/opt/studia/.env` remoto**

No heredoc remoto, no bloco de saída (perto de build.sh:191 onde está `printf 'GEMINI_API_KEY=%s\n' "$GEMINI_API_KEY"`), adicionar logo após a linha do GEMINI:
```bash
  printf 'LITELLM_API_KEY=%s\n' "$LITELLM_API_KEY"
  echo "LITELLM_BASE_URL=http://platform-litellm:4000"
```

- [ ] **Step 4: Validar sintaxe do script**

Run: `cd /home/wital/studia && bash -n build.sh && echo "build.sh OK"`
Expected: `build.sh OK`.

- [ ] **Step 5: Commit**

```bash
git add build.sh
git commit -m "build(ia): propaga LITELLM_API_KEY + LITELLM_BASE_URL p/ /opt/studia/.env"
```

---

### Task 4: Provisionar a virtual key + deploy + smoke (controlador, via SSH)

**Files:** nenhum no repo. Requer SSH de prod (autorizado p/ leitura/diagnóstico e fluxo `build.sh`; mintar key é **aditivo/não-destrutivo**).

- [ ] **Step 1: Mintar a virtual key `studia` no LiteLLM (persistente)**

```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 '
LLM=$(docker ps --format "{{.Names}}" | grep platform-litellm | head -1)
docker exec "$LLM" sh -lc "python3 - <<PY
import os,json,urllib.request
KEY=os.environ[\"LITELLM_MASTER_KEY\"]
body={\"key_alias\":\"studia\",\"models\":[],\"metadata\":{\"app\":\"studia\"}}
req=urllib.request.Request(\"http://localhost:4000/key/generate\",data=json.dumps(body).encode(),method=\"POST\",headers={\"Authorization\":\"Bearer \"+KEY,\"Content-Type\":\"application/json\"})
print(json.load(urllib.request.urlopen(req,timeout=30))[\"key\"])
PY"
'
```
Guardar o `sk-...` retornado (é segredo). Se já existir uma key `studia` (alias duplicado é permitido pelo LiteLLM, mas evitar recriar), reusar a existente: `GET /key/list` e checar alias.

- [ ] **Step 2: Gravar no `.env` LOCAL (fonte do build.sh)**

Adicionar ao `/home/wital/studia/.env` local a linha `LITELLM_API_KEY=sk-...` (com o valor do Step 1). Conferir que não há duplicata:
```bash
grep -c '^LITELLM_API_KEY=' /home/wital/studia/.env
```
Expected: `1`.

- [ ] **Step 2.5: Confirmar com o usuário antes do deploy**

O deploy é via `./build.sh` (autorizado em automode). Como é prod e mexe no caminho de IA, dar um aviso e seguir (rollback Swarm pronto).

- [ ] **Step 3: Push + deploy**

```bash
cd /home/wital/studia && git push && ./build.sh
```
Expected: `/opt/studia/.env` recebe `LITELLM_API_KEY` + `LITELLM_BASE_URL`; stack deployada; backend/worker 1/1.

- [ ] **Step 4: Smoke — env aplicado**

```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 '
grep -E "^LITELLM_(API_KEY|BASE_URL)=" /opt/studia/.env | sed -E "s/(API_KEY=sk-).{6}.*/\1<redacted>/"
BK=$(docker ps -qf name=studia_backend | head -1)
docker exec "$BK" sh -lc "echo via_proxy:; python -c \"from gemini_service import _client_config as c; x=c(); print(x.via_proxy, x.base_url)\""
'
```
Expected: `LITELLM_BASE_URL=http://platform-litellm:4000`, `LITELLM_API_KEY=sk-<redacted>`; `via_proxy: True http://platform-litellm:4000/gemini`.

- [ ] **Step 5: Smoke — chat + Batch reais pelo proxy (prod)**

```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 '
BK=$(docker ps -qf name=studia_backend | head -1)
docker exec "$BK" python -c "
import asyncio
from gemini_service import chat_stream, process_pdf_chunks  # noqa
async def go():
    out=[]
    async for t in chat_stream(\"contexto de teste\", \"responda apenas: OK\", [], modelo=\"gemini-3-flash-preview\"):
        out.append(t)
    print(\"chat:\", (\"\".join(out)).strip()[:40])
asyncio.run(go())
"
'
```
Expected: `chat: OK` (ou similar) — prova o chat streaming pelo passthrough. (O Batch já foi validado na descoberta; um teste de Batch real exige PDF — fazer pela UI no Step 6 se desejado.)

- [ ] **Step 6: Smoke ponta-a-ponta opcional (UI)**

Pela UI de prod, subir um PDF de aula pequeno e confirmar `status='concluido'` (blocos/fórmulas/flashcards criados) — exercita o Batch pelo proxy no worker. Conferir atribuição de uso no LiteLLM:
```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 'docker service logs witdev-platform-core_platform-litellm --tail 30 2>&1 | grep -iE "studia|gemini" | tail -10'
```
Rollback de emergência: `docker service rollback studia_backend studia_worker`.

- [ ] **Step 7: Worktree limpo + memória**

Run: `cd /home/wital/studia && git status` (limpo). Atualizar memória `studia-padronizacao.md` (Plano 04 ✅, padrão passthrough) e criar/atualizar memória sobre o LLM proxy (base interna, virtual key, passthrough `/gemini`, embeddings ausentes no /v1).

---

## Self-Review

**Spec coverage:**
- "Consolidar IA no proxy" → Tasks 1 (chat+batch via `_get_client`) e 2 (embeddings).
- "Manter Batch 50% off" → mantido: Batch continua sendo Gemini Batch, só roteado pelo passthrough (validado SUCCEEDED).
- "Virtual key, não master" → Task 4 Step 1 (alias `studia`).
- "Comunicação por rede interna" → `LITELLM_BASE_URL=http://platform-litellm:4000` (DNS docker).
- "Provisionamento de segredo como o JWT/GEMINI" → Task 3 (build.sh) + Task 4 (.env local).

**Placeholder scan:** sem TBD/TODO; todo passo de código mostra o código real.

**Type consistency:** `ClientConfig(api_key, base_url, via_proxy)` usado igual em `_client_config()`, `_get_client()` e nos testes. `_client_config`/`_get_client` reusados por `generate_embeddings.py`.

**Riscos:**
- Ramo **JSONL/Files API** (≥20MB) com upload pelo passthrough não validado → mitigação documentada (inline cobre o caso comum; validar e, se preciso, manter esse ramo no Gemini direto). 
- **Dev sem proxy:** `LITELLM_API_KEY` ausente → fallback Gemini direto (sem quebrar dev).
- **Embeddings pelo passthrough** (`embed_content`) não validado em runtime → script CLI manual; validar quando rodar. `/v1/embeddings` do LiteLLM NÃO tem modelo registrado (não usar a rota OpenAI p/ embeddings).
