# Mapa da Aprovação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Usuário escolhe um concurso coletado, a IA lê o edital (PDF no MinIO) e extrai cargos/matérias/eventos; ao escolher o cargo nasce o Mapa da Aprovação: timeline de eventos, edital verticalizado com checklist, cadernos automáticos com questões da banca e data da prova pré-preenchida no cronograma.

**Architecture:** Extração estruturada 1x por concurso (cacheada em `edital_extracoes`, task Taskiq no worker), via **proxy LiteLLM da WitDev** (passthrough `/gemini`, `generate_content` — NUNCA Batch aqui). Mapa por usuário (`mapas_aprovacao` + `mapa_itens`), gate PRO na criação. Router novo `backend/mapa_router.py`; catálogo público de concursos no `concursos_router`. Frontend: wizard `/q/mapa/novo`, lista `/q/mapa`, detalhe `/q/mapa/[id]`, tudo React Query v5.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic; google-genai via LiteLLM passthrough; Taskiq/NATS (worker); Next.js 16 + React Query v5 + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-07-02-mapa-da-aprovacao-design.md` (leia antes).

## Global Constraints

- Trabalhe SEMPRE no worktree `/home/wital/studia/.claude/worktrees/mapa-da-aprovacao` (branch `worktree-mapa-da-aprovacao`). NUNCA commite na `main`.
- UI 100% em português BR. **PROIBIDO** "TC", "TecConcursos" ou "tec" em qualquer texto visível da UI (regra do projeto — use "fonte externa"/nada).
- Frontend: React Query v5 obrigatório (`useQuery`/`useMutation`, tratar `isPending`/`isError`); NUNCA `fetch` cru em `useEffect`. Carga de banco → `<Skeleton>`; operação lenta (extração do edital) → `<BrandLoader>`. Nada de dado "pulando" na tela (reservar espaço; nunca mostrar estado-vazio enquanto algo pende).
- LLM: SEMPRE via `gemini_service._get_client()` (proxy LiteLLM passthrough `/gemini`). **NUNCA Batch API** nesta feature. Modelo vem da setting `llm.mapa_edital`.
- Testes backend: `cd /home/wital/studia/.claude/worktrees/mapa-da-aprovacao/backend && python -m pytest tests/<arquivo> -v`. Suíte completa deve passar ao final de cada task (incluindo `test_alembic_no_drift.py`).
- Lint frontend: `cd /home/wital/studia/.claude/worktrees/mapa-da-aprovacao/fontend && pnpm lint`.
- Commits frequentes, mensagem em pt-BR `feat(mapa)|test(mapa)|docs(mapa): ...`, terminando com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Head atual do Alembic: `a7c8d9e0f1b2` (tc_concursos). A migration nova DEVE ter `down_revision = "a7c8d9e0f1b2"` (uma head só).

---

### Task 1: Schemas Pydantic da extração (`mapa_schemas.py`)

**Files:**
- Create: `backend/mapa_schemas.py`
- Test: `backend/tests/test_mapa_schemas.py`

**Interfaces:**
- Produces: `EditalExtraido` (Pydantic v2) com `.model_validate(dict)` e `.model_dump(mode="json")`; classes `ConcursoEdital`, `EventoEdital`, `CargoEdital`, `MateriaProgramatica`, `EtapaCargo`, `DistribuicaoQuestoes`. Tasks 4, 5 e 8 consomem.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mapa_schemas.py
"""Validação do JSON de extração do edital (shape tolerante a campos ausentes)."""
import pytest

from mapa_schemas import EditalExtraido

FIXTURE = {
    "concurso": {"orgao": "Prefeitura X", "banca": "IDECAN",
                 "taxa_inscricao": "R$ 120,00", "data_prova": "2026-09-20"},
    "eventos": [
        {"titulo": "Inscrições", "data_inicio": "2026-07-01",
         "data_fim": "2026-07-30", "tipo": "inscricao"},
        {"titulo": "Prova objetiva", "data_inicio": "2026-09-20", "tipo": "prova"},
    ],
    "cargos": [
        {"nome": "Engenheiro Civil", "escolaridade": "Superior",
         "vagas": "2 + CR", "salario": "R$ 6.500,00",
         "conteudo_programatico": [
             {"materia": "Língua Portuguesa", "assuntos": ["Interpretação de texto", "Crase"]},
             {"materia": "Engenharia Civil", "assuntos": ["Fundações", "Concreto armado"]},
         ],
         "etapas": [{"nome": "Prova objetiva", "carater": "eliminatorio"}],
         "distribuicao_questoes": [{"materia": "Língua Portuguesa", "quantidade": 10, "peso": 1.0}]},
    ],
}


def test_parse_fixture_completa():
    ext = EditalExtraido.model_validate(FIXTURE)
    assert ext.concurso.data_prova == "2026-09-20"
    assert len(ext.eventos) == 2
    assert ext.eventos[1].data_fim is None
    assert ext.cargos[0].nome == "Engenheiro Civil"
    assert ext.cargos[0].conteudo_programatico[1].assuntos == ["Fundações", "Concreto armado"]
    # roundtrip JSON-safe (vai para coluna JSON)
    assert ext.model_dump(mode="json")["cargos"][0]["vagas"] == "2 + CR"


def test_parse_vazio_nao_quebra():
    ext = EditalExtraido.model_validate({})
    assert ext.concurso.data_prova is None
    assert ext.eventos == [] and ext.cargos == []


def test_tipo_evento_desconhecido_vira_outro():
    ext = EditalExtraido.model_validate(
        {"eventos": [{"titulo": "X", "tipo": "PROVA OBJETIVA!!"}]}
    )
    assert ext.eventos[0].tipo == "outro"


def test_data_invalida_vira_none():
    ext = EditalExtraido.model_validate(
        {"eventos": [{"titulo": "X", "data_inicio": "20/09/2026", "tipo": "prova"}]}
    )
    assert ext.eventos[0].data_inicio is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/wital/studia/.claude/worktrees/mapa-da-aprovacao/backend && python -m pytest tests/test_mapa_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mapa_schemas'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/mapa_schemas.py
"""Shapes Pydantic do JSON extraído do edital (Mapa da Aprovação).

A IA pode devolver lixo parcial: tudo aqui é tolerante — campo ausente vira
None/lista vazia, tipo de evento fora do vocabulário vira "outro", data fora
do ISO vira None. NUNCA levantar por campo opcional malformado.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIPOS_EVENTO = {"inscricao", "isencao", "prova", "recurso", "resultado", "homologacao", "outro"}


def _data_iso_ou_none(v: object) -> Optional[str]:
    s = str(v).strip() if v is not None else ""
    return s if _ISO_DATE.match(s) else None


class EventoEdital(BaseModel):
    titulo: str = ""
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    tipo: str = "outro"

    @field_validator("tipo", mode="before")
    @classmethod
    def _tipo(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        return s if s in TIPOS_EVENTO else "outro"

    @field_validator("data_inicio", "data_fim", mode="before")
    @classmethod
    def _datas(cls, v: object) -> Optional[str]:
        return _data_iso_ou_none(v)


class MateriaProgramatica(BaseModel):
    materia: str = ""
    assuntos: list[str] = Field(default_factory=list)


class EtapaCargo(BaseModel):
    nome: str = ""
    carater: Optional[str] = None


class DistribuicaoQuestoes(BaseModel):
    materia: str = ""
    quantidade: Optional[int] = None
    peso: Optional[float] = None


class CargoEdital(BaseModel):
    nome: str = ""
    escolaridade: Optional[str] = None
    # Editais escrevem "CR", "2 + CR", "R$ 6.500,00" — strings livres.
    vagas: Optional[str] = None
    salario: Optional[str] = None
    requisitos: Optional[str] = None
    jornada: Optional[str] = None
    conteudo_programatico: list[MateriaProgramatica] = Field(default_factory=list)
    etapas: list[EtapaCargo] = Field(default_factory=list)
    distribuicao_questoes: list[DistribuicaoQuestoes] = Field(default_factory=list)


class ConcursoEdital(BaseModel):
    orgao: Optional[str] = None
    banca: Optional[str] = None
    taxa_inscricao: Optional[str] = None
    data_prova: Optional[str] = None

    @field_validator("data_prova", mode="before")
    @classmethod
    def _data(cls, v: object) -> Optional[str]:
        return _data_iso_ou_none(v)


class EditalExtraido(BaseModel):
    concurso: ConcursoEdital = Field(default_factory=ConcursoEdital)
    eventos: list[EventoEdital] = Field(default_factory=list)
    cargos: list[CargoEdital] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/wital/studia/.claude/worktrees/mapa-da-aprovacao/backend && python -m pytest tests/test_mapa_schemas.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/mapa_schemas.py backend/tests/test_mapa_schemas.py
git commit -m "feat(mapa): schemas Pydantic tolerantes do JSON de extração do edital

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Modelos SQLAlchemy + migration Alembic

**Files:**
- Modify: `backend/models.py` (append após `AppSetting`, fim do arquivo)
- Create: `backend/alembic/versions/b3c4d5e6f7a8_mapa_aprovacao.py`
- Test: `backend/tests/test_alembic_no_drift.py` (já existe — deve continuar passando)

**Interfaces:**
- Produces: `EditalExtracao` (tabela `edital_extracoes`: `concurso_id` unique, `status` em pendente|processando|concluido|erro, `dados` JSON, `modelo_usado`, `prompt_versao`, `erro_msg`); `MapaAprovacao` (tabela `mapas_aprovacao`); `MapaItem` (tabela `mapa_itens`). Tasks 5–9 consomem.

- [ ] **Step 1: Adicionar modelos em `backend/models.py`** (após a classe `AppSetting`, no fim do arquivo)

```python
# ─── Mapa da Aprovação ─────────────────────────────────────


class EditalExtracao(Base):
    """Extração IA do edital de um concurso coletado — 1 por concurso, compartilhada.

    O JSON `dados` segue mapa_schemas.EditalExtraido. Reextração (edital
    retificado / prompt novo) reusa a MESMA linha: status volta a "pendente"
    e `prompt_versao` incrementa.
    """
    __tablename__ = "edital_extracoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concurso_id: Mapped[int] = mapped_column(
        ForeignKey("tc_concursos.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pendente")
    dados: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    modelo_usado: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_versao: Mapped[int] = mapped_column(Integer, default=1)
    erro_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class MapaAprovacao(Base):
    """Mapa da Aprovação de um usuário para um cargo de um concurso (feature PRO).

    `cargo_dados` é snapshot do CargoEdital escolhido — reextrações futuras
    NÃO reescrevem mapas existentes.
    """
    __tablename__ = "mapas_aprovacao"
    __table_args__ = (
        UniqueConstraint("usuario_uid", "concurso_id", "cargo_nome",
                         name="uq_mapa_user_concurso_cargo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_uid: Mapped[str] = mapped_column(String(64), index=True)
    concurso_id: Mapped[int] = mapped_column(
        ForeignKey("tc_concursos.id", ondelete="CASCADE"), index=True
    )
    extracao_id: Mapped[int] = mapped_column(
        ForeignKey("edital_extracoes.id", ondelete="CASCADE")
    )
    cargo_nome: Mapped[str] = mapped_column(String(512))
    cargo_dados: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    itens: Mapped[list["MapaItem"]] = relationship(
        back_populates="mapa", cascade="all, delete-orphan", lazy="selectin",
        order_by="MapaItem.ordem",
    )


class MapaItem(Base):
    """Verticalização: 1 linha por assunto do conteúdo programático do cargo."""
    __tablename__ = "mapa_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapa_id: Mapped[int] = mapped_column(
        ForeignKey("mapas_aprovacao.id", ondelete="CASCADE"), index=True
    )
    materia_nome: Mapped[str] = mapped_column(String(512))
    assunto_texto: Mapped[str] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="nao_visto")
    materia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("materias.id", ondelete="SET NULL"), nullable=True
    )
    caderno_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="SET NULL"), nullable=True
    )

    mapa: Mapped["MapaAprovacao"] = relationship(back_populates="itens")
```

(Os imports `Integer, String, Text, DateTime, JSON, ForeignKey, UniqueConstraint, func, relationship, Mapped, mapped_column, Optional, datetime` já existem no topo de `models.py` — não adicionar duplicatas.)

- [ ] **Step 2: Criar a migration**

```python
# backend/alembic/versions/b3c4d5e6f7a8_mapa_aprovacao.py
"""mapa da aprovação: edital_extracoes + mapas_aprovacao + mapa_itens

Revision ID: b3c4d5e6f7a8
Revises: a7c8d9e0f1b2
"""
import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a7c8d9e0f1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edital_extracoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concurso_id", sa.BigInteger(),
                  sa.ForeignKey("tc_concursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pendente"),
        sa.Column("dados", sa.JSON(), nullable=True),
        sa.Column("modelo_usado", sa.String(128), nullable=True),
        sa.Column("prompt_versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("erro_msg", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_edital_extracoes_concurso_id", "edital_extracoes",
                    ["concurso_id"], unique=True)

    op.create_table(
        "mapas_aprovacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_uid", sa.String(64), nullable=False),
        sa.Column("concurso_id", sa.BigInteger(),
                  sa.ForeignKey("tc_concursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extracao_id", sa.Integer(),
                  sa.ForeignKey("edital_extracoes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cargo_nome", sa.String(512), nullable=False),
        sa.Column("cargo_dados", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("usuario_uid", "concurso_id", "cargo_nome",
                            name="uq_mapa_user_concurso_cargo"),
    )
    op.create_index("ix_mapas_aprovacao_usuario_uid", "mapas_aprovacao", ["usuario_uid"])
    op.create_index("ix_mapas_aprovacao_concurso_id", "mapas_aprovacao", ["concurso_id"])

    op.create_table(
        "mapa_itens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mapa_id", sa.Integer(),
                  sa.ForeignKey("mapas_aprovacao.id", ondelete="CASCADE"), nullable=False),
        sa.Column("materia_nome", sa.String(512), nullable=False),
        sa.Column("assunto_texto", sa.Text(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="nao_visto"),
        sa.Column("materia_id", sa.Integer(),
                  sa.ForeignKey("materias.id", ondelete="SET NULL"), nullable=True),
        sa.Column("caderno_id", sa.Integer(),
                  sa.ForeignKey("cadernos_questoes.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_mapa_itens_mapa_id", "mapa_itens", ["mapa_id"])


def downgrade() -> None:
    op.drop_table("mapa_itens")
    op.drop_table("mapas_aprovacao")
    op.drop_table("edital_extracoes")
```

⚠️ Confira o tipo real da PK de `cadernos_questoes.id` e `materias.id` (`Integer`) e de `tc_concursos.id` (`BigInteger`) — os FKs acima já respeitam isso. Se `test_alembic_no_drift` acusar diferença (ex.: variante sqlite), ajuste a migration para casar com o modelo, não o contrário.

- [ ] **Step 3: Rodar o teste de drift + suíte**

Run: `cd /home/wital/studia/.claude/worktrees/mapa-da-aprovacao/backend && python -m pytest tests/test_alembic_no_drift.py -v`
Expected: PASS (uma head só, schema == modelos)

- [ ] **Step 4: Commit**

```bash
git add backend/models.py backend/alembic/versions/b3c4d5e6f7a8_mapa_aprovacao.py
git commit -m "feat(mapa): modelos EditalExtracao/MapaAprovacao/MapaItem + migration

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Setting `llm.mapa_edital` no registry + painel admin

**Files:**
- Modify: `backend/llm_registry.py` (bloco de chaves, linhas ~30-44)
- Modify: `backend/admin_llm_router.py` (`_FIELD_TO_KEY`, `LlmSettingsPut`, import)
- Test: `backend/tests/test_admin_llm_router.py` (arquivo existente — adicionar caso) ou criar `backend/tests/test_llm_registry_mapa.py`

**Interfaces:**
- Produces: `SETTING_MAPA = "llm.mapa_edital"` exportado de `llm_registry`, default `gemini-3-flash-preview`, editável via `PUT /api/admin/llm/settings` campo `mapa_edital`. Tasks 5 e 7 consomem via `get_setting(db, SETTING_MAPA, SETTING_DEFAULTS[SETTING_MAPA])`.

- [ ] **Step 1: Teste falhando** — em `backend/tests/test_llm_registry_mapa.py`:

```python
"""Setting llm.mapa_edital: registrada, com default, exposta no painel admin."""
from llm_registry import SETTING_DEFAULTS, SETTING_MAPA


def test_setting_mapa_registrada_com_default():
    assert SETTING_MAPA == "llm.mapa_edital"
    assert SETTING_DEFAULTS[SETTING_MAPA] == "gemini-3-flash-preview"


def test_painel_admin_expoe_campo_mapa():
    from admin_llm_router import _FIELD_TO_KEY, LlmSettingsPut
    assert _FIELD_TO_KEY["mapa_edital"] == SETTING_MAPA
    assert "mapa_edital" in LlmSettingsPut.model_fields
```

Run: `python -m pytest tests/test_llm_registry_mapa.py -v` → FAIL (`ImportError: SETTING_MAPA`)

- [ ] **Step 2: Implementar** — em `llm_registry.py`, junto das chaves existentes:

```python
SETTING_MAPA = "llm.mapa_edital"
```

e no dict `SETTING_DEFAULTS`:

```python
SETTING_DEFAULTS = {
    SETTING_CALC: DEFAULT_CALC_ALIAS,
    SETTING_PDF: DEFAULT_GEMINI_MODEL,
    SETTING_CHAT: DEFAULT_GEMINI_MODEL,
    SETTING_MAPA: DEFAULT_GEMINI_MODEL,
}
```

Em `admin_llm_router.py`: adicionar `SETTING_MAPA` ao import de `llm_registry`, entrada `"mapa_edital": SETTING_MAPA` em `_FIELD_TO_KEY`, e campo `mapa_edital: Optional[str] = None` em `LlmSettingsPut`. A validação do PUT existente itera `_FIELD_TO_KEY` — verifique se o valor de `mapa_edital` é validado contra `gemini_options_from_catalog` (mesma regra de `processamento_pdf`/`chat_aula`, id Gemini upstream); siga exatamente o branch que valida `SETTING_PDF`.

- [ ] **Step 3: Rodar** `python -m pytest tests/test_llm_registry_mapa.py tests/ -k "llm" -v` → PASS (e os testes llm existentes continuam verdes)

- [ ] **Step 4: Front do painel (menor):** em `fontend/app/jobs/page.tsx` (seção "Modelos de IA" do admin — localizar por `processamento_pdf`), adicionar o card/select `mapa_edital` com rótulo "Mapa da Aprovação (leitura de edital)", espelhando o markup dos campos existentes. `pnpm lint` limpo.

- [ ] **Step 5: Commit**

```bash
git add backend/llm_registry.py backend/admin_llm_router.py backend/tests/test_llm_registry_mapa.py fontend/app/jobs/page.tsx
git commit -m "feat(mapa): setting llm.mapa_edital no registry + painel admin

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Funções de IA em `gemini_service.py` (extração + match)

**Files:**
- Modify: `backend/gemini_service.py` (append ao final, junto de `gerar_temas_discursivas`)
- Test: `backend/tests/test_gemini_mapa.py`

**Interfaces:**
- Consumes: `_get_client()`, `types`, `INLINE_MAX_BYTES`, `json` (já no módulo).
- Produces: `extrair_edital_estruturado(pdf_bytes: bytes, modelo: str) -> dict` (levanta em falha — chamador trata) e `mapear_materias(materias_edital: list[str], materias_banco: list[str], modelo: str) -> dict[str, str | None]` (nunca devolve valor fora de `materias_banco`). Ambas SÍNCRONAS (chamar com `asyncio.to_thread`), ambas via proxy.

- [ ] **Step 1: Teste falhando** — `backend/tests/test_gemini_mapa.py`:

```python
"""extrair_edital_estruturado / mapear_materias com client Gemini mockado."""
import json
from unittest.mock import MagicMock

import pytest

import gemini_service


def _mock_client(monkeypatch, text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=text)
    monkeypatch.setattr(gemini_service, "_get_client", lambda: client)
    return client


def test_extrair_edital_envia_pdf_e_parseia(monkeypatch):
    client = _mock_client(monkeypatch, json.dumps({"cargos": [{"nome": "Engenheiro Civil"}]}))
    out = gemini_service.extrair_edital_estruturado(b"%PDF-fake", "gemini-3-flash-preview")
    assert out["cargos"][0]["nome"] == "Engenheiro Civil"
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3-flash-preview"
    assert kwargs["config"].response_mime_type == "application/json"


def test_extrair_edital_recusa_pdf_gigante(monkeypatch):
    _mock_client(monkeypatch, "{}")
    with pytest.raises(ValueError, match="20MB"):
        gemini_service.extrair_edital_estruturado(b"x" * (21 * 1024 * 1024), "m")


def test_mapear_materias_filtra_fora_do_banco(monkeypatch):
    _mock_client(monkeypatch, json.dumps({"mapeamento": {
        "Língua Portuguesa": "Português",
        "Raciocínio Lógico": "Matemágica Inventada",
    }}))
    out = gemini_service.mapear_materias(
        ["Língua Portuguesa", "Raciocínio Lógico"], ["Português", "Matemática"], "m"
    )
    assert out == {"Língua Portuguesa": "Português", "Raciocínio Lógico": None}


def test_mapear_materias_listas_vazias_sem_ia(monkeypatch):
    client = _mock_client(monkeypatch, "{}")
    assert gemini_service.mapear_materias(["A"], [], "m") == {"A": None}
    client.models.generate_content.assert_not_called()
```

Run: `python -m pytest tests/test_gemini_mapa.py -v` → FAIL (`AttributeError`)

- [ ] **Step 2: Implementar** — append em `gemini_service.py`:

```python
# ─── Mapa da Aprovação ─────────────────────────────────────

PROMPT_EDITAL = """Você é um analista de concursos públicos. Leia o EDITAL em PDF anexo e extraia os dados abaixo em JSON VÁLIDO.

REGRAS:
- NUNCA invente dados: campo ausente no edital fica null (listas ficam vazias).
- Datas SEMPRE em ISO "YYYY-MM-DD". Períodos usam data_inicio e data_fim.
- Copie nomes de cargos e matérias EXATAMENTE como escritos no edital.
- conteudo_programatico: TODAS as matérias do cargo com a lista COMPLETA de assuntos (cada item do programa é um assunto). Não resuma nem agrupe.
- eventos: todos os prazos do cronograma do edital. tipo ∈ {inscricao, isencao, prova, recurso, resultado, homologacao, outro}.
- vagas/salario/taxa_inscricao: strings livres como estão no edital (ex.: "2 + CR", "R$ 6.500,00").

FORMATO:
{"concurso": {"orgao": null, "banca": null, "taxa_inscricao": null, "data_prova": null},
 "eventos": [{"titulo": "", "data_inicio": null, "data_fim": null, "tipo": "outro"}],
 "cargos": [{"nome": "", "escolaridade": null, "vagas": null, "salario": null,
             "requisitos": null, "jornada": null,
             "conteudo_programatico": [{"materia": "", "assuntos": [""]}],
             "etapas": [{"nome": "", "carater": null}],
             "distribuicao_questoes": [{"materia": "", "quantidade": null, "peso": null}]}]}
Responda APENAS o JSON."""


def extrair_edital_estruturado(pdf_bytes: bytes, modelo: str) -> dict:
    """Extrai a estrutura do edital (cargos/matérias/eventos) em JSON.

    Via proxy LiteLLM (mesmo _get_client de sempre) — NUNCA Batch: o usuário
    espera na tela. Levanta em falha (chamador marca status=erro).
    """
    if len(pdf_bytes) > INLINE_MAX_BYTES:
        raise ValueError("edital maior que 20MB — não suportado")
    client = _get_client()
    response = client.models.generate_content(
        model=modelo,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            PROMPT_EDITAL,
        ],
        config=types.GenerateContentConfig(
            temperature=0.2, response_mime_type="application/json"
        ),
    )
    data = json.loads(response.text)
    if not isinstance(data, dict):
        raise ValueError("IA não devolveu um objeto JSON")
    return data


def mapear_materias(
    materias_edital: list[str], materias_banco: list[str], modelo: str
) -> dict[str, str | None]:
    """De-para matéria do edital → matéria do nosso banco (ou None sem correspondência).

    Só devolve valores que existem EXATAMENTE em `materias_banco` — resposta
    fora da lista vira None (a IA não pode inventar matéria).
    """
    if not materias_edital:
        return {}
    if not materias_banco:
        return {m: None for m in materias_edital}
    prompt = (
        "Faça o de-para entre matérias de um edital de concurso e as matérias "
        "de um banco de questões. Para cada matéria do edital, escolha a matéria "
        "do banco de MESMO conteúdo, ou null se não houver equivalente claro. "
        "Use SOMENTE nomes exatos da lista do banco.\n"
        f"MATÉRIAS DO EDITAL: {json.dumps(materias_edital, ensure_ascii=False)}\n"
        f"MATÉRIAS DO BANCO: {json.dumps(materias_banco, ensure_ascii=False)}\n"
        'Responda APENAS JSON: {"mapeamento": {"<materia do edital>": "<materia do banco ou null>"}}'
    )
    client = _get_client()
    response = client.models.generate_content(
        model=modelo,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.0, response_mime_type="application/json"
        ),
    )
    data = json.loads(response.text)
    bruto = data.get("mapeamento", {}) if isinstance(data, dict) else {}
    validos = set(materias_banco)
    return {
        m: (bruto.get(m) if isinstance(bruto.get(m), str) and bruto.get(m) in validos else None)
        for m in materias_edital
    }
```

- [ ] **Step 3: Rodar** `python -m pytest tests/test_gemini_mapa.py -v` → 4 passed

- [ ] **Step 4: Commit**

```bash
git add backend/gemini_service.py backend/tests/test_gemini_mapa.py
git commit -m "feat(mapa): extração estruturada do edital + match de matérias via proxy LLM

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `mapa_service.executar_extracao` + task no worker

**Files:**
- Create: `backend/mapa_service.py`
- Modify: `backend/worker.py` (nova task no final, junto de `scrape_caderno_tc`)
- Test: `backend/tests/test_mapa_service.py`

**Interfaces:**
- Consumes: `EditalExtracao`, `TcConcursoArquivo` (Task 2), `extrair_edital_estruturado` (Task 4), `EditalExtraido` (Task 1), `minio_client.download_bytes`.
- Produces: `async executar_extracao(db: AsyncSession, concurso_id: int, modelo: str) -> dict` — transiciona pendente→processando→concluido|erro; idempotente (skip em concluido/processando). Worker task `extrair_edital_task(concurso_id: int, modelo: str)`. Task 7 enfileira via `.kiq()`.

- [ ] **Step 1: Teste falhando** — `backend/tests/test_mapa_service.py`:

```python
"""executar_extracao: transições de status, PDF via MinIO, IA mockada."""
import pytest
from sqlalchemy import select

import mapa_service
from models import EditalExtracao, TcConcurso, TcConcursoArquivo

pytestmark = pytest.mark.asyncio


async def _seed_concurso(db, com_edital=True) -> TcConcurso:
    c = TcConcurso(concurso_id_externo=111, nome_completo="Concurso X",
                   url_concurso="x", banca_nome="IDECAN — Instituto", ano=2026)
    db.add(c)
    await db.flush()
    if com_edital:
        db.add(TcConcursoArquivo(concurso_id=c.id, tipo="EDITAL",
                                 arquivo_id_externo=1, uuid="u1",
                                 nome_arquivo="edital.pdf",
                                 minio_object_key="concursos/u1.pdf"))
    db.add(EditalExtracao(concurso_id=c.id, status="pendente"))
    await db.commit()
    return c


async def test_extracao_feliz(db_session, monkeypatch):
    c = await _seed_concurso(db_session)
    monkeypatch.setattr(mapa_service, "download_bytes", lambda k: b"%PDF")
    monkeypatch.setattr(
        mapa_service, "extrair_edital_estruturado",
        lambda pdf, modelo: {"cargos": [{"nome": "Engenheiro Civil"}]},
    )
    await mapa_service.executar_extracao(db_session, c.id, "gemini-3-flash-preview")
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "concluido"
    assert ext.dados["cargos"][0]["nome"] == "Engenheiro Civil"
    assert ext.modelo_usado == "gemini-3-flash-preview"


async def test_extracao_ia_falha_marca_erro(db_session, monkeypatch):
    c = await _seed_concurso(db_session)
    monkeypatch.setattr(mapa_service, "download_bytes", lambda k: b"%PDF")

    def _boom(pdf, modelo):
        raise RuntimeError("proxy indisponível")

    monkeypatch.setattr(mapa_service, "extrair_edital_estruturado", _boom)
    await mapa_service.executar_extracao(db_session, c.id, "m")
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "erro"
    assert "proxy indisponível" in ext.erro_msg


async def test_extracao_sem_edital_marca_erro(db_session):
    c = await _seed_concurso(db_session, com_edital=False)
    await mapa_service.executar_extracao(db_session, c.id, "m")
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "erro"


async def test_extracao_concluida_e_skip(db_session, monkeypatch):
    c = await _seed_concurso(db_session)
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    ext.status = "concluido"
    await db_session.commit()
    out = await mapa_service.executar_extracao(db_session, c.id, "m")
    assert out["status"] == "skip"
```

Run: `python -m pytest tests/test_mapa_service.py -v` → FAIL (módulo não existe)

- [ ] **Step 2: Implementar `backend/mapa_service.py`**

```python
"""Serviço do Mapa da Aprovação: extração do edital (chamado pelo worker).

Separado do router para ser testável sem NATS: o worker é um wrapper fino.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gemini_service import extrair_edital_estruturado
from mapa_schemas import EditalExtraido
from minio_client import download_bytes
from models import EditalExtracao, TcConcursoArquivo


async def executar_extracao(db: AsyncSession, concurso_id: int, modelo: str) -> dict:
    """Roda a extração IA do edital de um concurso. Idempotente por status.

    pendente/erro → processando → concluido|erro. Falha NUNCA propaga (o
    worker não deve reentregar um job de IA caro): fica registrada em erro_msg.
    """
    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso_id)
        )
    ).scalar_one_or_none()
    if ext is None:
        return {"error": f"extração do concurso {concurso_id} não registrada"}
    if ext.status in ("concluido", "processando"):
        return {"status": "skip", "motivo": ext.status}

    ext.status = "processando"
    ext.modelo_usado = modelo
    ext.erro_msg = None
    await db.commit()

    try:
        arq = (
            await db.execute(
                select(TcConcursoArquivo)
                .where(
                    TcConcursoArquivo.concurso_id == concurso_id,
                    TcConcursoArquivo.tipo == "EDITAL",
                )
                .order_by(TcConcursoArquivo.arquivo_id_externo)
            )
        ).scalars().first()
        if arq is None:
            raise RuntimeError("concurso sem arquivo de edital")

        pdf_bytes = await asyncio.to_thread(download_bytes, arq.minio_object_key)
        bruto = await asyncio.to_thread(extrair_edital_estruturado, pdf_bytes, modelo)
        dados = EditalExtraido.model_validate(bruto)  # normaliza datas/tipos
        if not dados.cargos:
            raise RuntimeError("IA não encontrou nenhum cargo no edital")
        ext.dados = dados.model_dump(mode="json")
        ext.status = "concluido"
    except Exception as exc:  # noqa: BLE001 — falha vira status visível, nunca crash
        ext.status = "erro"
        ext.erro_msg = str(exc)[:2000]
    await db.commit()
    return {"status": ext.status}
```

- [ ] **Step 3: Task no worker** — append em `backend/worker.py` (depois de `scrape_questoes_tc`):

```python
@broker.task
async def extrair_edital_task(concurso_id: int, modelo: str = "gemini-3-flash-preview"):
    """Extração IA do edital (Mapa da Aprovação) — generate_content via proxy, sem Batch."""
    from mapa_service import executar_extracao

    async with async_session() as db:
        return await executar_extracao(db, concurso_id, modelo)
```

- [ ] **Step 4: Rodar** `python -m pytest tests/test_mapa_service.py -v` → 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/mapa_service.py backend/worker.py backend/tests/test_mapa_service.py
git commit -m "feat(mapa): executar_extracao (mapa_service) + task extrair_edital no worker

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Catálogo de concursos para usuário logado

**Files:**
- Modify: `backend/concursos_router.py` (novo endpoint após `listar_concursos`)
- Test: `backend/tests/test_concursos_catalogo.py`

**Interfaces:**
- Consumes: `require_user` (de `auth`), `TcConcurso`, `TcConcursoArquivo`, `_concurso_dict`.
- Produces: `GET /api/q/concursos/catalogo?busca=&page=&page_size=` → `{"items": [...], "total": N}` (mesmo shape de `listar_concursos`), somente concursos com ≥1 arquivo `EDITAL`, qualquer usuário logado. Task 10/11 consomem no front.

- [ ] **Step 1: Teste falhando** — `backend/tests/test_concursos_catalogo.py`:

```python
"""GET /api/q/concursos/catalogo: user comum vê só concursos com edital."""
import pytest

from models import TcConcurso, TcConcursoArquivo
from tests.conftest import make_user

pytestmark = pytest.mark.asyncio


async def _seed(db):
    com = TcConcurso(concurso_id_externo=1, nome_completo="Prefeitura A — IDECAN",
                     url_concurso="a", banca_nome="IDECAN", ano=2026)
    sem = TcConcurso(concurso_id_externo=2, nome_completo="Prefeitura B",
                     url_concurso="b", ano=2025)
    db.add_all([com, sem])
    await db.flush()
    db.add(TcConcursoArquivo(concurso_id=com.id, tipo="EDITAL", arquivo_id_externo=1,
                             uuid="u", nome_arquivo="e.pdf", minio_object_key="k"))
    db.add(TcConcursoArquivo(concurso_id=sem.id, tipo="PROVA_OBJETIVA", arquivo_id_externo=2,
                             uuid="u2", nome_arquivo="p.pdf", minio_object_key="k2"))
    await db.commit()


async def test_catalogo_so_com_edital(client, db_session, auth_state):
    await _seed(db_session)
    auth_state["user"] = make_user("u1")  # usuário comum, não admin
    r = await client.get("/api/q/concursos/catalogo")
    assert r.status_code == 200
    nomes = [c["nome_completo"] for c in r.json()["items"]]
    assert nomes == ["Prefeitura A — IDECAN"]


async def test_catalogo_exige_login(client, auth_state):
    auth_state["user"] = None
    r = await client.get("/api/q/concursos/catalogo")
    assert r.status_code == 401


async def test_catalogo_busca(client, db_session, auth_state):
    await _seed(db_session)
    auth_state["user"] = make_user("u1")
    r = await client.get("/api/q/concursos/catalogo?busca=IDECAN")
    assert r.json()["total"] == 1
```

> Ajuste os nomes de fixture (`client`, `db_session`, `auth_state`, `make_user`) ao contrato REAL de `tests/conftest.py` — leia o conftest e espelhe um teste existente de router (ex.: `test_cronograma_router.py`) antes de escrever.

Run: `python -m pytest tests/test_concursos_catalogo.py -v` → FAIL (404)

- [ ] **Step 2: Implementar** — em `concursos_router.py`, após `listar_concursos` (importar `require_user` de `auth`):

```python
@router.get("/catalogo")
async def catalogo_concursos(
    busca: str | None = None,
    page: int = 1,
    page_size: int = 24,
    _user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Catálogo para o Mapa da Aprovação (qualquer usuário logado).

    Diferente de `listar_concursos` (admin), só mostra concursos que têm
    arquivo de EDITAL — sem edital não há o que extrair.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    tem_edital = select(TcConcursoArquivo.concurso_id).where(
        TcConcursoArquivo.tipo == "EDITAL"
    )
    base = select(TcConcurso).where(TcConcurso.id.in_(tem_edital))
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        base = base.where(
            or_(
                TcConcurso.nome_completo.ilike(termo),
                TcConcurso.orgao_nome.ilike(termo),
                TcConcurso.orgao_sigla.ilike(termo),
                TcConcurso.banca_nome.ilike(termo),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(TcConcurso.ano.desc().nullslast(), TcConcurso.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()
    return {"items": [_concurso_dict(c) for c in rows], "total": int(total)}
```

- [ ] **Step 3: Rodar** `python -m pytest tests/test_concursos_catalogo.py -v` → 3 passed

- [ ] **Step 4: Commit**

```bash
git add backend/concursos_router.py backend/tests/test_concursos_catalogo.py
git commit -m "feat(mapa): catálogo de concursos com edital para usuário logado

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: `mapa_router.py` — extração (POST /extrair + GET /extracao)

**Files:**
- Create: `backend/mapa_router.py`
- Modify: `backend/main.py` (import + `app.include_router(mapa_router)` junto dos outros)
- Test: `backend/tests/test_mapa_router.py`

**Interfaces:**
- Consumes: `EditalExtracao`, `TcConcurso`, `TcConcursoArquivo`, `require_user`, `get_setting`/`SETTING_MAPA`/`SETTING_DEFAULTS`, `extrair_edital_task` (Task 5).
- Produces: router `/api/q/mapas`; `POST /api/q/mapas/extrair {concurso_id}` → 202 `{"status": ...}`; `GET /api/q/mapas/extracao/{concurso_id}` → `{"status", "erro_msg", "dados"?}` (dados só quando concluído). Tasks 8-9 estendem este arquivo.

- [ ] **Step 1: Testes falhando** — `backend/tests/test_mapa_router.py` (primeiro bloco):

```python
"""Mapa da Aprovação — extração: enfileira, faz polling, idempotência."""
import pytest
from sqlalchemy import select

from models import EditalExtracao, TcConcurso, TcConcursoArquivo
from tests.conftest import make_user

pytestmark = pytest.mark.asyncio

DADOS_OK = {
    "concurso": {"data_prova": "2026-09-20"},
    "eventos": [{"titulo": "Prova", "data_inicio": "2026-09-20", "tipo": "prova"}],
    "cargos": [{"nome": "Engenheiro Civil",
                "conteudo_programatico": [
                    {"materia": "Língua Portuguesa", "assuntos": ["Crase", "Concordância"]},
                ]}],
}


async def seed_concurso(db, *, com_edital=True) -> TcConcurso:
    c = TcConcurso(concurso_id_externo=99, nome_completo="Prefeitura X — 2026",
                   url_concurso="x", banca_nome="IDECAN — Instituto de Desenvolvimento",
                   orgao_sigla="PMX", ano=2026)
    db.add(c)
    await db.flush()
    if com_edital:
        db.add(TcConcursoArquivo(concurso_id=c.id, tipo="EDITAL", arquivo_id_externo=1,
                                 uuid="u", nome_arquivo="e.pdf", minio_object_key="k"))
    await db.commit()
    return c


@pytest.fixture(autouse=True)
def _sem_fila(monkeypatch):
    """Extração não vai pro NATS em teste: kiq vira no-op registrando chamadas."""
    import mapa_router

    chamadas: list[tuple] = []

    class FakeTask:
        async def kiq(self, *a, **kw):
            chamadas.append(a)

    monkeypatch.setattr(mapa_router, "extrair_edital_task", FakeTask())
    return chamadas


async def test_extrair_cria_registro_e_enfileira(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 202
    assert r.json()["status"] == "pendente"
    assert len(_sem_fila) == 1
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "pendente"


async def test_extrair_concluido_nao_reenfileira(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 202
    assert r.json()["status"] == "concluido"
    assert _sem_fila == []


async def test_extrair_sem_edital_409(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session, com_edital=False)
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas/extrair", json={"concurso_id": c.id})
    assert r.status_code == 409


async def test_polling_extracao(client, db_session, auth_state):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.get(f"/api/q/mapas/extracao/{c.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "concluido"
    assert body["dados"]["cargos"][0]["nome"] == "Engenheiro Civil"
```

Run: `python -m pytest tests/test_mapa_router.py -v` → FAIL (404)

- [ ] **Step 2: Criar `backend/mapa_router.py`** (esqueleto + extração):

```python
"""Endpoints `/api/q/mapas/*` — Mapa da Aprovação.

Extração do edital é compartilhada por concurso (1 linha em edital_extracoes,
qualquer logado dispara — o resultado serve a todos). Criar/gerir o Mapa em si
é feature PRO (Tasks seguintes).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_admin, require_user
from database import get_db
from entitlements import acesso_pro_ativo
from llm_registry import SETTING_DEFAULTS, SETTING_MAPA, get_setting
from models import (
    EditalExtracao,
    MapaAprovacao,
    MapaItem,
    TcConcurso,
    TcConcursoArquivo,
)
from worker import extrair_edital_task

router = APIRouter(prefix="/api/q/mapas", tags=["mapa-aprovacao"])


class ExtrairReq(BaseModel):
    concurso_id: int


async def _concurso_ou_404(db: AsyncSession, concurso_id: int) -> TcConcurso:
    c = (
        await db.execute(select(TcConcurso).where(TcConcurso.id == concurso_id))
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Concurso não encontrado")
    return c


@router.post("/extrair", status_code=status.HTTP_202_ACCEPTED)
async def extrair_edital(
    req: ExtrairReq,
    _user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dispara (ou reaproveita) a extração IA do edital. Idempotente.

    concluido/processando → devolve o status sem reenfileirar; pendente/erro
    → (re)enfileira no worker.
    """
    concurso = await _concurso_ou_404(db, req.concurso_id)
    tem_edital = (
        await db.execute(
            select(TcConcursoArquivo.id).where(
                TcConcursoArquivo.concurso_id == concurso.id,
                TcConcursoArquivo.tipo == "EDITAL",
            )
        )
    ).first()
    if tem_edital is None:
        raise HTTPException(409, "Este concurso não tem edital coletado")

    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso.id)
        )
    ).scalar_one_or_none()
    if ext is not None and ext.status in ("concluido", "processando"):
        return {"status": ext.status}

    if ext is None:
        ext = EditalExtracao(concurso_id=concurso.id, status="pendente")
        db.add(ext)
    else:  # erro → nova tentativa
        ext.status = "pendente"
        ext.erro_msg = None
    await db.commit()

    modelo = await get_setting(db, SETTING_MAPA, SETTING_DEFAULTS[SETTING_MAPA])
    await extrair_edital_task.kiq(concurso.id, modelo)
    return {"status": "pendente"}


@router.get("/extracao/{concurso_id}")
async def status_extracao(
    concurso_id: int,
    _user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Polling do wizard: status + dados quando concluído."""
    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso_id)
        )
    ).scalar_one_or_none()
    if ext is None:
        return {"status": "nao_iniciada", "erro_msg": None}
    out: dict[str, Any] = {"status": ext.status, "erro_msg": ext.erro_msg}
    if ext.status == "concluido":
        out["dados"] = ext.dados
    return out
```

Em `main.py`, junto dos outros routers: `from mapa_router import router as mapa_router` + `app.include_router(mapa_router)` (espelhe as linhas 139-170).

⚠️ `from worker import extrair_edital_task` importa o módulo do worker no processo da API — `main.py` já faz isso para `processar_aula`; siga o mesmo caminho de import que `main.py` usa (verifique se é `from worker import ...` direto e reuse).

- [ ] **Step 3: Rodar** `python -m pytest tests/test_mapa_router.py tests/ -v` → novos passam, suíte verde

- [ ] **Step 4: Commit**

```bash
git add backend/mapa_router.py backend/main.py backend/tests/test_mapa_router.py
git commit -m "feat(mapa): endpoints de extração do edital (disparo idempotente + polling)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Criação do Mapa (PRO) — match de matérias + cadernos automáticos + itens

**Files:**
- Modify: `backend/mapa_router.py`
- Modify: `backend/mapa_service.py` (helpers de match/caderno)
- Test: `backend/tests/test_mapa_router.py` (novo bloco)

**Interfaces:**
- Consumes: `mapear_materias` (Task 4), `Materia`, `Banca`, `Questao`, `Prova`, `CadernoQuestoes`, `acesso_pro_ativo`.
- Produces: `POST /api/q/mapas {concurso_id, cargo_nome}` → `{"id", "redirect", "cadernos_criados", "total_questoes"}`; helpers em `mapa_service`: `resolver_banca_id(db, banca_nome) -> int | None`, `questao_ids_para(db, banca_id, materia_id, cap=500) -> list[int]`, `async montar_mapa(db, user_uid, concurso, ext, cargo: dict, modelo: str) -> MapaAprovacao`.

- [ ] **Step 1: Testes falhando** — adicionar em `test_mapa_router.py`:

```python
from models import Banca, CadernoQuestoes, MapaAprovacao, MapaItem, Materia, Prova, Questao


async def _seed_banco_questoes(db) -> None:
    """Banca IDECAN + matéria Português + 3 questões (1 anulada)."""
    banca = Banca(nome="Instituto de Desenvolvimento — IDECAN", slug="idecan", sigla="IDECAN")
    mat = Materia(nome="Português")
    db.add_all([banca, mat])
    await db.flush()
    prova = Prova(banca_id=banca.id, ano=2024)
    db.add(prova)
    await db.flush()
    db.add_all([
        Questao(banca_id=banca.id, materia_id=mat.id, prova_id=prova.id, gabarito="A"),
        Questao(banca_id=banca.id, materia_id=mat.id, prova_id=prova.id, gabarito="B"),
        Questao(banca_id=banca.id, materia_id=mat.id, prova_id=prova.id,
                status="ANULADA", gabarito="ANULADA"),
    ])
    await db.commit()


@pytest.fixture
def _pro(monkeypatch):
    import mapa_router
    async def _sim(db, uid):
        return True
    monkeypatch.setattr(mapa_router, "acesso_pro_ativo", _sim)


@pytest.fixture
def _match_ia(monkeypatch):
    import mapa_service
    def _fake(materias_edital, materias_banco, modelo):
        return {"Língua Portuguesa": "Português"}
    monkeypatch.setattr(mapa_service, "mapear_materias", _fake)


async def test_criar_mapa_completo(client, db_session, auth_state, _pro, _match_ia):
    c = await seed_concurso(db_session)
    await _seed_banco_questoes(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")

    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cadernos_criados"] == 1
    assert body["total_questoes"] == 2  # anulada ficou fora

    mapa = (await db_session.execute(select(MapaAprovacao))).scalar_one()
    assert mapa.cargo_nome == "Engenheiro Civil"
    itens = (await db_session.execute(
        select(MapaItem).where(MapaItem.mapa_id == mapa.id).order_by(MapaItem.ordem)
    )).scalars().all()
    assert [i.assunto_texto for i in itens] == ["Crase", "Concordância"]
    assert all(i.caderno_id is not None for i in itens)  # matéria com match ganhou caderno
    cad = (await db_session.execute(select(CadernoQuestoes))).scalar_one()
    assert cad.owner_uid == "u1"
    assert len(cad.question_ids) == 2


async def test_criar_mapa_sem_pro_403(client, db_session, auth_state, _match_ia, monkeypatch):
    import mapa_router

    async def _nao_pro(db, uid):
        return False

    # Não usar o acesso_pro_ativo real: tabelas de billing podem não existir
    # no banco de teste — o contrato aqui é só "sem PRO → 403".
    monkeypatch.setattr(mapa_router, "acesso_pro_ativo", _nao_pro)
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 403


async def test_criar_mapa_cargo_inexistente_404(client, db_session, auth_state, _pro):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Fiscal"})
    assert r.status_code == 404


async def test_criar_mapa_duplicado_409(client, db_session, auth_state, _pro, _match_ia):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    await client.post("/api/q/mapas", json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    r = await client.post("/api/q/mapas", json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 409
    assert "id" in r.json()["detail"] if isinstance(r.json().get("detail"), dict) else True


async def test_criar_mapa_ia_match_fora_nao_quebra(client, db_session, auth_state, _pro, monkeypatch):
    """IA de match indisponível → mapa nasce sem cadernos, sem 500."""
    import mapa_service
    def _boom(a, b, m):
        raise RuntimeError("proxy fora")
    monkeypatch.setattr(mapa_service, "mapear_materias", _boom)
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    assert r.status_code == 200
    assert r.json()["cadernos_criados"] == 0
```

Run → FAIL

- [ ] **Step 2: Helpers em `mapa_service.py`** (append):

```python
import re as _re

from sqlalchemy import func, or_

from gemini_service import mapear_materias
from models import Banca, CadernoQuestoes, MapaAprovacao, MapaItem, Materia, Prova, Questao


def _sigla_da_banca(banca_nome: str | None) -> str | None:
    """Primeiro token "sigla-like" do nome vindo da fonte (ex.: "IDECAN — Inst..." → IDECAN)."""
    if not banca_nome:
        return None
    token = _re.split(r"[—\-–(/]", banca_nome, maxsplit=1)[0].strip()
    return token or None


async def resolver_banca_id(db: AsyncSession, banca_nome: str | None) -> int | None:
    """Casa a banca do concurso com a tabela `bancas` (sigla exata > nome ilike)."""
    sigla = _sigla_da_banca(banca_nome)
    if not sigla:
        return None
    row = (
        await db.execute(
            select(Banca.id).where(
                or_(
                    func.upper(Banca.sigla) == sigla.upper(),
                    Banca.nome.ilike(f"%{sigla}%"),
                )
            ).order_by(Banca.id)
        )
    ).scalars().first()
    return row


async def questao_ids_para(
    db: AsyncSession, banca_id: int, materia_id: int, cap: int = 500
) -> list[int]:
    """Questões da banca+matéria, não-anuladas, mais recentes primeiro (ano da prova)."""
    rows = (
        await db.execute(
            select(Questao.id)
            .outerjoin(Prova, Questao.prova_id == Prova.id)
            .where(
                Questao.banca_id == banca_id,
                Questao.materia_id == materia_id,
                or_(Questao.status.is_(None), Questao.status != "ANULADA"),
                ~func.upper(func.coalesce(Questao.gabarito, "")).like("ANULADA%"),
            )
            .order_by(Prova.ano.desc().nullslast(), Questao.id.desc())
            .limit(cap)
        )
    ).scalars().all()
    return [int(q) for q in rows]


async def montar_mapa(
    db: AsyncSession,
    user_uid: str,
    concurso,  # TcConcurso
    extracao: "EditalExtracao",
    cargo: dict,
    modelo: str,
) -> tuple[MapaAprovacao, int, int]:
    """Cria MapaAprovacao + itens + cadernos automáticos. Retorna (mapa, n_cadernos, n_questoes).

    Falha da IA de match NÃO propaga: mapa nasce sem cadernos (itens sem
    materia_id/caderno_id) — o usuário ainda ganha timeline + verticalização.
    """
    mapa = MapaAprovacao(
        usuario_uid=user_uid,
        concurso_id=concurso.id,
        extracao_id=extracao.id,
        cargo_nome=cargo.get("nome") or "Cargo",
        cargo_dados=cargo,
    )
    db.add(mapa)
    await db.flush()

    programatico = cargo.get("conteudo_programatico") or []
    materias_edital = [m.get("materia", "") for m in programatico if m.get("materia")]
    materias_banco = (
        (await db.execute(select(Materia.nome))).scalars().all() if materias_edital else []
    )

    mapeamento: dict[str, str | None] = {}
    try:
        if materias_edital and materias_banco:
            mapeamento = await asyncio.to_thread(
                mapear_materias, materias_edital, list(materias_banco), modelo
            )
    except Exception:  # noqa: BLE001 — match é bônus, nunca bloqueia o mapa
        mapeamento = {}

    materia_id_por_nome: dict[str, int] = {}
    if any(mapeamento.values()):
        rows = (
            await db.execute(
                select(Materia.id, Materia.nome).where(
                    Materia.nome.in_([v for v in mapeamento.values() if v])
                )
            )
        ).all()
        materia_id_por_nome = {nome: mid for mid, nome in rows}

    banca_id = await resolver_banca_id(db, concurso.banca_nome)
    pasta = f"🗺️ {concurso.orgao_sigla or concurso.nome_completo[:60]}"

    n_cadernos = 0
    n_questoes = 0
    ordem = 0
    for bloco in programatico:
        nome_edital = bloco.get("materia") or "Matéria"
        materia_banco = mapeamento.get(nome_edital)
        materia_id = materia_id_por_nome.get(materia_banco) if materia_banco else None

        caderno_id: int | None = None
        if materia_id and banca_id:
            ids = await questao_ids_para(db, banca_id, materia_id)
            if ids:
                caderno = CadernoQuestoes(
                    owner_uid=user_uid,
                    nome=f"🗺️ {nome_edital}",
                    pasta=pasta,
                    filtros={"origem": "mapa_aprovacao", "concurso_id": concurso.id,
                             "banca_id": banca_id, "materia_id": materia_id},
                    question_ids=ids,
                    total=len(ids),
                )
                db.add(caderno)
                await db.flush()
                caderno_id = caderno.id
                n_cadernos += 1
                n_questoes += len(ids)

        assuntos = bloco.get("assuntos") or []
        if not assuntos:
            assuntos = [nome_edital]  # matéria sem itens vira 1 item genérico
        for assunto in assuntos:
            db.add(MapaItem(
                mapa_id=mapa.id, materia_nome=nome_edital,
                assunto_texto=str(assunto), ordem=ordem,
                materia_id=materia_id, caderno_id=caderno_id,
            ))
            ordem += 1

    await db.commit()
    await db.refresh(mapa)
    return mapa, n_cadernos, n_questoes
```

- [ ] **Step 3: Endpoint em `mapa_router.py`**:

```python
import mapa_service


class CriarMapaReq(BaseModel):
    concurso_id: int
    cargo_nome: str


@router.post("")
async def criar_mapa(
    req: CriarMapaReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cria o Mapa da Aprovação (PRO): itens verticalizados + cadernos automáticos."""
    if not (user.is_admin or await acesso_pro_ativo(db, user.id)):
        raise HTTPException(403, "O Mapa da Aprovação é um recurso PRO")

    concurso = await _concurso_ou_404(db, req.concurso_id)
    ext = (
        await db.execute(
            select(EditalExtracao).where(
                EditalExtracao.concurso_id == concurso.id,
                EditalExtracao.status == "concluido",
            )
        )
    ).scalar_one_or_none()
    if ext is None or not ext.dados:
        raise HTTPException(409, "Edital ainda não extraído")

    cargo = next(
        (c for c in (ext.dados.get("cargos") or []) if c.get("nome") == req.cargo_nome),
        None,
    )
    if cargo is None:
        raise HTTPException(404, "Cargo não encontrado no edital")

    existente = (
        await db.execute(
            select(MapaAprovacao.id).where(
                MapaAprovacao.usuario_uid == user.id,
                MapaAprovacao.concurso_id == concurso.id,
                MapaAprovacao.cargo_nome == req.cargo_nome,
            )
        )
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(409, f"Você já tem um Mapa para este cargo (id {existente})")

    modelo = await get_setting(db, SETTING_MAPA, SETTING_DEFAULTS[SETTING_MAPA])
    mapa, n_cadernos, n_questoes = await mapa_service.montar_mapa(
        db, user.id, concurso, ext, cargo, modelo
    )
    return {
        "id": mapa.id,
        "redirect": f"/q/mapa/{mapa.id}",
        "cadernos_criados": n_cadernos,
        "total_questoes": n_questoes,
    }
```

(No topo de `mapa_service.py` garanta `import asyncio` — já existe da Task 5.)

- [ ] **Step 4: Rodar** `python -m pytest tests/test_mapa_router.py -v` → todos passam; suíte inteira verde (`python -m pytest tests/ -q`)

- [ ] **Step 5: Commit**

```bash
git add backend/mapa_router.py backend/mapa_service.py backend/tests/test_mapa_router.py
git commit -m "feat(mapa): criação do Mapa (PRO) com match de matérias e cadernos automáticos

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: CRUD do Mapa — lista, detalhe, checklist, delete, reextrair

**Files:**
- Modify: `backend/mapa_router.py`
- Test: `backend/tests/test_mapa_router.py` (novo bloco)

**Interfaces:**
- Produces:
  - `GET /api/q/mapas` → `{"mapas": [{id, concurso_id, concurso_nome, orgao_sigla, banca_nome, cargo_nome, data_prova, total_itens, itens_dominados, caderno_ids, criado_em}]}` — `data_prova` (ISO ou null) resolvida por: `dados.concurso.data_prova` → primeiro evento `tipo=prova` com data → `TcConcurso.data_aplicacao` (só a data). Front (Tasks 10-13) consome.
  - `GET /api/q/mapas/{id}` → mapa + `eventos` (da extração) + `verticalizacao` agrupada `[{materia_nome, materia_id, caderno_id, itens: [{id, assunto_texto, status}]}]` + `cargo_dados`.
  - `PATCH /api/q/mapas/{id}/itens/{item_id}` body `{"status": "nao_visto|estudando|dominado"}`.
  - `DELETE /api/q/mapas/{id}` (cadernos permanecem).
  - `POST /api/q/mapas/extracao/{concurso_id}/reextrair` (admin) — zera para pendente, `prompt_versao += 1`, re-enfileira.

- [ ] **Step 1: Testes falhando** (padrões: dono vê, não-dono 404, status inválido 422/400):

```python
async def _criar_mapa_via_api(client, db_session, auth_state, _pro_flag=True):
    c = await seed_concurso(db_session)
    await _seed_banco_questoes(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido", dados=DADOS_OK))
    await db_session.commit()
    auth_state["user"] = make_user("u1")
    r = await client.post("/api/q/mapas",
                          json={"concurso_id": c.id, "cargo_nome": "Engenheiro Civil"})
    return r.json()["id"], c


async def test_listar_meus_mapas(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, c = await _criar_mapa_via_api(client, db_session, auth_state)
    r = await client.get("/api/q/mapas")
    assert r.status_code == 200
    m = r.json()["mapas"][0]
    assert m["id"] == mapa_id
    assert m["data_prova"] == "2026-09-20"
    assert m["total_itens"] == 2
    assert m["caderno_ids"]


async def test_detalhe_verticalizacao(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    r = await client.get(f"/api/q/mapas/{mapa_id}")
    body = r.json()
    assert body["eventos"][0]["tipo"] == "prova"
    v = body["verticalizacao"]
    assert v[0]["materia_nome"] == "Língua Portuguesa"
    assert [i["assunto_texto"] for i in v[0]["itens"]] == ["Crase", "Concordância"]


async def test_detalhe_de_outro_usuario_404(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    auth_state["user"] = make_user("u2")
    r = await client.get(f"/api/q/mapas/{mapa_id}")
    assert r.status_code == 404


async def test_patch_item_status(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    det = (await client.get(f"/api/q/mapas/{mapa_id}")).json()
    item_id = det["verticalizacao"][0]["itens"][0]["id"]
    r = await client.patch(f"/api/q/mapas/{mapa_id}/itens/{item_id}",
                           json={"status": "dominado"})
    assert r.status_code == 200
    r2 = await client.patch(f"/api/q/mapas/{mapa_id}/itens/{item_id}",
                            json={"status": "qualquer"})
    assert r2.status_code in (400, 422)


async def test_delete_mapa_preserva_cadernos(client, db_session, auth_state, _pro, _match_ia):
    mapa_id, _ = await _criar_mapa_via_api(client, db_session, auth_state)
    r = await client.delete(f"/api/q/mapas/{mapa_id}")
    assert r.status_code == 200
    assert (await db_session.execute(select(MapaAprovacao))).scalar_one_or_none() is None
    assert (await db_session.execute(select(CadernoQuestoes))).scalar_one() is not None


async def test_reextrair_admin(client, db_session, auth_state, _sem_fila):
    c = await seed_concurso(db_session)
    db_session.add(EditalExtracao(concurso_id=c.id, status="concluido",
                                  dados=DADOS_OK, prompt_versao=1))
    await db_session.commit()
    auth_state["user"] = make_user("adm", role="admin")
    r = await client.post(f"/api/q/mapas/extracao/{c.id}/reextrair")
    assert r.status_code == 202
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "pendente" and ext.prompt_versao == 2
    assert len(_sem_fila) == 1

    auth_state["user"] = make_user("u1")  # não-admin
    assert (await client.post(f"/api/q/mapas/extracao/{c.id}/reextrair")).status_code == 403
```

- [ ] **Step 2: Implementar em `mapa_router.py`**:

```python
STATUS_ITEM = {"nao_visto", "estudando", "dominado"}


def _data_prova_do_mapa(dados: Optional[dict], concurso: TcConcurso) -> Optional[str]:
    """data_prova ISO: extração > evento tipo=prova > data_aplicacao do concurso."""
    if dados:
        dp = (dados.get("concurso") or {}).get("data_prova")
        if dp:
            return dp
        for ev in dados.get("eventos") or []:
            if ev.get("tipo") == "prova" and ev.get("data_inicio"):
                return ev["data_inicio"]
    if concurso.data_aplicacao:
        return concurso.data_aplicacao.date().isoformat()
    return None


async def _mapa_do_usuario(db: AsyncSession, mapa_id: int, user_uid: str) -> MapaAprovacao:
    mapa = (
        await db.execute(
            select(MapaAprovacao).where(
                MapaAprovacao.id == mapa_id, MapaAprovacao.usuario_uid == user_uid
            )
        )
    ).scalar_one_or_none()
    if mapa is None:
        raise HTTPException(404, "Mapa não encontrado")
    return mapa


@router.get("")
async def listar_mapas(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    mapas = (
        await db.execute(
            select(MapaAprovacao)
            .where(MapaAprovacao.usuario_uid == user.id)
            .order_by(MapaAprovacao.criado_em.desc())
        )
    ).scalars().all()
    out = []
    for m in mapas:
        concurso = (
            await db.execute(select(TcConcurso).where(TcConcurso.id == m.concurso_id))
        ).scalar_one()
        ext = (
            await db.execute(
                select(EditalExtracao).where(EditalExtracao.id == m.extracao_id)
            )
        ).scalar_one_or_none()
        itens = m.itens  # lazy="selectin"
        out.append({
            "id": m.id,
            "concurso_id": m.concurso_id,
            "concurso_nome": concurso.nome_completo,
            "orgao_sigla": concurso.orgao_sigla,
            "banca_nome": concurso.banca_nome,
            "cargo_nome": m.cargo_nome,
            "data_prova": _data_prova_do_mapa(ext.dados if ext else None, concurso),
            "total_itens": len(itens),
            "itens_dominados": sum(1 for i in itens if i.status == "dominado"),
            "caderno_ids": sorted({i.caderno_id for i in itens if i.caderno_id}),
            "criado_em": m.criado_em.isoformat() if m.criado_em else None,
        })
    return {"mapas": out}


@router.get("/{mapa_id}")
async def detalhar_mapa(
    mapa_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    mapa = await _mapa_do_usuario(db, mapa_id, user.id)
    concurso = (
        await db.execute(select(TcConcurso).where(TcConcurso.id == mapa.concurso_id))
    ).scalar_one()
    ext = (
        await db.execute(select(EditalExtracao).where(EditalExtracao.id == mapa.extracao_id))
    ).scalar_one_or_none()

    # Verticalização agrupada por matéria, na ordem dos itens
    grupos: dict[str, dict[str, Any]] = {}
    for i in mapa.itens:
        g = grupos.setdefault(i.materia_nome, {
            "materia_nome": i.materia_nome, "materia_id": i.materia_id,
            "caderno_id": i.caderno_id, "itens": [],
        })
        g["itens"].append({"id": i.id, "assunto_texto": i.assunto_texto, "status": i.status})

    cadernos_ids = sorted({i.caderno_id for i in mapa.itens if i.caderno_id})
    cadernos = []
    if cadernos_ids:
        from models import CadernoQuestoes
        rows = (
            await db.execute(
                select(CadernoQuestoes).where(CadernoQuestoes.id.in_(cadernos_ids))
            )
        ).scalars().all()
        cadernos = [{"id": c.id, "nome": c.nome, "total": c.total} for c in rows]

    return {
        "id": mapa.id,
        "concurso_id": mapa.concurso_id,
        "concurso_nome": concurso.nome_completo,
        "orgao_sigla": concurso.orgao_sigla,
        "banca_nome": concurso.banca_nome,
        "cargo_nome": mapa.cargo_nome,
        "cargo_dados": mapa.cargo_dados,
        "data_prova": _data_prova_do_mapa(ext.dados if ext else None, concurso),
        "eventos": (ext.dados.get("eventos") if ext and ext.dados else []) or [],
        "verticalizacao": list(grupos.values()),
        "cadernos": cadernos,
    }


class ItemPatch(BaseModel):
    status: str


@router.patch("/{mapa_id}/itens/{item_id}")
async def atualizar_item(
    mapa_id: int,
    item_id: int,
    req: ItemPatch,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if req.status not in STATUS_ITEM:
        raise HTTPException(400, f"status deve ser um de {sorted(STATUS_ITEM)}")
    await _mapa_do_usuario(db, mapa_id, user.id)
    item = (
        await db.execute(
            select(MapaItem).where(MapaItem.id == item_id, MapaItem.mapa_id == mapa_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    item.status = req.status
    await db.commit()
    return {"ok": True, "id": item.id, "status": item.status}


@router.delete("/{mapa_id}")
async def excluir_mapa(
    mapa_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove o mapa (cascade nos itens). Cadernos criados são do usuário — ficam."""
    mapa = await _mapa_do_usuario(db, mapa_id, user.id)
    await db.delete(mapa)
    await db.commit()
    return {"ok": True}


@router.post("/extracao/{concurso_id}/reextrair", status_code=status.HTTP_202_ACCEPTED)
async def reextrair_edital(
    concurso_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Força nova extração (edital retificado / prompt novo). Mapas existentes
    mantêm o snapshot em cargo_dados — não são reescritos."""
    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso_id)
        )
    ).scalar_one_or_none()
    if ext is None:
        raise HTTPException(404, "Extração não encontrada")
    ext.status = "pendente"
    ext.erro_msg = None
    ext.prompt_versao = (ext.prompt_versao or 1) + 1
    await db.commit()
    modelo = await get_setting(db, SETTING_MAPA, SETTING_DEFAULTS[SETTING_MAPA])
    await extrair_edital_task.kiq(concurso_id, modelo)
    return {"status": "pendente", "prompt_versao": ext.prompt_versao}
```

⚠️ Ordem das rotas: `GET /extracao/{concurso_id}` e `POST /extracao/{...}/reextrair` devem ser declaradas ANTES de `GET /{mapa_id}` no arquivo — FastAPI casa na ordem; "extracao" não pode ser engolido por `/{mapa_id}` (int converter já protege, mas mantenha o agrupamento claro).

- [ ] **Step 3: Rodar** `python -m pytest tests/test_mapa_router.py -v && python -m pytest tests/ -q` → tudo verde

- [ ] **Step 4: Commit**

```bash
git add backend/mapa_router.py backend/tests/test_mapa_router.py
git commit -m "feat(mapa): lista/detalhe/checklist/delete do Mapa + reextração admin

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Frontend — queryKeys, Sidebar e página `/q/mapa` (lista)

**Files:**
- Modify: `fontend/lib/queryKeys.ts`
- Modify: `fontend/app/components/Sidebar.tsx` (array `NAV_ITEMS`, linhas ~22-45)
- Create: `fontend/app/q/mapa/page.tsx`

**Interfaces:**
- Consumes: `GET /api/q/mapas` (Task 9), `apiUrl` de `fontend/lib/api.ts`, componentes `ds` (`Skeleton`, `Card`, `Icon`).
- Produces: chaves `qk.mapas()`, `qk.mapa(id)`, `qk.mapaExtracao(concursoId)`, `qk.concursosCatalogo(busca, page)`; rota `/q/mapa`; item de menu "Mapa da Aprovação".

- [ ] **Step 1: queryKeys** — adicionar em `fontend/lib/queryKeys.ts` (dentro de `qk`):

```ts
  // Mapa da Aprovação
  mapas: () => ["q", "mapas"] as const,
  mapa: (id: string | number) => ["q", "mapas", String(id)] as const,
  mapaExtracao: (concursoId: string | number) =>
    ["q", "mapas", "extracao", String(concursoId)] as const,
  concursosCatalogo: (busca: string, page: number) =>
    ["q", "concursos", "catalogo", busca, page] as const,
```

- [ ] **Step 2: Sidebar** — em `NAV_ITEMS`, logo acima de `{ href: "/planejamento", ... }`:

```ts
  { href: "/q/mapa", label: "Mapa da Aprovação", icon: "map" },
```

- [ ] **Step 3: Página `/q/mapa`** — `fontend/app/q/mapa/page.tsx`. Siga o padrão de client page com React Query de `fontend/app/q/concursos/page.tsx` (mesmos imports de `apiUrl`, `useQuery`, credentials). Estrutura:

```tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiUrl } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Skeleton } from "@/app/components/ds";

type MapaResumo = {
  id: number;
  concurso_nome: string;
  orgao_sigla: string | null;
  banca_nome: string | null;
  cargo_nome: string;
  data_prova: string | null;
  total_itens: number;
  itens_dominados: number;
  caderno_ids: number[];
  criado_em: string | null;
};

function diasRestantes(dataProva: string | null): number | null {
  if (!dataProva) return null;
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  const prova = new Date(`${dataProva}T00:00:00`);
  return Math.round((prova.getTime() - hoje.getTime()) / 86_400_000);
}

export default function MapaListaPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: qk.mapas(),
    queryFn: async (): Promise<{ mapas: MapaResumo[] }> => {
      const r = await fetch(apiUrl("/api/q/mapas"), { credentials: "include" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
  });

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-fg-strong">🗺️ Mapa da Aprovação</h1>
          <p className="text-sm text-fg-muted">
            Do edital à prova: cargos, matérias, prazos e questões da banca em um só plano.
          </p>
        </div>
        <Link
          href="/q/mapa/novo"
          className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:opacity-90"
        >
          + Criar Mapa
        </Link>
      </header>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-36 rounded-xl" />
          <Skeleton className="h-36 rounded-xl" />
        </div>
      )}
      {isError && (
        <p className="text-sm text-red-400">Não foi possível carregar seus mapas. Recarregue a página.</p>
      )}
      {data && data.mapas.length === 0 && (
        <div className="rounded-xl border border-fg-strong/10 p-10 text-center space-y-3">
          <p className="text-fg-muted">
            Você ainda não tem nenhum Mapa. Escolha um concurso e deixe a IA ler o edital para você.
          </p>
          <Link href="/q/mapa/novo" className="text-primary font-medium">
            Criar meu primeiro Mapa →
          </Link>
        </div>
      )}
      {data && data.mapas.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {data.mapas.map((m) => {
            const dias = diasRestantes(m.data_prova);
            const pct = m.total_itens
              ? Math.round((100 * m.itens_dominados) / m.total_itens)
              : 0;
            return (
              <Link
                key={m.id}
                href={`/q/mapa/${m.id}`}
                className="rounded-xl border border-fg-strong/10 bg-surface p-5 space-y-2 hover:border-primary/50"
              >
                <p className="text-xs text-fg-faint">{m.banca_nome ?? ""}</p>
                <h2 className="font-semibold text-fg-strong leading-snug">{m.concurso_nome}</h2>
                <p className="text-sm text-primary">{m.cargo_nome}</p>
                <div className="flex items-center justify-between text-xs text-fg-muted pt-2">
                  <span>
                    {dias === null ? "Data da prova não informada"
                      : dias >= 0 ? `${dias} dias até a prova` : "Prova realizada"}
                  </span>
                  <span>{pct}% dominado</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

Confira os exports reais de `fontend/app/components/ds/index.ts` (nome do `Skeleton`) e os tokens de cor do tema (`bg-surface`, `text-fg-*`) usados nas páginas vizinhas — espelhe-os.

- [ ] **Step 4: Lint** — `cd fontend && pnpm lint` → 0 erros

- [ ] **Step 5: Commit**

```bash
git add fontend/lib/queryKeys.ts fontend/app/components/Sidebar.tsx fontend/app/q/mapa/page.tsx
git commit -m "feat(mapa): página Meus Mapas + entrada no menu + query keys

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Frontend — wizard `/q/mapa/novo`

**Files:**
- Create: `fontend/app/q/mapa/novo/page.tsx`
- Create: `fontend/app/q/mapa/novo/components/PassoConcurso.tsx`
- Create: `fontend/app/q/mapa/novo/components/PassoExtracao.tsx`
- Create: `fontend/app/q/mapa/novo/components/PassoCargo.tsx`

**Interfaces:**
- Consumes: `GET /api/q/concursos/catalogo` (Task 6), `POST /api/q/mapas/extrair` + `GET /api/q/mapas/extracao/{id}` (Task 7), `POST /api/q/mapas` (Task 8), `BrandLoader`/`Skeleton` de `ds`.
- Produces: fluxo completo de criação; em sucesso `router.push(res.redirect)`.

Comportamento exigido (regras de UI do projeto):

1. **Passo concurso**: busca com debounce 300ms no catálogo (`useQuery(qk.concursosCatalogo(busca, page))`, `placeholderData: keepPreviousData`); cards com nome/banca/ano; `<Skeleton>` na carga — nunca "nenhum resultado" enquanto `isPending`.
2. **Passo extração**: ao selecionar concurso → `useMutation` POST `/extrair`; enquanto status ≠ `concluido` → **`<BrandLoader>`** com texto "studIA está lendo o edital… isso leva um ou dois minutos" (operação lenta = BrandLoader, espaço reservado). Polling: `useQuery(qk.mapaExtracao(concursoId), { refetchInterval: (q) => (q.state.data?.status === "concluido" || q.state.data?.status === "erro" ? false : 4000) })`. Status `erro` → mensagem com `erro_msg` + botão "Tentar de novo" (re-POST `/extrair`).
3. **Passo cargo**: "Li o edital e encontrei N cargos" + cards (nome, vagas, salário, escolaridade, nº de matérias do programa). Seleção → resumo final (matérias + eventos com datas) + botão **"Criar meu Mapa"**.
4. **Criação**: `useMutation` POST `/api/q/mapas`; sucesso → `queryClient.invalidateQueries({ queryKey: qk.mapas() })` + `router.push(redirect)`. **403** → paywall inline: "O Mapa da Aprovação é um recurso PRO" + link para `/assinaturas`. **409** com id existente → link "abrir o Mapa que você já tem".
5. Estado do wizard num único `useState<"concurso" | "extracao" | "cargo">` na page; dados passam por props. Sem `fetch` em `useEffect`.

- [ ] **Step 1: Implementar os 4 arquivos** seguindo o comportamento acima (estrutura de componentes/estilo espelhando `fontend/app/q/concursos/page.tsx` e `ForumPanel.tsx` para o BrandLoader).
- [ ] **Step 2: Lint** — `pnpm lint` → 0 erros
- [ ] **Step 3: Smoke manual** (dev): `./dev.sh up:d` na raiz do checkout principal NÃO se aplica ao worktree — apenas garantir que `pnpm lint` e o build de tipos passam: `cd fontend && pnpm exec tsc --noEmit` (se o projeto tiver `tsc` disponível; senão, lint basta).
- [ ] **Step 4: Commit**

```bash
git add fontend/app/q/mapa/novo/
git commit -m "feat(mapa): wizard de criação (concurso → leitura IA do edital → cargo)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Frontend — página do Mapa `/q/mapa/[id]`

**Files:**
- Create: `fontend/app/q/mapa/[id]/page.tsx`
- Create: `fontend/app/q/mapa/[id]/components/TimelineEventos.tsx`
- Create: `fontend/app/q/mapa/[id]/components/Verticalizacao.tsx`

**Interfaces:**
- Consumes: `GET /api/q/mapas/{id}`, `PATCH /api/q/mapas/{id}/itens/{item_id}`, `DELETE /api/q/mapas/{id}` (Task 9).
- Produces: página com hero (countdown), timeline, verticalização com checklist otimista, cadernos com link para `/q/caderno/{id}` e atalho "Gerar cronograma" → `/q/caderno/{id}/cronograma`.

Comportamento exigido:

1. **Hero**: órgão + cargo + banca; countdown grande "faltam N dias" quando `data_prova` (senão "Data da prova ainda não divulgada"); barra de progresso `% dominado`.
2. **Timeline** (`TimelineEventos`): lista vertical dos `eventos` ordenados por `data_inicio` (nulls no fim), ícone por `tipo` (inscricao=edit_calendar, prova=quiz, resultado=flag, recurso=gavel, outro=event), destaque visual para eventos futuros ≤ 7 dias.
3. **Verticalização** (`Verticalizacao`): accordion por matéria; cada assunto com ciclo de status ao clicar (nao_visto → estudando → dominado → nao_visto) via `useMutation` com **update otimista** (`onMutate` atualiza o cache de `qk.mapa(id)`, `onError` desfaz com o snapshot) — padrão React Query v5.
4. **Cadernos**: cards "🗺️ {matéria} — N questões" linkando `/q/caderno/{id}` + botão "Gerar cronograma" → `/q/caderno/{id}/cronograma`.
5. Excluir mapa: botão discreto com `confirm()` nativo → DELETE → invalidate `qk.mapas()` → `router.push("/q/mapa")`. Texto deixa claro que os cadernos permanecem.
6. Carga: `<Skeleton>` no formato do layout final (hero + 2 colunas).

- [ ] **Step 1: Implementar os 3 arquivos**
- [ ] **Step 2: Lint** — `pnpm lint` → 0 erros
- [ ] **Step 3: Commit**

```bash
git add fontend/app/q/mapa/\[id\]/
git commit -m "feat(mapa): página do Mapa (countdown, timeline do edital, verticalização, cadernos)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 13: Cronograma — pré-preencher data da prova a partir do Mapa

**Files:**
- Modify: `fontend/app/q/caderno/[id]/cronograma/components/ConfigForm.tsx` (linha ~18)
- Modify: `fontend/app/q/caderno/[id]/cronograma/page.tsx` (onde `ConfigForm` é montado)

**Interfaces:**
- Consumes: `GET /api/q/mapas` (`caderno_ids` + `data_prova` por mapa, Task 9); prop existente `initial` do `ConfigForm`.
- Produces: prop nova opcional `sugestaoDataProva?: string | null` no `ConfigForm`.

- [ ] **Step 1: `ConfigForm.tsx`** — assinatura ganha a prop e o estado inicial usa a sugestão apenas quando não há valor salvo:

```tsx
// antes:
const [dataProva, setDataProva] = useState(initial?.data_prova ?? "");
// depois:
const [dataProva, setDataProva] = useState(
  initial?.data_prova ?? sugestaoDataProva ?? ""
);
```

Adicionar abaixo do input de data, quando a sugestão foi usada (`!initial?.data_prova && sugestaoDataProva`), o hint: `<p className="text-xs text-fg-faint">Data preenchida pelo seu Mapa da Aprovação — ajuste se precisar.</p>`

- [ ] **Step 2: `cronograma/page.tsx`** — buscar os mapas e derivar a sugestão para este caderno:

```tsx
const { data: mapasData } = useQuery({
  queryKey: qk.mapas(),
  queryFn: async (): Promise<{ mapas: { caderno_ids: number[]; data_prova: string | null }[] }> => {
    const r = await fetch(apiUrl("/api/q/mapas"), { credentials: "include" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
  staleTime: 60_000,
});
const sugestaoDataProva =
  mapasData?.mapas.find((m) => m.caderno_ids.includes(cadernoId))?.data_prova ?? null;
```

e passar `sugestaoDataProva={sugestaoDataProva}` ao `<ConfigForm>`. Atenção à regra de UI: o form só deve ser renderizado quando a query de mapas resolver (`isPending` → skeleton do form), para a data não "pular" de vazia para preenchida.

- [ ] **Step 3: Lint** — `pnpm lint` → 0 erros
- [ ] **Step 4: Commit**

```bash
git add fontend/app/q/caderno/\[id\]/cronograma/
git commit -m "feat(mapa): cronograma pré-preenche a data da prova a partir do Mapa da Aprovação

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 14: Verificação final

- [ ] **Step 1: Suíte backend completa** — `cd backend && python -m pytest tests/ -v` → 100% verde (incluindo drift).
- [ ] **Step 2: Lint frontend** — `cd fontend && pnpm lint` → limpo.
- [ ] **Step 3: Revisão do diff** — `git log --oneline main..HEAD` e `git diff main --stat`: só arquivos do plano; nenhum resquício de debug.
- [ ] **Step 4: Commit final se houver ajustes** e reportar ao usuário para o fluxo de merge/deploy do CLAUDE.md (merge na `main` a partir do checkout principal → `git push` → `./build.sh` → `git worktree remove`). O deploy roda migrations sozinho (`db_prepare` no startup).

## Notas de execução

- **Fixtures de teste:** os testes acima assumem o contrato de `tests/conftest.py` (`client`, `db_session`, `auth_state`, `make_user`). ANTES da Task 6, leia `backend/tests/conftest.py` e um teste de router existente (`test_cronograma_router.py`) e adapte os nomes/formas EXATOS — o comportamento testado não muda.
- **`from worker import ...` nos testes:** importar `mapa_router` puxa `worker` (NATS). Os testes existentes já importam `main`/routers sem broker rodando (o broker só conecta no startup) — se algum import de `worker` explodir em teste, mova o import de `extrair_edital_task` para dentro das funções que o usam (padrão lazy), mantendo o monkeypatch em `mapa_router.extrair_edital_task` via import module-level; nesse caso monkeypatche `worker.extrair_edital_task`.
- **Preview "X questões em Y matérias":** decisão de design — a contagem aparece no retorno do POST (toast de sucesso no wizard) e na página do Mapa, não antes da criação (evita endpoint extra de pré-contagem).
