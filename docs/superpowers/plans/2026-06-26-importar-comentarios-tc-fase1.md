# Importar comentários do TC — Fase 1 (lazy) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando o usuário abre uma aba do fórum (💬 alunos ou 🎓 professor) numa questão, importar sob demanda os comentários reais do TecConcursos daquela questão, com imagens re-hospedadas no MinIO, gravando no fórum existente.

**Architecture:** O destino (tabela `questao_comentarios`, fórum por quadro, pseudônimo, render) já existe. Esta fase pluga a fonte: 2 funções de fetch no scraper + 2 rotas HTTP, um endpoint de import no backend que faz upsert idempotente e re-hospeda imagens, um marcador anti-rescrape, e um gatilho lazy no `ForumPanel`. Match por `Questao.id_externo` = `idQuestao` do TC (igual ao import de gabarito).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), httpx + BeautifulSoup + Playwright (scraper), React 19 + TanStack Query (frontend), MinIO, pytest.

## Global Constraints

- **Copy do frontend:** NENHUMA string visível ao usuário pode citar "TC", "TecConcursos", "tec" ou similar. Spinner = exatamente **"Buscando…"**. A origem é detalhe interno (backend/scraper).
- **Match:** sempre por `Questao.id_externo` (= `idQuestao` do TC).
- **Idempotência:** upsert por `QuestaoComentario.tc_comentario_id` (unique). Reimport não duplica.
- **Imagens:** re-hospedadas no MinIO sob a key `forum/{uuid}.{ext}` via `upload_bytes()`, servidas por `GET /api/q/forum/imagem/{key}` (mesmo esquema do `/forum/upload`). URL do TC nunca exposta no markdown final.
- **Pacing interativo:** o fetch lazy usa o caminho leve do `TcClient` (`client._client.get` + `client._check`), SEM as pausas longas do human-mode (igual ao `fetch_gabarito`).
- **Credenciais:** `TC_EMAIL`/`TC_PASSWORD` vivem nas envs do stack do scraper, NUNCA commitadas.
- **Segurança (SSRF):** a rota de proxy de imagem do scraper só baixa URLs cujo host termina num domínio do TC (allowlist do contrato do Task 1).
- TDD, commits frequentes, DRY, YAGNI.

---

### Task 1: Descobrir os 2 endpoints do TC (Passo 0 — bloqueador) ✅ CONCLUÍDA

> **CONCLUÍDA** (commit `d41cdba`) via DevTools/MCP (questão 2272394, logado). Contrato em
> `services/scraper/discovery/comentarios_contract.md`; fixtures reais em
> `services/scraper/tests/fixtures/coment_alunos_sample.json` e `coment_professor_sample.json`.
> Tasks 2 e 3 já refletem os shapes reais. Os passos abaixo ficam como registro histórico.

Captura, via sessão autenticada do scraper, as 2 requisições XHR que a página da questão dispara ao abrir 💬 (fórum dos alunos) e 🎓 ("Comentário em Texto" do professor). Produz um contrato escrito + 2 amostras JSON reais que servem de fixture pro Task 2.

**Files:**
- Create: `services/scraper/discovery/comentarios_contract.md`
- Create: `services/scraper/tests/fixtures/coment_alunos_sample.json`
- Create: `services/scraper/tests/fixtures/coment_professor_sample.json`
- Create (temporário): `services/scraper/scripts/capturar_comentarios.py`

**Interfaces:**
- Produces: contrato com, para cada quadro — URL exata, método, query/payload, `Referer` necessário, formato da resposta (chaves de: id do comentário, id do pai, nome do autor, tipo, curtidas, corpo HTML, data) e o(s) host(s) das imagens. As 2 amostras JSON são a resposta crua real de uma questão conhecida (`id_externo=2272394`).

- [ ] **Step 1: Script de captura via Playwright (reusa o login existente)**

```python
# services/scraper/scripts/capturar_comentarios.py
"""Abre uma questão logado e captura as XHR de comentários (alunos + professor).

Uso: python -m scripts.capturar_comentarios 2272394
Salva cada resposta JSON capturada em tests/fixtures/ e loga URL+método.
"""
from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright
from app.config import get_settings

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

async def main(qid: int) -> None:
    s = get_settings()
    capturas: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=s.tc_storage_state_path,
                                        locale="pt-BR")
        page = await ctx.new_page()

        async def on_response(resp):
            u = resp.url
            if "tecconcursos.com.br/api" in u and resp.request.method in ("GET", "POST"):
                ct = resp.headers.get("content-type", "")
                if "application/json" in ct:
                    try:
                        body = await resp.json()
                    except Exception:
                        return
                    capturas.append({"url": u, "method": resp.request.method,
                                     "post_data": resp.request.post_data, "body": body})
                    print(f"XHR {resp.request.method} {u}")

        page.on("response", on_response)
        await page.goto(f"https://www.tecconcursos.com.br/questoes/{qid}", wait_until="networkidle")
        # Abre o fórum dos alunos (💬) e o comentário do professor (🎓).
        # Os seletores reais saem da inspeção; tentar clicar nos ícones do header.
        for seletor in ['text=Fórum', '[title*="omentário"]', 'text=Comentário em Texto']:
            try:
                await page.click(seletor, timeout=3000)
                await page.wait_for_timeout(2500)
            except Exception:
                pass
        await browser.close()

    FIX.mkdir(parents=True, exist_ok=True)
    (FIX / "_capturas_raw.json").write_text(json.dumps(capturas, ensure_ascii=False, indent=2))
    print(f"\n{len(capturas)} capturas salvas em {FIX/'_capturas_raw.json'}")

if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1] if len(sys.argv) > 1 else 2272394)))
```

- [ ] **Step 2: Rodar a captura logado**

Garanta o storage_state válido (`python -m app.main login --headless` se necessário; usa `TC_EMAIL`/`TC_PASSWORD` do env). Depois:

Run: `cd services/scraper && python -m scripts.capturar_comentarios 2272394`
Expected: imprime ≥2 linhas `XHR ...` com URLs `/api/...` (uma do fórum dos alunos, uma do comentário do professor) e grava `tests/fixtures/_capturas_raw.json`.

Se nenhum XHR de comentário aparecer (conteúdo server-rendered, exige clique diferente ou captcha): PARAR e reportar — o design muda e precisa reavaliação antes de seguir.

- [ ] **Step 3: Destilar o contrato e as fixtures**

A partir de `_capturas_raw.json`, identifique as 2 requisições de comentário e:
- Escreva `services/scraper/discovery/comentarios_contract.md` documentando, para alunos e professor: URL (com `{id}`), método, payload, `Referer`, e o caminho de cada campo no JSON (`id`, pai, autor, tipo, curtidas, corpo HTML, data) + host(s) de imagem.
- Salve a resposta crua do fórum dos alunos em `tests/fixtures/coment_alunos_sample.json` e a do professor em `tests/fixtures/coment_professor_sample.json`.

- [ ] **Step 4: Remover o script temporário e o raw**

```bash
cd services/scraper && rm -f scripts/capturar_comentarios.py tests/fixtures/_capturas_raw.json
```

- [ ] **Step 5: Commit**

```bash
git add services/scraper/discovery/comentarios_contract.md services/scraper/tests/fixtures/coment_alunos_sample.json services/scraper/tests/fixtures/coment_professor_sample.json
git commit -m "feat(scraper): contrato + fixtures dos endpoints de comentários do TC (Passo 0)"
```

---

### Task 2: `tc_comentarios.py` — normalizador no scraper

Função pura que recebe a resposta crua (a fixture do Task 1) e devolve comentários normalizados. Testada contra a fixture real — sem adivinhação.

**Files:**
- Create: `services/scraper/app/scrapers/tc_comentarios.py`
- Test: `services/scraper/tests/test_tc_comentarios.py`

**Interfaces:**
- Consumes: `app.textmd.html_to_md`, fixtures do Task 1.
- Produces:
  - `normalizar_comentarios(payload: dict | list, quadro: str) -> list[dict]` onde cada item é
    `{"tc_comentario_id": int, "tc_parent_id": int|None, "autor_nome": str|None, "autor_tipo": str|None, "curtidas": int, "md": str|None, "imagens": list[str], "publicado_em": str|None}`.
  - `async def fetch_comentarios(client, id_questao: int, quadro: str) -> dict` → `{"comentarios": [<normalizado>...]}`.

- [ ] **Step 1: Teste contra a fixture real**

```python
# services/scraper/tests/test_tc_comentarios.py
import json
from pathlib import Path
from app.scrapers.tc_comentarios import normalizar_comentarios

FIX = Path(__file__).parent / "fixtures"

def _carrega(nome):
    return json.loads((FIX / nome).read_text())

def test_normaliza_alunos_valores_reais():
    out = normalizar_comentarios(_carrega("coment_alunos_sample.json"), "alunos")
    assert len(out) == 3
    c = out[0]
    assert set(c) == {"tc_comentario_id", "tc_parent_id", "autor_nome",
                      "autor_tipo", "curtidas", "md", "imagens", "publicado_em"}
    assert c["tc_comentario_id"] == 1984253
    assert c["autor_nome"] == "concurseirolol"
    assert c["autor_tipo"] == "aluno"
    assert c["curtidas"] == 1
    assert c["publicado_em"] == "02/12/2023 20:09:16"
    # 1º comentário é só uma imagem (s3) + texto
    assert any("amazonaws.com" in u or "tecconcursos" in u for u in c["imagens"])

def test_normaliza_professor_objeto_unico():
    out = normalizar_comentarios(_carrega("coment_professor_sample.json"), "professores")
    assert len(out) == 1
    c = out[0]
    assert c["autor_tipo"] == "professor"
    assert c["autor_nome"] == "Camila Rosa Vaz"
    assert c["publicado_em"] == "2024-04-28"
    assert c["md"] and "764" in c["md"]  # corpo convertido p/ markdown
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd services/scraper && python -m pytest tests/test_tc_comentarios.py -v`
Expected: FAIL com `ModuleNotFoundError: app.scrapers.tc_comentarios`.

- [ ] **Step 3: Implementar o normalizador + fetch**

Shapes reais (ver `discovery/comentarios_contract.md` + fixtures). São DOIS formatos
distintos: alunos = lista paginada em `comentarios.pageComentarios.list`; professor =
objeto único em `comentario`, sem id (sintetizar `-id_questao`).

```python
# services/scraper/app/scrapers/tc_comentarios.py
"""Comentários de uma questão no TC: fórum dos alunos (💬) e comentário do
professor (🎓). Shapes em discovery/comentarios_contract.md.
"""
from __future__ import annotations
import asyncio
from typing import Any
from bs4 import BeautifulSoup
from app.client import TcClient
from app.textmd import html_to_md
from app.observability import get_logger

log = get_logger(__name__)

DELAY_S = 1.2
MAX_PAGINAS = 40  # trava de segurança (50/pág); questões reais têm pouquíssimos


def _imagens_de(html: str | None) -> list[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [img["src"] for img in soup.find_all("img") if img.get("src")]


def _page_alunos(payload: Any) -> dict:
    return ((payload or {}).get("comentarios") or {}).get("pageComentarios") or {}


def _normalizar_alunos(payload: Any) -> list[dict]:
    out: list[dict] = []
    for it in _page_alunos(payload).get("list") or []:
        corpo = it.get("comentario")
        tipo = ("professor" if it.get("professor")
                else "administrador" if it.get("administrador") else "aluno")
        dp = it.get("dataPublicacao") or {}
        out.append({
            "tc_comentario_id": int(it["id"]),
            "tc_parent_id": None,  # fórum do TC é flat (sem thread no payload)
            "autor_nome": it.get("apelidoUsuario"),
            "autor_tipo": tipo,
            "curtidas": int(it.get("quantidadeVoto") or 0),
            "md": html_to_md(corpo),
            "imagens": _imagens_de(corpo),
            "publicado_em": (dp.get("$") if isinstance(dp, dict) else None),
        })
    return out


def _normalizar_professor(payload: Any) -> list[dict]:
    c = (payload or {}).get("comentario") or {}
    corpo = c.get("textoComentario")
    if not corpo:
        return []
    return [{
        "tc_comentario_id": None,  # TC não dá id; fetch_comentarios sintetiza -id_questao
        "tc_parent_id": None,
        "autor_nome": c.get("nomeProfessor"),
        "autor_tipo": "professor",
        "curtidas": 0,
        "md": html_to_md(corpo),
        "imagens": _imagens_de(corpo),
        "publicado_em": c.get("dataFormatadaParaHtml5"),
    }]


def normalizar_comentarios(payload: Any, quadro: str) -> list[dict]:
    return (_normalizar_professor(payload) if quadro == "professores"
            else _normalizar_alunos(payload))


async def fetch_comentarios(client: TcClient, id_questao: int, quadro: str) -> dict:
    """Busca os comentários de uma questão (caminho leve, sem human-mode)."""
    referer = f"https://www.tecconcursos.com.br/questoes/{id_questao}"

    if quadro == "professores":
        await asyncio.sleep(DELAY_S)
        path = f"/api/questoes/{id_questao}/comentario?tokenPreVisualizacao="
        r = await client._client.get(path, headers=client._build_headers(referer, None))
        client._check(r)
        coments = normalizar_comentarios(r.json(), "professores")
        for c in coments:  # sintetiza id determinístico (1 comentário/questão)
            if c["tc_comentario_id"] is None:
                c["tc_comentario_id"] = -id_questao
        log.info("tc.comentarios.fetched", id_questao=id_questao, quadro=quadro, n=len(coments))
        return {"comentarios": coments}

    # alunos: paginado (pageSize 50)
    coments: list[dict] = []
    pagina = 1
    while pagina <= MAX_PAGINAS:
        await asyncio.sleep(DELAY_S)
        path = (f"/api/discussoes/{id_questao}/comentarios-alunos"
                f"?ordenarPor=data&pagina={pagina}")
        r = await client._client.get(path, headers=client._build_headers(referer, None))
        client._check(r)
        data = r.json()
        pagina_itens = normalizar_comentarios(data, "alunos")
        coments.extend(pagina_itens)
        pg = _page_alunos(data)
        page_size = int(pg.get("pageSize") or 50)
        total_pages = int(pg.get("totalPages") or 0)
        if len(pagina_itens) < page_size or (total_pages and pagina >= total_pages):
            break
        pagina += 1

    log.info("tc.comentarios.fetched", id_questao=id_questao, quadro=quadro, n=len(coments))
    return {"comentarios": coments}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd services/scraper && python -m pytest tests/test_tc_comentarios.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add services/scraper/app/scrapers/tc_comentarios.py services/scraper/tests/test_tc_comentarios.py
git commit -m "feat(scraper): normalizar_comentarios + fetch_comentarios (alunos/professor)"
```

---

### Task 3: Rotas HTTP do scraper (comentários + proxy de imagem)

Expõe o fetch e um proxy autenticado de imagem (pro backend re-hospedar sem ter cookies do TC).

**Files:**
- Modify: `services/scraper/app/main.py` (adicionar 2 rotas após `gabarito_endpoint`, ~linha 243)

**Interfaces:**
- Consumes: `fetch_comentarios` (Task 2), `_with_tc_client` (existente).
- Produces:
  - `GET /questao/{id_questao}/comentarios?quadro=alunos|professores` → `{"comentarios": [...]}`.
  - `GET /tc/imagem?u=<url>` → `Response(bytes, media_type=<content-type>)`.

- [ ] **Step 1: Adicionar as rotas**

```python
# services/scraper/app/main.py — após gabarito_endpoint (~L243)
from fastapi import Response  # garantir no topo dos imports do FastAPI

_TC_IMG_HOSTS = ("tecconcursos.com.br", "s3-sa-east-1.amazonaws.com")  # do contrato (Task 1)


@api.get("/questao/{id_questao}/comentarios")
async def comentarios_endpoint(
    id_questao: int, quadro: str = "alunos", relogin: bool = False
) -> dict[str, Any]:
    from app.scrapers.tc_comentarios import fetch_comentarios
    if quadro not in ("alunos", "professores"):
        raise HTTPException(422, "quadro inválido")
    return await _with_tc_client(
        lambda c: fetch_comentarios(c, id_questao, quadro), relogin=relogin
    )


@api.get("/tc/imagem")
async def tc_imagem_endpoint(u: str) -> Response:
    """Baixa uma imagem do TC pela sessão autenticada (proxy p/ re-host no MinIO)."""
    from urllib.parse import urlparse
    host = (urlparse(u).hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _TC_IMG_HOSTS):
        raise HTTPException(400, "host de imagem não permitido")

    async def _baixar(client: TcClient) -> Response:
        r = await client._client.get(u, headers=client._build_headers(
            "https://www.tecconcursos.com.br/", None))
        client._check(r)
        return Response(content=r.content,
                        media_type=r.headers.get("content-type", "image/png"))

    return await _with_tc_client(_baixar)
```

- [ ] **Step 2: Verificar import e boot**

Run: `cd services/scraper && python -c "from app.main import api; print([r.path for r in api.routes if 'coment' in r.path or 'imagem' in r.path])"`
Expected: imprime `['/questao/{id_questao}/comentarios', '/tc/imagem']`.

- [ ] **Step 3: Commit**

```bash
git add services/scraper/app/main.py
git commit -m "feat(scraper): rotas /questao/{id}/comentarios e /tc/imagem (proxy autenticado)"
```

---

### Task 4: Marcador `QuestaoTcImport` + migração Alembic

Distingue "questão sem comentário" de "ainda não buscada" — evita re-scrape de questão vazia.

**Files:**
- Modify: `backend/models.py` (adicionar classe após `ComentarioVoto`, ~L699)
- Create: `backend/alembic/versions/d9f0a1b2c3e4_questao_tc_import.py`
- Test: `backend/tests/test_tc_import_marker.py`

**Interfaces:**
- Produces: model `QuestaoTcImport(id, questao_id, quadro, fetched_at, count)` com `UNIQUE(questao_id, quadro)`.

- [ ] **Step 1: Teste do model (cria e lê via unique)**

```python
# backend/tests/test_tc_import_marker.py
import pytest
from sqlalchemy import select
from models import QuestaoTcImport

@pytest.mark.asyncio
async def test_marcador_unico_por_questao_quadro(db_session):
    db_session.add(QuestaoTcImport(questao_id=1, quadro="alunos", count=3))
    await db_session.commit()
    row = (await db_session.execute(
        select(QuestaoTcImport).where(
            QuestaoTcImport.questao_id == 1, QuestaoTcImport.quadro == "alunos")
    )).scalar_one()
    assert row.count == 3 and row.fetched_at is not None
```

(Use a fixture `db_session` do `backend/tests/conftest.py`; confira o nome real e ajuste se for `session`.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_tc_import_marker.py -v`
Expected: FAIL com `ImportError: cannot import name 'QuestaoTcImport'`.

- [ ] **Step 3: Adicionar o model**

```python
# backend/models.py — após ComentarioVoto (~L699)
class QuestaoTcImport(Base):
    """Marcador: comentários do TC já buscados para (questão, quadro).

    Existência da linha = já buscado (mesmo que `count=0`). Evita re-scrape.
    """
    __tablename__ = "questao_tc_imports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), index=True
    )
    quadro: Mapped[str] = mapped_column(String(16))  # "alunos" | "professores"
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("questao_id", "quadro", name="uq_tc_import_questao_quadro"),
    )
```

(`UniqueConstraint` já é importado em models.py — confirme no topo; se não, adicione ao import de `sqlalchemy`.)

- [ ] **Step 4: Migração Alembic (head atual = b8e4f1a2c3d6)**

```python
# backend/alembic/versions/d9f0a1b2c3e4_questao_tc_import.py
"""questao_tc_imports (marcador anti-rescrape de comentários do TC)"""
from alembic import op
import sqlalchemy as sa

revision = "d9f0a1b2c3e4"
down_revision = "b8e4f1a2c3d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "questao_tc_imports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("questao_id", sa.Integer(), nullable=False),
        sa.Column("quadro", sa.String(length=16), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["questao_id"], ["questoes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("questao_id", "quadro", name="uq_tc_import_questao_quadro"),
    )
    op.create_index("ix_questao_tc_imports_questao_id", "questao_tc_imports", ["questao_id"])


def downgrade() -> None:
    op.drop_index("ix_questao_tc_imports_questao_id", table_name="questao_tc_imports")
    op.drop_table("questao_tc_imports")
```

- [ ] **Step 5: Rodar testes (model + drift de migração)**

Run: `cd backend && python -m pytest tests/test_tc_import_marker.py tests/test_alembic_no_drift.py -v`
Expected: PASS (o teste de drift confirma que o model casa com a migração).

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/alembic/versions/d9f0a1b2c3e4_questao_tc_import.py backend/tests/test_tc_import_marker.py
git commit -m "feat(forum): marcador questao_tc_imports + migração (anti-rescrape)"
```

---

### Task 5: Helper de re-host de imagem no backend

Baixa cada imagem do TC pelo proxy do scraper e re-hospeda no MinIO, devolvendo o markdown reescrito.

**Files:**
- Modify: `backend/q_router.py` (adicionar helper perto dos helpers de fórum, antes do endpoint do Task 6)
- Test: `backend/tests/test_rehost_imagens_tc.py`

**Interfaces:**
- Consumes: `upload_bytes` (já importado em q_router), `SCRAPER_URL`, `httpx`.
- Produces: `async def _rehost_imagens_tc(md: str | None, imagens: list[str], client: httpx.AsyncClient) -> str | None` — reescreve cada URL de `imagens` presente em `md` para `/api/q/forum/imagem/forum/{uuid}.{ext}`.

- [ ] **Step 1: Teste (mock do proxy + do upload)**

```python
# backend/tests/test_rehost_imagens_tc.py
import pytest, httpx
import q_router

@pytest.mark.asyncio
async def test_rehost_reescreve_url(monkeypatch):
    subiu = {}
    monkeypatch.setattr(q_router, "upload_bytes",
                        lambda key, data, ct: subiu.update({key: (data, ct)}))

    def handler(req):
        return httpx.Response(200, content=b"\x89PNG...", headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as c:
        md = "![](https://www.tecconcursos.com.br/img/a.png) fim"
        out = await q_router._rehost_imagens_tc(
            md, ["https://www.tecconcursos.com.br/img/a.png"], c)
    assert "tecconcursos.com.br" not in out
    assert "/api/q/forum/imagem/forum/" in out
    assert len(subiu) == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_rehost_imagens_tc.py -v`
Expected: FAIL com `AttributeError: module 'q_router' has no attribute '_rehost_imagens_tc'`.

- [ ] **Step 3: Implementar o helper**

```python
# backend/q_router.py — perto dos helpers de fórum (após _serializar_comentario)
_EXT_POR_CT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


async def _rehost_imagens_tc(
    md: str | None, imagens: list[str], client: httpx.AsyncClient
) -> str | None:
    """Baixa cada imagem do TC (via proxy do scraper) → MinIO → reescreve o md."""
    if not md or not imagens:
        return md
    for url in dict.fromkeys(imagens):  # dedup preservando ordem
        if url not in md:
            continue
        try:
            r = await client.get(f"{SCRAPER_URL}/tc/imagem", params={"u": url})
            if r.status_code != 200:
                continue
            ct = r.headers.get("content-type", "image/png").split(";")[0].strip()
            ext = _EXT_POR_CT.get(ct, "png")
            key = f"forum/{_uuid.uuid4()}.{ext}"
            upload_bytes(key, r.content, ct)
            md = md.replace(url, f"/api/q/forum/imagem/{key}")
        except httpx.HTTPError:
            continue
    return md
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_rehost_imagens_tc.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_rehost_imagens_tc.py
git commit -m "feat(forum): _rehost_imagens_tc (TC→MinIO) com dedup"
```

---

### Task 6: Endpoint de import lazy + upsert + marcador

O coração: dado (questão, quadro), busca no scraper, re-hospeda imagens, faz upsert idempotente e grava o marcador.

**Files:**
- Modify: `backend/q_router.py` (novo endpoint após `listar_forum`)
- Test: `backend/tests/test_importar_comentarios_tc.py`

**Interfaces:**
- Consumes: `_rehost_imagens_tc` (Task 5), `QuestaoTcImport` (Task 4), `QuestaoComentario`, `Questao`, `SCRAPER_URL`.
- Produces: `POST /api/q/questoes/{questao_id}/importar-comentarios-tc?quadro=alunos|professores` → `{ "importados": int, "count": int, "ja_importado": bool }`.

- [ ] **Step 1: Teste (mock do scraper, sem imagem; valida upsert + idempotência + marcador)**

```python
# backend/tests/test_importar_comentarios_tc.py
import pytest, httpx
from sqlalchemy import select
import q_router
from models import Questao, QuestaoComentario, QuestaoTcImport

def _mock_scraper(monkeypatch, comentarios):
    def handler(req):
        return httpx.Response(200, json={"comentarios": comentarios})
    real = httpx.AsyncClient
    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)
    monkeypatch.setattr(q_router.httpx, "AsyncClient", fake_client)

@pytest.mark.asyncio
async def test_importa_e_e_idempotente(db_session, client_autenticado, monkeypatch):
    db_session.add(Questao(id=10, id_externo=2272394, enunciado_md="x"))
    await db_session.commit()
    _mock_scraper(monkeypatch, [
        {"tc_comentario_id": 555, "tc_parent_id": None, "autor_nome": "Fulano",
         "autor_tipo": "aluno", "curtidas": 4, "md": "resp", "imagens": [],
         "publicado_em": None},
    ])
    r1 = await client_autenticado.post("/api/q/questoes/10/importar-comentarios-tc?quadro=alunos")
    assert r1.status_code == 200 and r1.json()["importados"] == 1
    r2 = await client_autenticado.post("/api/q/questoes/10/importar-comentarios-tc?quadro=alunos")
    assert r2.json()["ja_importado"] is True and r2.json()["importados"] == 0
    n = (await db_session.execute(select(QuestaoComentario).where(
        QuestaoComentario.tc_comentario_id == 555))).scalars().all()
    assert len(n) == 1  # não duplicou
    m = (await db_session.execute(select(QuestaoTcImport).where(
        QuestaoTcImport.questao_id == 10, QuestaoTcImport.quadro == "alunos"))).scalar_one()
    assert m.count == 1
```

(Confirme os nomes de fixtures (`db_session`, `client_autenticado`) no `conftest.py` e ajuste — `test_forum_api.py` mostra o padrão real.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_importar_comentarios_tc.py -v`
Expected: FAIL (404 — rota inexistente).

- [ ] **Step 3: Implementar o endpoint**

```python
# backend/q_router.py — após listar_forum (~L1971)
@router.post("/questoes/{questao_id}/importar-comentarios-tc")
async def importar_comentarios_tc(
    questao_id: int,
    quadro: Literal["alunos", "professores"] = "alunos",
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Importa (sob demanda) os comentários do TC para (questão, quadro).

    Idempotente: o marcador `QuestaoTcImport` impede re-scrape; o upsert por
    `tc_comentario_id` impede duplicar. Origem nunca exposta ao usuário.
    """
    q = (await db.execute(
        select(Questao.id_externo).where(Questao.id == questao_id)
    )).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "questão não encontrada")
    if q is None or q == 0:  # sem id_externo → não veio do TC
        return {"importados": 0, "count": 0, "ja_importado": False}
    id_externo = q

    ja = (await db.execute(
        select(QuestaoTcImport).where(
            QuestaoTcImport.questao_id == questao_id,
            QuestaoTcImport.quadro == quadro,
        )
    )).scalar_one_or_none()
    if ja is not None:
        return {"importados": 0, "count": ja.count, "ja_importado": True}

    # Busca no scraper (sessão TC + proxy vivem lá).
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=120, write=10, pool=125)
        ) as c:
            r = await c.get(
                f"{SCRAPER_URL}/questao/{id_externo}/comentarios", params={"quadro": quadro}
            )
            if r.status_code != 200:
                raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:200]}")
            coments = (r.json() or {}).get("comentarios") or []

            # tc_comentario_id já presentes (dedup global por unique).
            tc_ids = [x["tc_comentario_id"] for x in coments if x.get("tc_comentario_id")]
            existentes: set[int] = set()
            if tc_ids:
                existentes = set((await db.execute(
                    select(QuestaoComentario.tc_comentario_id).where(
                        QuestaoComentario.tc_comentario_id.in_(tc_ids))
                )).scalars().all())

            # 1ª passada: raízes; 2ª: respostas (mapeia tc_parent → id local).
            tc_para_local: dict[int, int] = {}
            importados = 0
            for passada in ("raiz", "resposta"):
                for x in coments:
                    tcid = x.get("tc_comentario_id")
                    if not tcid or tcid in existentes:
                        continue
                    eh_raiz = x.get("tc_parent_id") is None
                    if (passada == "raiz") != eh_raiz:
                        continue
                    md = await _rehost_imagens_tc(x.get("md"), x.get("imagens") or [], c)
                    parent_local = (None if eh_raiz
                                    else tc_para_local.get(x["tc_parent_id"]))
                    com = QuestaoComentario(
                        questao_id=questao_id, origem="tc", forum_tipo=quadro,
                        tc_comentario_id=tcid, tc_parent_id=x.get("tc_parent_id"),
                        parent_id=parent_local,
                        autor_nome=x.get("autor_nome"), autor_tipo=x.get("autor_tipo"),
                        curtidas=int(x.get("curtidas") or 0),
                        score=int(x.get("curtidas") or 0), texto_md=md,
                    )
                    db.add(com)
                    await db.flush()
                    tc_para_local[tcid] = com.id
                    existentes.add(tcid)
                    importados += 1
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fonte indisponível: {exc}") from exc

    total = (await db.execute(
        select(func.count()).select_from(QuestaoComentario).where(
            QuestaoComentario.questao_id == questao_id,
            QuestaoComentario.forum_tipo == quadro,
            QuestaoComentario.origem == "tc",
        )
    )).scalar_one()
    db.add(QuestaoTcImport(questao_id=questao_id, quadro=quadro, count=int(total)))
    await db.commit()
    return {"importados": importados, "count": int(total), "ja_importado": False}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_importar_comentarios_tc.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_importar_comentarios_tc.py
git commit -m "feat(forum): endpoint lazy importar-comentarios-tc (upsert idempotente + marcador)"
```

---

### Task 7: `GET …/forum` devolve `tc_importado`

Permite o front decidir se dispara a coleta lazy.

**Files:**
- Modify: `backend/q_router.py` (`listar_forum`, ~L1919-1971)
- Test: `backend/tests/test_forum_api.py` (adicionar caso) ou novo arquivo

**Interfaces:**
- Produces: o JSON de `GET /api/q/questoes/{id}/forum` passa a incluir `"tc_importado": bool`.

- [ ] **Step 1: Teste (sem marcador = false; com marcador = true)**

```python
# backend/tests/test_forum_tc_importado.py
import pytest
from models import Questao, QuestaoTcImport

@pytest.mark.asyncio
async def test_forum_expoe_flag_tc_importado(db_session, client_autenticado):
    db_session.add(Questao(id=20, id_externo=999, enunciado_md="x"))
    await db_session.commit()
    r = await client_autenticado.get("/api/q/questoes/20/forum?quadro=alunos")
    assert r.json()["tc_importado"] is False
    db_session.add(QuestaoTcImport(questao_id=20, quadro="alunos", count=0))
    await db_session.commit()
    r2 = await client_autenticado.get("/api/q/questoes/20/forum?quadro=alunos")
    assert r2.json()["tc_importado"] is True
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_forum_tc_importado.py -v`
Expected: FAIL com `KeyError: 'tc_importado'`.

- [ ] **Step 3: Adicionar a flag ao retorno**

```python
# backend/q_router.py — dentro de listar_forum, antes do `return {...}` final
    tc_importado = (await db.execute(
        select(QuestaoTcImport.id).where(
            QuestaoTcImport.questao_id == questao_id,
            QuestaoTcImport.quadro == quadro,
        )
    )).first() is not None

    return {"total": total, "comentarios": out, "tc_importado": tc_importado}
```

(Remover o `return {"total": total, "comentarios": out}` antigo.)

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_forum_tc_importado.py tests/test_forum_api.py -v`
Expected: PASS (inclusive os testes de fórum existentes — retrocompatível).

- [ ] **Step 5: Commit**

```bash
git add backend/q_router.py backend/tests/test_forum_tc_importado.py
git commit -m "feat(forum): listar_forum expõe tc_importado (gatilho do lazy)"
```

---

### Task 8: Gatilho lazy no frontend (spinner "Buscando…")

Ao abrir uma aba ainda não buscada, dispara o import e mostra "Buscando…".

**Files:**
- Modify: `fontend/app/q/hooks/useForum.ts` (campo `tc_importado` + mutation)
- Modify: `fontend/app/q/caderno/[id]/components/ForumPanel.tsx` (efeito + spinner)

**Interfaces:**
- Consumes: `POST /api/q/questoes/{id}/importar-comentarios-tc?quadro=` (Task 6), `tc_importado` (Task 7).
- Produces: `useImportarComentariosTc(questaoId, quadro)`; `ForumData.tc_importado`.

- [ ] **Step 1: Adicionar `tc_importado` ao tipo e a mutation**

```typescript
// fontend/app/q/hooks/useForum.ts — em ForumData
export interface ForumData {
  total: number;
  comentarios: Comentario[];
  tc_importado: boolean;
}
```

```typescript
// fontend/app/q/hooks/useForum.ts — nova mutation (após useCriarComentario)
export function useImportarComentariosTc(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
  return useMutation({
    mutationFn: () =>
      apiPost<{ importados: number; count: number; ja_importado: boolean }>(
        `/api/q/questoes/${questaoId}/importar-comentarios-tc?quadro=${quadro}`, {}),
    onSuccess: invalidar,
  });
}
```

- [ ] **Step 2: Disparar no `ForumPanel` (uma vez) + spinner**

```tsx
// fontend/app/q/caderno/[id]/components/ForumPanel.tsx
// imports:
import { useEffect, useRef, useState } from "react";
import {
  useCriarComentario, useForum, useImportarComentariosTc, type Quadro,
} from "../../../hooks/useForum";

// dentro de ForumPanel, após `const criar = ...`:
  const importar = useImportarComentariosTc(questaoId, quadro);
  const jaDisparou = useRef(false);
  useEffect(() => {
    if (!jaDisparou.current && data && data.tc_importado === false && !importar.isPending) {
      jaDisparou.current = true;
      importar.mutate();
    }
  }, [data, importar]);
```

```tsx
// no bloco da lista, antes do `isPending` existente:
        {(isPending || importar.isPending) && (
          <p className="py-4 text-sm text-fg-faint">Buscando…</p>
        )}
```

(Substitua a condição `{isPending && ...}` antiga por esta, para não mostrar dois spinners.)

- [ ] **Step 3: Lint + typecheck**

Run: `cd fontend && pnpm lint`
Expected: 0 errors. Verifique que NENHUMA string nova cita "TC"/"tec".

- [ ] **Step 4: Verificação manual (dev)**

Run: `./dev.sh up:d` e abra uma questão com `id_externo` conhecido; abra 💬 → deve aparecer **"Buscando…"** e em seguida os comentários; reabrir não re-busca (sem spinner).
Expected: comportamento acima; imagens renderizam via `/api/q/forum/imagem/...`.

- [ ] **Step 5: Commit**

```bash
git add fontend/app/q/hooks/useForum.ts fontend/app/q/caderno/[id]/components/ForumPanel.tsx
git commit -m "feat(forum): gatilho lazy de import + spinner 'Buscando…' no ForumPanel"
```

---

## Deploy (após todas as tasks verdes)

Conforme o workflow obrigatório do projeto:

```bash
cd /home/wital/studia && git push && ./build.sh
```

O `db_prepare` no startup roda `alembic upgrade head` (cria `questao_tc_imports`). Configure `TC_EMAIL`/`TC_PASSWORD` no env do scraper (fora do git) antes do deploy do serviço scraper.

## Self-Review (preenchido)

**Spec coverage:** lazy (Tasks 6+8) ✅ · re-host MinIO (Tasks 3,5) ✅ · abas 🎓/💬 (já existem; Task 8 dispara por quadro) ✅ · match id_externo (Task 6) ✅ · pseudônimo (já em `_display_name`) ✅ · marcador anti-rescrape (Tasks 4,6,7) ✅ · idempotência (Task 6) ✅ · copy sem "TC" (Task 8 + Global Constraints) ✅ · Passo 0 descoberta (Task 1) ✅. **Fase 2 (coleta em massa)** = plano separado (próximo).

**Placeholder scan:** sem TBD/TODO. O único ponto dependente de descoberta externa (chaves/URL do TC) está isolado em constantes (`ENDPOINT`, `K`, `_TC_IMG_HOSTS`) confirmadas contra a fixture real do Task 1 via teste — não é placeholder, é reconciliação fechada por teste.

**Type consistency:** `tc_comentario_id`, `tc_parent_id`, `autor_tipo`, `curtidas`, `md`, `imagens` consistentes entre Task 2 (scraper) → Task 6 (consumo). `tc_importado` consistente Task 7 → Task 8. `forum/{uuid}.{ext}` + `/api/q/forum/imagem/{key}` idênticos ao esquema existente.
