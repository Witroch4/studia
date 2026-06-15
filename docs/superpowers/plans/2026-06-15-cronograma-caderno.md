# Cronograma de Estudo por Caderno — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar ao studIA um cronograma de estudo por caderno — uma página viva que cruza um plano dia-a-dia (gerado pela data da prova) com o progresso real do usuário, mais export `.xlsx` no estilo da planilha ALECE.

**Architecture:** Config enxuta + cálculo sob demanda (decisão A do spec). Persiste só a configuração (`cronogramas`), os temas de discursiva gerados por IA (`cronograma_discursivas`) e os resultados de simulado (`cronograma_simulados`). Metas diárias, saldo, KPIs e revisão espaçada são **funções puras** em `cronograma_core.py`, alimentadas pela config + tabela `Resolucao`. Endpoints em `cronograma_router.py` (prefixo `/api/q`), export em `cronograma_xlsx.py`. Frontend em `/q/caderno/[id]/cronograma`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Postgres; pytest + pytest-asyncio + aiosqlite (testes); openpyxl (export); google-genai via `gemini_service.py` (IA); Next.js 16 App Router + React 19 + Tailwind (frontend).

**Spec:** `docs/superpowers/specs/2026-06-15-cronograma-caderno-design.md`

---

## File Structure

**Backend (criar):**
- `backend/cronograma_core.py` — lógica pura: geração do plano, distribuição de carga, fases, KPIs/saldo, revisão espaçada, agenda de discursivas e simulados. **Sem dependência de DB nem FastAPI.**
- `backend/cronograma_router.py` — endpoints `/api/q/cadernos/{id}/cronograma*` (schemas Pydantic + CRUD + PATCH + export).
- `backend/cronograma_xlsx.py` — monta o workbook openpyxl a partir do plano calculado.
- `backend/tests/test_cronograma_core.py` — testes unitários das funções puras.
- `backend/tests/test_cronograma_router.py` — testes de integração dos endpoints.
- `backend/tests/test_cronograma_xlsx.py` — teste do export.
- `backend/alembic/versions/<rev>_cronograma.py` — migration das 3 tabelas.

**Backend (modificar):**
- `backend/models.py` — adicionar `Cronograma`, `CronogramaDiscursiva`, `CronogramaSimulado`.
- `backend/gemini_service.py` — adicionar `gerar_temas_discursivas(...)`.
- `backend/main.py:193` — `include_router(cronograma_router)` após o `q_router`.
- `backend/requirements.txt` — adicionar `openpyxl`.

**Frontend (criar):**
- `fontend/app/q/caderno/[id]/cronograma/page.tsx` — página (criação + dashboard).
- `fontend/app/q/caderno/[id]/cronograma/api.ts` — chamadas tipadas via `apiFetch`.
- `fontend/app/q/caderno/[id]/cronograma/components/` — `KpiStrip.tsx`, `TimelineTable.tsx`, `RevisarHoje.tsx`, `DiscursivasList.tsx`, `SimuladosList.tsx`, `ConfigForm.tsx`.
- `fontend/app/planejamento/page.tsx` — lista de cadernos com cronograma (substitui o link `/em-breve?f=Planejamento`).

**Frontend (modificar):**
- `fontend/app/q/caderno/[id]/page.tsx` — botão "Cronograma" no header do player.
- `fontend/app/Sidebar.tsx:33` — apontar "Planejamento" para `/planejamento`.

---

## Convenções de teste (lidas do código existente)

- Rodar testes: a partir de `backend/`, `python -m pytest tests/<arquivo> -v`. O fixture de DB usa Postgres de teste (`TEST_DATABASE_URL`, default `postgresql+asyncpg://postgres:postgres@postgres:5432/studia_test`). Rodar dentro do container backend dev (`./dev.sh shell backend`) garante o Postgres acessível.
- Testes puros (`test_cronograma_core.py`) **não** usam DB — rodam em qualquer lugar.
- Padrão de teste de endpoint: usar os fixtures `client`, `db_session`, `auth_state`, `USER_A`, `USER_B` de `tests/conftest.py`. `auth_state["user"]` default = admin; reatribuir para isolar usuários.
- Há um teste de drift (`tests/test_alembic_no_drift.py`): a migration tem que casar com os models, senão ele quebra.

---

## Task 1: Dependência openpyxl + esqueleto do core com teste de distribuição

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/cronograma_core.py`
- Test: `backend/tests/test_cronograma_core.py`

- [ ] **Step 1: Adicionar dependência**

Em `backend/requirements.txt`, na seção `# witdev-tec-master` (após `markdownify>=0.13.0`), adicionar:

```
# cronograma de estudo: export .xlsx
openpyxl>=3.1.0
```

Instalar no ambiente/container: `pip install "openpyxl>=3.1.0"`.

- [ ] **Step 2: Escrever o teste de distribuição de carga (falhando)**

Criar `backend/tests/test_cronograma_core.py`:

```python
from datetime import date

from cronograma_core import distribuir_carga


def test_distribuir_carga_exata_soma_total():
    # 100 questões em 7 dias úteis → soma exatamente 100, diferença máx. 1 entre dias
    cargas = distribuir_carga(total=100, n_dias=7)
    assert sum(cargas) == 100
    assert len(cargas) == 7
    assert max(cargas) - min(cargas) <= 1
    # os primeiros dias recebem o resto (100 = 14*7 + 2 → dois dias com 15)
    assert cargas == [15, 15, 14, 14, 14, 14, 14]


def test_distribuir_carga_divisivel():
    assert distribuir_carga(total=80, n_dias=8) == [10] * 8


def test_distribuir_carga_um_dia():
    assert distribuir_carga(total=42, n_dias=1) == [42]
```

- [ ] **Step 3: Rodar o teste e ver falhar**

Run: `python -m pytest tests/test_cronograma_core.py -v`
Expected: FAIL — `ImportError: cannot import name 'distribuir_carga'`.

- [ ] **Step 4: Implementar `distribuir_carga`**

Criar `backend/cronograma_core.py`:

```python
"""Lógica pura do cronograma de estudo por caderno.

Sem dependência de DB nem FastAPI — tudo recebe dados primitivos e devolve
estruturas simples, para ser testável isoladamente. As datas de "hoje" são
sempre injetadas como parâmetro (nunca `date.today()` aqui dentro).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil


def distribuir_carga(total: int, n_dias: int) -> list[int]:
    """Distribui `total` questões em `n_dias` dias úteis, o mais uniforme possível.

    Soma sempre == total. Os primeiros `total % n_dias` dias recebem +1.
    """
    if n_dias <= 0:
        raise ValueError("n_dias deve ser > 0")
    base, resto = divmod(total, n_dias)
    return [base + 1 if i < resto else base for i in range(n_dias)]
```

- [ ] **Step 5: Rodar o teste e ver passar**

Run: `python -m pytest tests/test_cronograma_core.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/cronograma_core.py backend/tests/test_cronograma_core.py
git commit -m "feat(cronograma): distribuir_carga + dep openpyxl"
```

---

## Task 2: Geração do plano dia-a-dia (fases, folgas, buffer, meta acumulada)

**Files:**
- Modify: `backend/cronograma_core.py`
- Test: `backend/tests/test_cronograma_core.py`

- [ ] **Step 1: Escrever os testes (falhando)**

Adicionar a `backend/tests/test_cronograma_core.py`:

```python
from cronograma_core import gerar_plano, DiaPlano


def test_gerar_plano_estrutura_basica():
    # Seg 2026-06-01 → prova Dom 2026-06-28, domingo de folga, buffer 7 dias.
    dias = gerar_plano(
        data_inicio=date(2026, 6, 1),
        data_prova=date(2026, 6, 28),
        total=120,
        dias_folga=[6],          # domingo (Monday=0 .. Sunday=6)
        buffer_dias=7,
    )
    # cobre todo o intervalo inclusive a prova
    assert dias[0].data == date(2026, 6, 1)
    assert dias[-1].data == date(2026, 6, 28)
    assert dias[-1].fase == "prova"
    # domingos são folga, carga 0
    domingos = [d for d in dias if d.data.weekday() == 6 and d.fase != "prova"]
    assert all(d.questoes_novas == 0 and d.fase == "folga" for d in domingos)
    # soma das questões novas == total
    assert sum(d.questoes_novas for d in dias) == 120
    # meta_acumulada é monotônica e fecha no total
    metas = [d.meta_acumulada for d in dias]
    assert metas == sorted(metas)
    assert metas[-1] == 120


def test_gerar_plano_buffer_sem_questoes_novas():
    dias = gerar_plano(
        data_inicio=date(2026, 6, 1),
        data_prova=date(2026, 6, 28),
        total=120,
        dias_folga=[6],
        buffer_dias=7,
    )
    # fim da 1a volta = prova - 7 dias = 2026-06-21; depois disso, fase buffer, 0 novas
    buffer = [d for d in dias if d.data > date(2026, 6, 21) and d.fase != "prova"]
    assert buffer, "deve haver dias de buffer"
    assert all(d.questoes_novas == 0 and d.fase == "buffer" for d in buffer)


def test_gerar_plano_sem_dias_uteis_levanta():
    import pytest
    with pytest.raises(ValueError):
        gerar_plano(
            data_inicio=date(2026, 6, 1),
            data_prova=date(2026, 6, 3),
            total=120,
            dias_folga=[0, 1, 2, 3, 4, 5, 6],  # tudo folga
            buffer_dias=0,
        )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_core.py -k gerar_plano -v`
Expected: FAIL — `cannot import name 'gerar_plano'`.

- [ ] **Step 3: Implementar `gerar_plano` + `DiaPlano`**

Adicionar a `backend/cronograma_core.py`:

```python
@dataclass
class DiaPlano:
    data: date
    weekday: int
    fase: str            # "1volta" | "folga" | "buffer" | "prova"
    questoes_novas: int
    meta_acumulada: int


def _enumerar_datas(inicio: date, fim: date) -> list[date]:
    n = (fim - inicio).days
    return [inicio + timedelta(days=i) for i in range(n + 1)]


def gerar_plano(
    data_inicio: date,
    data_prova: date,
    total: int,
    dias_folga: list[int],
    buffer_dias: int,
) -> list[DiaPlano]:
    """Plano dia-a-dia entre data_inicio e data_prova (inclusive).

    - Dias cujo weekday ∈ dias_folga → fase "folga", 0 questões.
    - 1ª volta = dias úteis entre data_inicio e (data_prova - buffer_dias).
      As `total` questões são distribuídas uniformemente entre eles.
    - Buffer = dias entre fim da 1ª volta e a prova → fase "buffer", 0 novas.
    - Último dia (data_prova) → fase "prova".
    """
    if data_prova <= data_inicio:
        raise ValueError("data_prova deve ser depois de data_inicio")
    folga = set(dias_folga)
    fim_1volta = data_prova - timedelta(days=buffer_dias)
    datas = _enumerar_datas(data_inicio, data_prova)

    uteis_1volta = [
        d for d in datas
        if d < data_prova and d <= fim_1volta and d.weekday() not in folga
    ]
    if not uteis_1volta:
        raise ValueError("sem dias úteis na 1ª volta — ajuste folgas/buffer/datas")

    cargas = distribuir_carga(total, len(uteis_1volta))
    carga_por_data = dict(zip(uteis_1volta, cargas))

    plano: list[DiaPlano] = []
    acumulado = 0
    for d in datas:
        if d == data_prova:
            fase, novas = "prova", 0
        elif d.weekday() in folga:
            fase, novas = "folga", 0
        elif d <= fim_1volta:
            novas = carga_por_data.get(d, 0)
            fase = "1volta"
        else:
            fase, novas = "buffer", 0
        acumulado += novas
        plano.append(DiaPlano(d, d.weekday(), fase, novas, acumulado))
    return plano
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_cronograma_core.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/cronograma_core.py backend/tests/test_cronograma_core.py
git commit -m "feat(cronograma): gerar_plano (fases, folgas, buffer, meta acumulada)"
```

---

## Task 3: KPIs/saldo + revisão espaçada (funções puras)

**Files:**
- Modify: `backend/cronograma_core.py`
- Test: `backend/tests/test_cronograma_core.py`

- [ ] **Step 1: Escrever os testes (falhando)**

Adicionar a `backend/tests/test_cronograma_core.py`:

```python
from cronograma_core import calcular_kpis, derivar_revisoes, PainelKPIs, ItemRevisao


def _plano_simples():
    return gerar_plano(date(2026, 6, 1), date(2026, 6, 28), 120, [6], 7)


def test_calcular_kpis_saldo_adiantado():
    plano = _plano_simples()
    # Em 2026-06-03 a meta acumulada é a soma das cargas até lá; resolvidas=60 (adiantado)
    kpis = calcular_kpis(plano, total=120, resolvidas=60, acertos=45, hoje=date(2026, 6, 3))
    assert isinstance(kpis, PainelKPIs)
    assert kpis.total == 120
    assert kpis.resolvidas == 60
    assert kpis.erros == 15
    assert kpis.restantes == 60
    assert kpis.pct_conclusao == 0.5
    assert round(kpis.pct_acerto, 2) == 0.75
    assert kpis.saldo == kpis.resolvidas - kpis.meta_hoje
    assert kpis.dias_uteis_restantes > 0
    assert kpis.questoes_dia_necessarias >= 1


def test_calcular_kpis_zero_resolvidas():
    plano = _plano_simples()
    kpis = calcular_kpis(plano, total=120, resolvidas=0, acertos=0, hoje=date(2026, 6, 1))
    assert kpis.pct_conclusao == 0.0
    assert kpis.pct_acerto == 0.0
    assert kpis.restantes == 120


def test_derivar_revisoes_d1_d7_vencidas():
    hoje = date(2026, 6, 10)
    # questão 1 errada em 06-09 → D+1 vence 06-10 (hoje): aparece
    # questão 2 errada em 06-03 → D+7 vence 06-10 (hoje): aparece
    # questão 3 errada em 06-02 mas reacertada em 06-05 → não aparece
    resolucoes = [
        (1, False, date(2026, 6, 9)),
        (2, False, date(2026, 6, 3)),
        (3, False, date(2026, 6, 2)),
        (3, True, date(2026, 6, 5)),
    ]
    itens = derivar_revisoes(resolucoes, hoje=hoje)
    qids = {i.questao_id for i in itens}
    assert qids == {1, 2}
    assert all(isinstance(i, ItemRevisao) for i in itens)
    assert all(i.revisar_em <= hoje for i in itens)


def test_derivar_revisoes_ignora_questao_so_acertada():
    itens = derivar_revisoes([(9, True, date(2026, 6, 1))], hoje=date(2026, 6, 30))
    assert itens == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_core.py -k "kpis or revisoes" -v`
Expected: FAIL — nomes não importáveis.

- [ ] **Step 3: Implementar KPIs + revisões**

Adicionar a `backend/cronograma_core.py`:

```python
@dataclass
class PainelKPIs:
    total: int
    resolvidas: int
    acertos: int
    erros: int
    pct_conclusao: float
    pct_acerto: float
    restantes: int
    dias_uteis_restantes: int
    questoes_dia_necessarias: int
    meta_hoje: int
    saldo: int


def calcular_kpis(
    plano: list[DiaPlano],
    total: int,
    resolvidas: int,
    acertos: int,
    hoje: date,
) -> PainelKPIs:
    """KPIs do painel. `resolvidas`/`acertos` são contagens DISTINCT de questões."""
    meta_hoje = 0
    for d in plano:
        if d.data <= hoje:
            meta_hoje = d.meta_acumulada
        else:
            break
    restantes = max(total - resolvidas, 0)
    dias_uteis_restantes = sum(
        1 for d in plano if d.data >= hoje and d.questoes_novas > 0
    )
    if dias_uteis_restantes > 0:
        necessarias = ceil(restantes / dias_uteis_restantes)
    else:
        necessarias = restantes
    return PainelKPIs(
        total=total,
        resolvidas=resolvidas,
        acertos=acertos,
        erros=max(resolvidas - acertos, 0),
        pct_conclusao=(resolvidas / total) if total else 0.0,
        pct_acerto=(acertos / resolvidas) if resolvidas else 0.0,
        restantes=restantes,
        dias_uteis_restantes=dias_uteis_restantes,
        questoes_dia_necessarias=necessarias,
        meta_hoje=meta_hoje,
        saldo=resolvidas - meta_hoje,
    )


@dataclass
class ItemRevisao:
    questao_id: int
    errou_em: date
    revisar_em: date
    intervalo: str          # "D+1" | "D+7" | "D+21"


_INTERVALOS = [(1, "D+1"), (7, "D+7"), (21, "D+21")]


def derivar_revisoes(
    resolucoes: list[tuple[int, bool, date]],
    hoje: date,
) -> list[ItemRevisao]:
    """Revisões vencidas (<= hoje) das questões erradas e ainda não reacertadas.

    `resolucoes`: (questao_id, acertou, data). Para cada questão pega o último
    erro; se houver acerto posterior, a questão está "resolvida" e é ignorada.
    Cada erro pendente gera os marcos D+1/D+7/D+21 que já venceram.
    """
    ult_erro: dict[int, date] = {}
    ult_acerto: dict[int, date] = {}
    for qid, acertou, dt in resolucoes:
        alvo = ult_acerto if acertou else ult_erro
        if qid not in alvo or dt > alvo[qid]:
            alvo[qid] = dt

    itens: list[ItemRevisao] = []
    for qid, errou_em in ult_erro.items():
        if qid in ult_acerto and ult_acerto[qid] > errou_em:
            continue  # reacertada depois do erro
        for delta, label in _INTERVALOS:
            revisar_em = errou_em + timedelta(days=delta)
            if revisar_em <= hoje:
                itens.append(ItemRevisao(qid, errou_em, revisar_em, label))
    itens.sort(key=lambda i: (i.revisar_em, i.questao_id))
    return itens
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_cronograma_core.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/cronograma_core.py backend/tests/test_cronograma_core.py
git commit -m "feat(cronograma): KPIs/saldo + revisão espaçada (puro)"
```

---

## Task 4: Agenda de discursivas e simulados (funções puras)

**Files:**
- Modify: `backend/cronograma_core.py`
- Test: `backend/tests/test_cronograma_core.py`

- [ ] **Step 1: Escrever os testes (falhando)**

Adicionar a `backend/tests/test_cronograma_core.py`:

```python
from cronograma_core import agendar_discursivas, gerar_simulados


def test_agendar_discursivas_tercas_e_quintas():
    temas = [f"tema {i}" for i in range(6)]
    agenda = agendar_discursivas(
        temas, data_inicio=date(2026, 6, 1), fim_1volta=date(2026, 6, 28), por_semana=2
    )
    assert len(agenda) == 6
    # terça=1, quinta=3
    assert all(d.weekday() in (1, 3) for d, _ in agenda)
    # ordem dos temas preservada e datas crescentes
    assert [t for _, t in agenda] == temas
    assert [d for d, _ in agenda] == sorted(d for d, _ in agenda)


def test_agendar_discursivas_sem_temas():
    assert agendar_discursivas([], date(2026, 6, 1), date(2026, 6, 28), 2) == []


def test_gerar_simulados_marcos():
    sims = gerar_simulados(
        data_inicio=date(2026, 5, 25), data_prova=date(2026, 8, 16), buffer_dias=21
    )
    assert len(sims) >= 2
    # todos dentro do intervalo e ordenados
    datas = [s["data"] for s in sims]
    assert datas == sorted(datas)
    assert datas[0] >= date(2026, 5, 25)
    assert datas[-1] <= date(2026, 8, 16)
    # pelo menos um "completo" na reta final (dentro do buffer)
    assert any(s["tipo"].startswith("Simulado completo") for s in sims)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_core.py -k "discursivas or simulados" -v`
Expected: FAIL.

- [ ] **Step 3: Implementar agenda**

Adicionar a `backend/cronograma_core.py`:

```python
def _proximos_dias_semana(inicio: date, fim: date, weekdays: list[int]) -> list[date]:
    alvo = set(weekdays)
    return [d for d in _enumerar_datas(inicio, fim) if d.weekday() in alvo]


def agendar_discursivas(
    temas: list[str],
    data_inicio: date,
    fim_1volta: date,
    por_semana: int,
) -> list[tuple[date, str]]:
    """Distribui os temas em terças/quintas (ou só terça se por_semana==1)."""
    if not temas:
        return []
    weekdays = [1, 3] if por_semana >= 2 else [1]
    slots = _proximos_dias_semana(data_inicio, fim_1volta, weekdays)
    return [(slots[i], tema) for i, tema in enumerate(temas) if i < len(slots)]


def gerar_simulados(
    data_inicio: date, data_prova: date, buffer_dias: int
) -> list[dict]:
    """Marcos de simulado: diagnóstico, parciais a cada ~14 dias, 2 completos na reta final."""
    fim_1volta = data_prova - timedelta(days=buffer_dias)
    sims: list[dict] = []

    diag = data_inicio + timedelta(days=20)
    if diag < fim_1volta:
        sims.append({"data": diag, "tipo": "Simulado diagnóstico",
                     "objetivas_planejadas": 35, "meta_objetiva": 50,
                     "discursiva_planejada": 1})
    cursor = diag + timedelta(days=14)
    while cursor < fim_1volta:
        sims.append({"data": cursor, "tipo": "Simulado parcial",
                     "objetivas_planejadas": 70, "meta_objetiva": 95,
                     "discursiva_planejada": 1})
        cursor += timedelta(days=14)
    # dois completos no buffer
    for offset, label in ((7, "Simulado completo"), (-7, "Simulado completo final")):
        d = (fim_1volta + timedelta(days=7)) if offset == 7 else (data_prova - timedelta(days=7))
        if data_inicio <= d <= data_prova:
            sims.append({"data": d, "tipo": label,
                         "objetivas_planejadas": 70, "meta_objetiva": 100,
                         "discursiva_planejada": 2})
    sims.sort(key=lambda s: s["data"])
    return sims
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_cronograma_core.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/cronograma_core.py backend/tests/test_cronograma_core.py
git commit -m "feat(cronograma): agenda de discursivas + marcos de simulado (puro)"
```

---

## Task 5: Models + migration Alembic

**Files:**
- Modify: `backend/models.py` (após a classe `QuestaoComentario`, no fim do arquivo)
- Create: `backend/alembic/versions/<rev>_cronograma.py`
- Test: `backend/tests/test_cronograma_models.py`

- [ ] **Step 1: Escrever o teste de models (falhando)**

Criar `backend/tests/test_cronograma_models.py`:

```python
from datetime import date

import pytest
from sqlalchemy import select

from models import Cronograma, CronogramaDiscursiva, CronogramaSimulado


@pytest.mark.asyncio
async def test_cria_cronograma_com_filhos(db_session):
    cron = Cronograma(
        usuario_uid="user-A", caderno_id=1,
        data_inicio=date(2026, 6, 1), data_prova=date(2026, 8, 16),
        dias_folga=[6], buffer_dias=21,
        incluir_revisao=True, incluir_discursivas=True, incluir_simulados=True,
        discursivas_por_semana=2,
    )
    db_session.add(cron)
    await db_session.flush()
    assert cron.id is not None

    db_session.add(CronogramaDiscursiva(
        cronograma_id=cron.id, data=date(2026, 6, 2), tema="Tema X",
        tipo="Treino 20 linhas", qtd=1, status="Pendente", reescrita=False,
    ))
    db_session.add(CronogramaSimulado(
        cronograma_id=cron.id, data=date(2026, 6, 28), tipo="Simulado parcial",
        objetivas_planejadas=70, meta_objetiva=95, discursiva_planejada=1,
    ))
    await db_session.flush()

    discs = (await db_session.execute(
        select(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == cron.id)
    )).scalars().all()
    assert len(discs) == 1
    assert discs[0].status == "Pendente"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_models.py -v`
Expected: FAIL — `cannot import name 'Cronograma'`.

- [ ] **Step 3: Adicionar os models**

No fim de `backend/models.py` (depois de `QuestaoComentario`):

```python
class Cronograma(Base):
    """Configuração de um cronograma de estudo para um caderno (1 por usuário/caderno).

    O plano dia-a-dia, KPIs e revisões NÃO são persistidos — são calculados sob
    demanda (cronograma_core) a partir desta config + da tabela `resolucoes`.
    """
    __tablename__ = "cronogramas"
    __table_args__ = (
        UniqueConstraint("usuario_uid", "caderno_id", name="uq_cronograma_user_caderno"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_uid: Mapped[str] = mapped_column(String(64), index=True)
    caderno_id: Mapped[int] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="CASCADE"), index=True
    )
    data_inicio: Mapped[date] = mapped_column(Date)
    data_prova: Mapped[date] = mapped_column(Date)
    rebaseline_em: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    dias_folga: Mapped[list] = mapped_column(JSON, default=list)
    buffer_dias: Mapped[int] = mapped_column(Integer, default=21)
    incluir_revisao: Mapped[bool] = mapped_column(Boolean, default=True)
    incluir_discursivas: Mapped[bool] = mapped_column(Boolean, default=False)
    incluir_simulados: Mapped[bool] = mapped_column(Boolean, default=True)
    discursivas_por_semana: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CronogramaDiscursiva(Base):
    __tablename__ = "cronograma_discursivas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cronograma_id: Mapped[int] = mapped_column(
        ForeignKey("cronogramas.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[date] = mapped_column(Date)
    tema: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(64), default="Treino 20 linhas")
    qtd: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="Pendente")
    nota: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reescrita: Mapped[bool] = mapped_column(Boolean, default=False)
    observacoes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CronogramaSimulado(Base):
    __tablename__ = "cronograma_simulados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cronograma_id: Mapped[int] = mapped_column(
        ForeignKey("cronogramas.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(64))
    objetivas_planejadas: Mapped[int] = mapped_column(Integer, default=0)
    meta_objetiva: Mapped[int] = mapped_column(Integer, default=0)
    resultado_objetiva: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    discursiva_planejada: Mapped[int] = mapped_column(Integer, default=0)
    resultado_discursiva: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    observacoes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

Nota: `date` e `Date` já estão importados no topo de `models.py`; `Float`, `Text`, `JSON`, `UniqueConstraint`, `Boolean`, `ForeignKey` também.

- [ ] **Step 4: Rodar o teste de models e ver passar**

Run: `python -m pytest tests/test_cronograma_models.py -v`
Expected: PASS (o fixture cria as tabelas a partir do metadata? Se o conftest **não** cria tabelas, ver Step 5 — a migration é quem cria; rode os testes de model depois de aplicar a migration no banco de teste, ou marque que dependem da migration). Se PASS, seguir.

- [ ] **Step 5: Gerar a migration por autogenerate**

Run (de `backend/`, com Postgres dev no schema atual):
```bash
alembic revision --autogenerate -m "cronograma"
```
Conferir que o arquivo gerado em `alembic/versions/` cria as 3 tabelas (`cronogramas`, `cronograma_discursivas`, `cronograma_simulados`), os índices (`ix_cronogramas_usuario_uid`, `ix_cronogramas_caderno_id`, `ix_cronograma_discursivas_cronograma_id`, `ix_cronograma_simulados_cronograma_id`) e a unique `uq_cronograma_user_caderno`, com `down_revision` apontando para a revisão mais recente (`a1b2c3d4e5f6`). Ajustar manualmente se o autogenerate trouxer ruído (seguindo o estilo de `a1b2c3d4e5f6_vouchers.py`).

- [ ] **Step 6: Aplicar e checar drift**

Run:
```bash
alembic upgrade head
python -m pytest tests/test_alembic_no_drift.py -v
```
Expected: PASS — sem drift entre models e migration.

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/alembic/versions/*cronograma*.py backend/tests/test_cronograma_models.py
git commit -m "feat(cronograma): models + migration (cronogramas/discursivas/simulados)"
```

---

## Task 6: Endpoints de config — POST/GET/PUT/DELETE

**Files:**
- Create: `backend/cronograma_router.py`
- Modify: `backend/main.py:193` (registrar router)
- Test: `backend/tests/test_cronograma_router.py`

- [ ] **Step 1: Escrever os testes de integração (falhando)**

Criar `backend/tests/test_cronograma_router.py`:

```python
import pytest
from datetime import date

from conftest import USER_A, USER_B
from models import CadernoQuestoes


async def _caderno(db, owner="user-A", total=120):
    cad = CadernoQuestoes(owner_uid=owner, nome="Caderno Teste", total=total,
                          question_ids=list(range(1, total + 1)))
    db.add(cad)
    await db.flush()
    return cad


@pytest.mark.asyncio
async def test_post_e_get_cronograma(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-06-01",
        "dias_folga": [6], "buffer_dias": 21,
        "incluir_discursivas": False, "incluir_simulados": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["config"]["caderno_id"] == cad.id
    assert len(body["plano"]) >= 1
    assert body["plano"][-1]["fase"] == "prova"
    assert body["kpis"]["total"] == 120

    r2 = await client.get(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r2.status_code == 200
    assert r2.json()["config"]["data_prova"] == "2026-08-16"


@pytest.mark.asyncio
async def test_get_sem_cronograma_404(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    r = await client.get(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_data_prova_invalida_422(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-05-01", "data_inicio": "2026-06-01",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_outro_usuario_nao_acessa(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session, owner="user-A")
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-06-01"})
    auth_state["user"] = USER_B
    r = await client.get(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_cronograma(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-06-01"})
    r = await client.delete(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r.status_code == 200
    assert (await client.get(f"/api/q/cadernos/{cad.id}/cronograma")).status_code == 404
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_router.py -v`
Expected: FAIL — 404/route inexistente (router não registrado).

- [ ] **Step 3: Implementar o router (config CRUD)**

Criar `backend/cronograma_router.py`:

```python
"""Endpoints do cronograma de estudo por caderno (`/api/q/cadernos/{id}/cronograma`)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_user
from database import get_db
from models import (
    CadernoQuestoes, GuiaCaderno, Resolucao,
    Cronograma, CronogramaDiscursiva, CronogramaSimulado,
)
import cronograma_core as core

router = APIRouter(prefix="/api/q", tags=["cronograma"])


class CronogramaIn(BaseModel):
    data_prova: date
    data_inicio: date = Field(default_factory=date.today)
    dias_folga: list[int] = Field(default_factory=lambda: [6])
    buffer_dias: int = Field(default=21, ge=0, le=120)
    incluir_revisao: bool = True
    incluir_discursivas: bool = False
    incluir_simulados: bool = True
    discursivas_por_semana: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def _valida_datas(self):
        if self.data_prova <= self.data_inicio:
            raise ValueError("data_prova deve ser depois de data_inicio")
        return self


async def _caderno_do_usuario(db: AsyncSession, caderno_id: int, user: CurrentUser) -> CadernoQuestoes:
    """Mesma regra de acesso de q_router._caderno_acessivel (dono ou catálogo)."""
    cad = (await db.execute(
        select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id)
    )).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    if cad.owner_uid == user.id:
        return cad
    eh_catalogo = (await db.execute(
        select(GuiaCaderno.id).where(GuiaCaderno.caderno_id == caderno_id).limit(1)
    )).first()
    if eh_catalogo:
        return cad
    raise HTTPException(404, "caderno não encontrado")


async def _get_cron(db: AsyncSession, caderno_id: int, uid: str) -> Optional[Cronograma]:
    return (await db.execute(
        select(Cronograma).where(
            Cronograma.caderno_id == caderno_id, Cronograma.usuario_uid == uid
        )
    )).scalar_one_or_none()


async def _resolucoes_distinct(db: AsyncSession, caderno_id: int, uid: str):
    """(resolvidas_distinct, acertos_distinct, lista (qid, acertou, data) p/ revisões)."""
    rows = (await db.execute(
        select(Resolucao.questao_id, Resolucao.acertou, Resolucao.created_at)
        .where(Resolucao.caderno_id == caderno_id, Resolucao.usuario_uid == uid)
    )).all()
    resolucoes = []
    distintas: set[int] = set()
    acertadas: set[int] = set()
    for qid, acertou, criado in rows:
        d = criado.date() if isinstance(criado, datetime) else criado
        resolucoes.append((qid, bool(acertou), d))
        distintas.add(qid)
        if acertou:
            acertadas.add(qid)
    return len(distintas), len(acertadas), resolucoes


def _cron_config_dict(c: Cronograma) -> dict[str, Any]:
    return {
        "caderno_id": c.caderno_id, "data_inicio": c.data_inicio.isoformat(),
        "data_prova": c.data_prova.isoformat(),
        "rebaseline_em": c.rebaseline_em.isoformat() if c.rebaseline_em else None,
        "dias_folga": c.dias_folga or [], "buffer_dias": c.buffer_dias,
        "incluir_revisao": c.incluir_revisao, "incluir_discursivas": c.incluir_discursivas,
        "incluir_simulados": c.incluir_simulados,
        "discursivas_por_semana": c.discursivas_por_semana,
    }


async def _montar_resposta(db: AsyncSession, cad: CadernoQuestoes, c: Cronograma) -> dict[str, Any]:
    hoje = date.today()
    inicio_efetivo = c.rebaseline_em or c.data_inicio
    plano = core.gerar_plano(inicio_efetivo, c.data_prova, cad.total or 0,
                             c.dias_folga or [], c.buffer_dias)
    resolvidas, acertos, resolucoes = await _resolucoes_distinct(db, cad.id, c.usuario_uid)
    kpis = core.calcular_kpis(plano, cad.total or 0, resolvidas, acertos, hoje)
    revisoes = core.derivar_revisoes(resolucoes, hoje) if c.incluir_revisao else []
    discs = (await db.execute(
        select(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == c.id)
        .order_by(CronogramaDiscursiva.data)
    )).scalars().all()
    sims = (await db.execute(
        select(CronogramaSimulado).where(CronogramaSimulado.cronograma_id == c.id)
        .order_by(CronogramaSimulado.data)
    )).scalars().all()
    return {
        "config": _cron_config_dict(c),
        "plano": [
            {"data": d.data.isoformat(), "weekday": d.weekday, "fase": d.fase,
             "questoes_novas": d.questoes_novas, "meta_acumulada": d.meta_acumulada,
             "hoje": d.data == hoje}
            for d in plano
        ],
        "kpis": kpis.__dict__,
        "revisar_hoje": [
            {"questao_id": i.questao_id, "revisar_em": i.revisar_em.isoformat(),
             "intervalo": i.intervalo} for i in revisoes
        ],
        "discursivas": [
            {"id": x.id, "data": x.data.isoformat(), "tema": x.tema, "tipo": x.tipo,
             "qtd": x.qtd, "status": x.status, "nota": x.nota,
             "reescrita": x.reescrita, "observacoes": x.observacoes} for x in discs
        ],
        "simulados": [
            {"id": s.id, "data": s.data.isoformat(), "tipo": s.tipo,
             "objetivas_planejadas": s.objetivas_planejadas, "meta_objetiva": s.meta_objetiva,
             "resultado_objetiva": s.resultado_objetiva,
             "discursiva_planejada": s.discursiva_planejada,
             "resultado_discursiva": s.resultado_discursiva,
             "observacoes": s.observacoes} for s in sims
        ],
    }


@router.post("/cadernos/{caderno_id}/cronograma")
async def criar_cronograma(
    caderno_id: int, payload: CronogramaIn,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    if await _get_cron(db, caderno_id, user.id):
        raise HTTPException(409, "cronograma já existe para este caderno")
    # valida que o plano é gerável (ex.: tem dias úteis)
    try:
        core.gerar_plano(payload.data_inicio, payload.data_prova, cad.total or 0,
                         payload.dias_folga, payload.buffer_dias)
    except ValueError as e:
        raise HTTPException(422, str(e))
    c = Cronograma(usuario_uid=user.id, caderno_id=caderno_id, **payload.model_dump())
    db.add(c)
    await db.flush()
    # simulados (marcos) gerados na criação
    if payload.incluir_simulados:
        for s in core.gerar_simulados(payload.data_inicio, payload.data_prova, payload.buffer_dias):
            db.add(CronogramaSimulado(cronograma_id=c.id, **s))
    # discursivas via IA são geradas na Task 8 (chamada aqui quando incluir_discursivas)
    await db.commit()
    await db.refresh(c)
    return await _montar_resposta(db, cad, c)


@router.get("/cadernos/{caderno_id}/cronograma")
async def obter_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    return await _montar_resposta(db, cad, c)


@router.put("/cadernos/{caderno_id}/cronograma")
async def atualizar_cronograma(
    caderno_id: int, payload: CronogramaIn,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    for k, v in payload.model_dump().items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return await _montar_resposta(db, cad, c)


@router.delete("/cadernos/{caderno_id}/cronograma")
async def deletar_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    await db.execute(sa_delete(Cronograma).where(Cronograma.id == c.id))
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Registrar o router**

Em `backend/main.py`, após as linhas 192-193 (`from q_router import ...` / `app.include_router(q_router)`), adicionar:

```python
from cronograma_router import router as cronograma_router  # noqa: E402
app.include_router(cronograma_router)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_cronograma_router.py -v`
Expected: PASS (5 passed). Nota: o validator do Pydantic levanta `ValueError` → FastAPI responde 422 (test_data_prova_invalida_422).

- [ ] **Step 6: Commit**

```bash
git add backend/cronograma_router.py backend/main.py backend/tests/test_cronograma_router.py
git commit -m "feat(cronograma): endpoints config CRUD + plano/KPIs/revisões na resposta"
```

---

## Task 7: PUT "Recalcular automático" (rebaseline) + PATCH simulados

**Files:**
- Modify: `backend/cronograma_router.py`
- Test: `backend/tests/test_cronograma_router.py`

- [ ] **Step 1: Escrever os testes (falhando)**

Adicionar a `backend/tests/test_cronograma_router.py`:

```python
@pytest.mark.asyncio
async def test_recalcular_rebaseline(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-06-01"})
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma/recalcular")
    assert r.status_code == 200
    assert r.json()["config"]["rebaseline_em"] is not None


@pytest.mark.asyncio
async def test_patch_simulado_resultado(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    body = (await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
            json={"data_prova": "2026-08-16", "data_inicio": "2026-05-25",
                  "incluir_simulados": True})).json()
    assert body["simulados"], "deve ter marcos de simulado"
    sid = body["simulados"][0]["id"]
    r = await client.patch(
        f"/api/q/cadernos/{cad.id}/cronograma/simulados/{sid}",
        json={"resultado_objetiva": 88, "observacoes": "ok"},
    )
    assert r.status_code == 200
    novo = (await client.get(f"/api/q/cadernos/{cad.id}/cronograma")).json()
    alvo = next(s for s in novo["simulados"] if s["id"] == sid)
    assert alvo["resultado_objetiva"] == 88
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_router.py -k "rebaseline or simulado" -v`
Expected: FAIL — rotas inexistentes.

- [ ] **Step 3: Implementar recalcular + patch simulado**

Adicionar a `backend/cronograma_router.py` (antes do `@router.delete`):

```python
@router.post("/cadernos/{caderno_id}/cronograma/recalcular")
async def recalcular_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Re-ancora o plano em hoje: a curva de meta passa a partir de hoje com o
    restante das questões. Mantém datas de prova/folgas/buffer."""
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    c.rebaseline_em = date.today()
    await db.commit()
    await db.refresh(c)
    return await _montar_resposta(db, cad, c)


class SimuladoPatch(BaseModel):
    resultado_objetiva: Optional[int] = None
    resultado_discursiva: Optional[float] = None
    observacoes: Optional[str] = None


@router.patch("/cadernos/{caderno_id}/cronograma/simulados/{sim_id}")
async def patch_simulado(
    caderno_id: int, sim_id: int, payload: SimuladoPatch,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    sim = (await db.execute(
        select(CronogramaSimulado).where(
            CronogramaSimulado.id == sim_id, CronogramaSimulado.cronograma_id == c.id
        )
    )).scalar_one_or_none()
    if not sim:
        raise HTTPException(404, "simulado não encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sim, k, v)
    await db.commit()
    return {"ok": True}
```

> Nota sobre rebaseline no core: `_montar_resposta` já usa `inicio_efetivo = c.rebaseline_em or c.data_inicio` ao chamar `gerar_plano`. Como `gerar_plano` redistribui `cad.total` pelos dias úteis a partir de `inicio_efetivo`, ancorar em hoje já redistribui a carga futura. (O total não muda; a curva recomeça de hoje — efeito desejado de "redistribuir o que falta pelos dias que sobram".)

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_cronograma_router.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/cronograma_router.py backend/tests/test_cronograma_router.py
git commit -m "feat(cronograma): recalcular automático (rebaseline) + PATCH simulado"
```

---

## Task 8: Discursivas via IA (gemini_service) + persistência + PATCH + regenerar

**Files:**
- Modify: `backend/gemini_service.py`, `backend/cronograma_router.py`
- Test: `backend/tests/test_cronograma_router.py`

- [ ] **Step 1: Escrever os testes (falhando) — com monkeypatch do Gemini**

Adicionar a `backend/tests/test_cronograma_router.py`:

```python
import cronograma_router as cr


@pytest.mark.asyncio
async def test_criar_com_discursivas_usa_ia(client, db_session, auth_state, monkeypatch):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    monkeypatch.setattr(cr, "gerar_temas_discursivas",
                        lambda materias, n: [f"Tema IA {i}" for i in range(n)])
    body = (await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_discursivas": True, "discursivas_por_semana": 2,
    })).json()
    assert len(body["discursivas"]) >= 1
    assert body["discursivas"][0]["tema"].startswith("Tema IA")


@pytest.mark.asyncio
async def test_ia_indisponivel_nao_bloqueia(client, db_session, auth_state, monkeypatch):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    def _boom(materias, n):
        raise RuntimeError("gemini down")
    monkeypatch.setattr(cr, "gerar_temas_discursivas", _boom)
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_discursivas": True,
    })
    assert r.status_code == 200
    assert r.json()["discursivas"] == []


@pytest.mark.asyncio
async def test_patch_discursiva_status(client, db_session, auth_state, monkeypatch):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    monkeypatch.setattr(cr, "gerar_temas_discursivas", lambda m, n: ["T1", "T2"])
    body = (await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_discursivas": True})).json()
    did = body["discursivas"][0]["id"]
    r = await client.patch(f"/api/q/cadernos/{cad.id}/cronograma/discursivas/{did}",
                           json={"status": "Feita", "nota": 17.5})
    assert r.status_code == 200
    novo = (await client.get(f"/api/q/cadernos/{cad.id}/cronograma")).json()
    alvo = next(d for d in novo["discursivas"] if d["id"] == did)
    assert alvo["status"] == "Feita" and alvo["nota"] == 17.5
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_router.py -k "discursiva or ia" -v`
Expected: FAIL — `gerar_temas_discursivas` não existe / rota patch ausente.

- [ ] **Step 3: Implementar `gerar_temas_discursivas` no gemini_service**

Adicionar ao fim de `backend/gemini_service.py`:

```python
def gerar_temas_discursivas(materias: list[str], n: int = 18) -> list[str]:
    """Sugere `n` temas de discursiva (caso prático) a partir das matérias do caderno.

    Retorna lista de strings. Levanta em caso de falha de IA — o chamador trata.
    """
    materias_txt = ", ".join(materias) or "tema geral do concurso"
    prompt = (
        "Você é um examinador de concursos. Gere "
        f"{n} temas de questão DISCURSIVA (caso prático, até 20 linhas) "
        f"para um candidato que estuda estas matérias: {materias_txt}. "
        "Cada tema deve ser específico e cobrir um aspecto diferente. "
        'Responda APENAS um JSON no formato {"temas": ["...", "..."]}.'
    )
    client = _get_client()
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=1.0, response_mime_type="application/json"
        ),
    )
    data = json.loads(response.text)
    temas = data.get("temas", []) if isinstance(data, dict) else []
    return [str(t).strip() for t in temas if str(t).strip()][:n]
```

- [ ] **Step 4: Ligar IA na criação + endpoint PATCH/regenerar**

Em `backend/cronograma_router.py`:

(a) No topo, importar:
```python
from gemini_service import gerar_temas_discursivas
import logging
_log = logging.getLogger("cronograma")
```

(b) Adicionar helper que coleta matérias do caderno e popula discursivas:
```python
async def _materias_do_caderno(db: AsyncSession, cad: CadernoQuestoes) -> list[str]:
    from models import Questao, Materia
    ids = cad.question_ids or []
    if not ids:
        return []
    rows = (await db.execute(
        select(Materia.nome, func.count())
        .join(Questao, Questao.materia_id == Materia.id)
        .where(Questao.id.in_(ids))
        .group_by(Materia.nome).order_by(func.count().desc())
    )).all()
    return [nome for nome, _ in rows]


async def _popular_discursivas(db: AsyncSession, cad: CadernoQuestoes, c: Cronograma) -> None:
    """Gera temas via IA e agenda em terças/quintas. Falha de IA não propaga."""
    try:
        materias = await _materias_do_caderno(db, cad)
        temas = gerar_temas_discursivas(materias, n=18)
    except Exception as e:  # noqa: BLE001
        _log.warning("IA de discursivas indisponível: %s", e)
        return
    fim_1volta = c.data_prova - __import__("datetime").timedelta(days=c.buffer_dias)
    agenda = core.agendar_discursivas(temas, c.data_inicio, fim_1volta, c.discursivas_por_semana)
    for data_, tema in agenda:
        db.add(CronogramaDiscursiva(cronograma_id=c.id, data=data_, tema=tema,
                                    tipo="Treino 20 linhas", qtd=1, status="Pendente",
                                    reescrita=False))
```

(c) Em `criar_cronograma`, após gerar simulados e **antes** do `await db.commit()`:
```python
    if payload.incluir_discursivas:
        await _popular_discursivas(db, cad, c)
```

(d) Adicionar PATCH e regenerar:
```python
class DiscursivaPatch(BaseModel):
    status: Optional[str] = None
    nota: Optional[float] = None
    reescrita: Optional[bool] = None
    observacoes: Optional[str] = None


@router.patch("/cadernos/{caderno_id}/cronograma/discursivas/{disc_id}")
async def patch_discursiva(
    caderno_id: int, disc_id: int, payload: DiscursivaPatch,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    d = (await db.execute(
        select(CronogramaDiscursiva).where(
            CronogramaDiscursiva.id == disc_id, CronogramaDiscursiva.cronograma_id == c.id
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "discursiva não encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    await db.commit()
    return {"ok": True}


@router.post("/cadernos/{caderno_id}/cronograma/discursivas/regenerar")
async def regenerar_discursivas(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    await db.execute(
        sa_delete(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == c.id)
    )
    await _popular_discursivas(db, cad, c)
    await db.commit()
    return await _montar_resposta(db, cad, c)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_cronograma_router.py -v`
Expected: PASS (todos). O monkeypatch substitui `cr.gerar_temas_discursivas` — por isso o import é `from gemini_service import gerar_temas_discursivas` (vira atributo do módulo `cronograma_router`).

- [ ] **Step 6: Commit**

```bash
git add backend/gemini_service.py backend/cronograma_router.py backend/tests/test_cronograma_router.py
git commit -m "feat(cronograma): discursivas via IA (Gemini) + PATCH + regenerar"
```

---

## Task 9: Export `.xlsx`

**Files:**
- Create: `backend/cronograma_xlsx.py`
- Modify: `backend/cronograma_router.py`
- Test: `backend/tests/test_cronograma_xlsx.py`

- [ ] **Step 1: Escrever o teste (falhando)**

Criar `backend/tests/test_cronograma_xlsx.py`:

```python
import io
from datetime import date

import openpyxl

from cronograma_core import gerar_plano, gerar_simulados


def test_montar_workbook_tem_abas_e_dados():
    plano = gerar_plano(date(2026, 5, 25), date(2026, 8, 16), 876, [6], 21)
    from cronograma_xlsx import montar_workbook
    payload = {
        "nome_caderno": "ALECE Eng Civil 876",
        "total": 876,
        "data_inicio": date(2026, 5, 25),
        "data_prova": date(2026, 8, 16),
        "plano": plano,
        "discursivas": [{"data": date(2026, 5, 26), "tema": "Fiscalização",
                         "tipo": "Treino 20 linhas", "qtd": 1, "status": "Pendente"}],
        "simulados": gerar_simulados(date(2026, 5, 25), date(2026, 8, 16), 21),
    }
    wb_bytes = montar_workbook(payload)
    wb = openpyxl.load_workbook(io.BytesIO(wb_bytes))
    assert {"Painel", "Cronograma", "Discursivas", "Simulados"} <= set(wb.sheetnames)
    crono = wb["Cronograma"]
    assert crono["A1"].value == "Data"
    # tem uma linha por dia do plano + cabeçalho
    assert crono.max_row == len(plano) + 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_cronograma_xlsx.py -v`
Expected: FAIL — `No module named 'cronograma_xlsx'`.

- [ ] **Step 3: Implementar o builder**

Criar `backend/cronograma_xlsx.py`:

```python
"""Monta a planilha .xlsx do cronograma (estilo da planilha modelo ALECE)."""
from __future__ import annotations

import io
from datetime import date
from typing import Any

from openpyxl import Workbook

_DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
_FASE_LABEL = {
    "1volta": "1ª volta – resolver questões",
    "folga": "Folga/buffer",
    "buffer": "Buffer – revisão, erradas e simulados",
    "prova": "PROVA",
}


def montar_workbook(payload: dict[str, Any]) -> bytes:
    wb = Workbook()

    # ── Painel ──
    ws = wb.active
    ws.title = "Painel"
    ws["A1"] = f"Cronograma — {payload['nome_caderno']}"
    linhas = [
        ("Métrica", "Valor"),
        ("Data inicial", payload["data_inicio"]),
        ("Data da prova", payload["data_prova"]),
        ("Total de questões", payload["total"]),
        ("Questões resolvidas", "=COUNTIF(Cronograma!J:J,\">0\")"),
    ]
    for i, (a, b) in enumerate(linhas, start=3):
        ws.cell(i, 1, a)
        ws.cell(i, 2, b)

    # ── Cronograma ──
    cr = wb.create_sheet("Cronograma")
    headers = ["Data", "Dia", "Fase", "Questões novas", "Meta acumulada",
               "Feitas no dia", "Acumulado real", "Saldo", "Observações"]
    cr.append(headers)
    for r, d in enumerate(payload["plano"], start=2):
        cr.cell(r, 1, d.data)
        cr.cell(r, 2, _DIAS_PT[d.weekday])
        cr.cell(r, 3, _FASE_LABEL.get(d.fase, d.fase))
        cr.cell(r, 4, d.questoes_novas)
        cr.cell(r, 5, d.meta_acumulada)
        # J (col 10 na planilha modelo) é "feitas no dia"; aqui col 6 + fórmulas relativas
        cr.cell(r, 7, f"=SUM($F$2:F{r})")
        cr.cell(r, 8, f"=G{r}-E{r}")

    # ── Discursivas ──
    di = wb.create_sheet("Discursivas")
    di.append(["Data", "Tema", "Tipo", "Qtd", "Status", "Nota", "Observações"])
    for x in payload.get("discursivas", []):
        di.append([x["data"], x["tema"], x.get("tipo", ""), x.get("qtd", 1),
                   x.get("status", "Pendente"), x.get("nota"), x.get("observacoes")])

    # ── Simulados ──
    si = wb.create_sheet("Simulados")
    si.append(["Data", "Tipo", "Objetivas planejadas", "Meta objetiva",
               "Resultado objetiva", "Discursiva planejada", "Resultado discursiva"])
    for s in payload.get("simulados", []):
        si.append([s["data"], s["tipo"], s.get("objetivas_planejadas", 0),
                   s.get("meta_objetiva", 0), s.get("resultado_objetiva"),
                   s.get("discursiva_planejada", 0), s.get("resultado_discursiva")])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_cronograma_xlsx.py -v`
Expected: PASS.

- [ ] **Step 5: Endpoint de download**

Adicionar a `backend/cronograma_router.py`:

(a) imports no topo:
```python
from fastapi.responses import StreamingResponse
from cronograma_xlsx import montar_workbook
```

(b) endpoint:
```python
@router.get("/cadernos/{caderno_id}/cronograma/export.xlsx")
async def exportar_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
):
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    inicio_efetivo = c.rebaseline_em or c.data_inicio
    plano = core.gerar_plano(inicio_efetivo, c.data_prova, cad.total or 0,
                             c.dias_folga or [], c.buffer_dias)
    discs = (await db.execute(
        select(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == c.id)
        .order_by(CronogramaDiscursiva.data)
    )).scalars().all()
    sims = (await db.execute(
        select(CronogramaSimulado).where(CronogramaSimulado.cronograma_id == c.id)
        .order_by(CronogramaSimulado.data)
    )).scalars().all()
    blob = montar_workbook({
        "nome_caderno": cad.nome, "total": cad.total or 0,
        "data_inicio": c.data_inicio, "data_prova": c.data_prova, "plano": plano,
        "discursivas": [{"data": x.data, "tema": x.tema, "tipo": x.tipo, "qtd": x.qtd,
                         "status": x.status, "nota": x.nota, "observacoes": x.observacoes}
                        for x in discs],
        "simulados": [{"data": s.data, "tipo": s.tipo,
                       "objetivas_planejadas": s.objetivas_planejadas,
                       "meta_objetiva": s.meta_objetiva,
                       "resultado_objetiva": s.resultado_objetiva,
                       "discursiva_planejada": s.discursiva_planejada,
                       "resultado_discursiva": s.resultado_discursiva} for s in sims],
    })
    nome = f"cronograma_caderno_{caderno_id}.xlsx"
    return StreamingResponse(
        io_module.BytesIO(blob),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
```

(c) garantir `import io as io_module` no topo do router.

- [ ] **Step 6: Teste de fumaça do endpoint export**

Adicionar a `backend/tests/test_cronograma_router.py`:

```python
@pytest.mark.asyncio
async def test_export_xlsx(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-05-25"})
    r = await client.get(f"/api/q/cadernos/{cad.id}/cronograma/export.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats")
    assert len(r.content) > 0
```

Run: `python -m pytest tests/test_cronograma_router.py tests/test_cronograma_xlsx.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/cronograma_xlsx.py backend/cronograma_router.py backend/tests/test_cronograma_xlsx.py backend/tests/test_cronograma_router.py
git commit -m "feat(cronograma): export .xlsx (Painel/Cronograma/Discursivas/Simulados)"
```

---

## Task 10: Frontend — camada de API tipada

**Files:**
- Create: `fontend/app/q/caderno/[id]/cronograma/api.ts`

- [ ] **Step 1: Implementar o cliente**

Criar `fontend/app/q/caderno/[id]/cronograma/api.ts`. Reusa `apiFetch` de `fontend/lib/api.ts` (já trata JWT/CSRF/handoff). Tipos espelham a resposta do backend.

```typescript
import { apiFetch } from "@/lib/api";

export type CronogramaConfig = {
  caderno_id: number; data_inicio: string; data_prova: string;
  rebaseline_em: string | null; dias_folga: number[]; buffer_dias: number;
  incluir_revisao: boolean; incluir_discursivas: boolean;
  incluir_simulados: boolean; discursivas_por_semana: number;
};
export type DiaPlano = {
  data: string; weekday: number; fase: string;
  questoes_novas: number; meta_acumulada: number; hoje: boolean;
};
export type Kpis = {
  total: number; resolvidas: number; acertos: number; erros: number;
  pct_conclusao: number; pct_acerto: number; restantes: number;
  dias_uteis_restantes: number; questoes_dia_necessarias: number;
  meta_hoje: number; saldo: number;
};
export type Discursiva = {
  id: number; data: string; tema: string; tipo: string; qtd: number;
  status: string; nota: number | null; reescrita: boolean; observacoes: string | null;
};
export type Simulado = {
  id: number; data: string; tipo: string; objetivas_planejadas: number;
  meta_objetiva: number; resultado_objetiva: number | null;
  discursiva_planejada: number; resultado_discursiva: number | null;
  observacoes: string | null;
};
export type RevisaoItem = { questao_id: number; revisar_em: string; intervalo: string };
export type CronogramaResp = {
  config: CronogramaConfig; plano: DiaPlano[]; kpis: Kpis;
  revisar_hoje: RevisaoItem[]; discursivas: Discursiva[]; simulados: Simulado[];
};
export type CronogramaInput = {
  data_prova: string; data_inicio: string; dias_folga: number[];
  buffer_dias: number; incluir_revisao: boolean; incluir_discursivas: boolean;
  incluir_simulados: boolean; discursivas_por_semana: number;
};

const base = (id: string | number) => `/api/q/cadernos/${id}/cronograma`;

export async function getCronograma(id: string): Promise<CronogramaResp | null> {
  const r = await apiFetch(base(id));
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("falha ao carregar cronograma");
  return r.json();
}
export async function criarCronograma(id: string, body: CronogramaInput): Promise<CronogramaResp> {
  const r = await apiFetch(base(id), { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "falha ao criar");
  return r.json();
}
export async function atualizarCronograma(id: string, body: CronogramaInput): Promise<CronogramaResp> {
  const r = await apiFetch(base(id), { method: "PUT", body: JSON.stringify(body) });
  if (!r.ok) throw new Error("falha ao atualizar");
  return r.json();
}
export async function recalcular(id: string): Promise<CronogramaResp> {
  const r = await apiFetch(`${base(id)}/recalcular`, { method: "POST" });
  if (!r.ok) throw new Error("falha ao recalcular");
  return r.json();
}
export async function deletarCronograma(id: string): Promise<void> {
  await apiFetch(base(id), { method: "DELETE" });
}
export async function patchDiscursiva(id: string, did: number, body: Partial<Discursiva>) {
  await apiFetch(`${base(id)}/discursivas/${did}`, { method: "PATCH", body: JSON.stringify(body) });
}
export async function regenerarDiscursivas(id: string): Promise<CronogramaResp> {
  const r = await apiFetch(`${base(id)}/discursivas/regenerar`, { method: "POST" });
  if (!r.ok) throw new Error("falha ao regenerar");
  return r.json();
}
export async function patchSimulado(id: string, sid: number, body: Partial<Simulado>) {
  await apiFetch(`${base(id)}/simulados/${sid}`, { method: "PATCH", body: JSON.stringify(body) });
}
export function exportUrl(id: string): string {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";
  return `${apiBase}${base(id)}/export.xlsx`;
}
```

> Conferir a assinatura exata de `apiFetch` em `fontend/lib/api.ts:69` (path relativo + options) e ajustar se necessário. Para o download `.xlsx`, abrir `exportUrl(id)` em nova aba com `credentials: include` — como `apiFetch` injeta cabeçalhos, alternativamente baixar via `apiFetch` + `blob()` e `URL.createObjectURL` (ver Task 12).

- [ ] **Step 2: Verificação de tipo**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos no arquivo `api.ts`.

- [ ] **Step 3: Commit**

```bash
git add fontend/app/q/caderno/[id]/cronograma/api.ts
git commit -m "feat(cronograma): cliente de API tipado no frontend"
```

---

## Task 11: Frontend — formulário de criação (ConfigForm)

**Files:**
- Create: `fontend/app/q/caderno/[id]/cronograma/components/ConfigForm.tsx`

- [ ] **Step 1: Implementar o form**

Criar `ConfigForm.tsx`. Segue os tokens/estilo do projeto (`bg-surface`, `border-border/60`, `text-primary`). 7 checkboxes de dias da semana (default: domingo = folga marcada). Props: valores iniciais opcionais + `onSubmit(input)`.

```tsx
"use client";
import { useState } from "react";
import type { CronogramaInput } from "../api";

const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]; // index = weekday (0..6)

export function ConfigForm({
  initial, submitLabel, onSubmit,
}: {
  initial?: Partial<CronogramaInput>;
  submitLabel: string;
  onSubmit: (input: CronogramaInput) => Promise<void>;
}) {
  const hoje = new Date().toISOString().slice(0, 10);
  const [dataInicio, setDataInicio] = useState(initial?.data_inicio ?? hoje);
  const [dataProva, setDataProva] = useState(initial?.data_prova ?? "");
  const [folga, setFolga] = useState<number[]>(initial?.dias_folga ?? [6]);
  const [buffer, setBuffer] = useState(initial?.buffer_dias ?? 21);
  const [discursivas, setDiscursivas] = useState(initial?.incluir_discursivas ?? false);
  const [simulados, setSimulados] = useState(initial?.incluir_simulados ?? true);
  const [revisao, setRevisao] = useState(initial?.incluir_revisao ?? true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const toggleDia = (w: number) =>
    setFolga((f) => (f.includes(w) ? f.filter((x) => x !== w) : [...f, w]));

  async function submit() {
    setErr("");
    if (!dataProva) { setErr("Informe a data da prova."); return; }
    if (dataProva <= dataInicio) { setErr("A prova deve ser depois do início."); return; }
    setBusy(true);
    try {
      await onSubmit({
        data_prova: dataProva, data_inicio: dataInicio, dias_folga: folga,
        buffer_dias: buffer, incluir_revisao: revisao,
        incluir_discursivas: discursivas, incluir_simulados: simulados,
        discursivas_por_semana: 2,
      });
    } catch (e) { setErr(e instanceof Error ? e.message : "Erro"); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-lg mx-auto bg-surface border border-border/60 rounded-lg p-6 space-y-4">
      <h2 className="text-lg font-semibold text-fg">Configurar cronograma</h2>
      <label className="block text-sm">Data da prova
        <input type="date" value={dataProva} onChange={(e) => setDataProva(e.target.value)}
          className="mt-1 w-full bg-surface-2 border border-border/60 rounded px-3 py-2" />
      </label>
      <label className="block text-sm">Início
        <input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)}
          className="mt-1 w-full bg-surface-2 border border-border/60 rounded px-3 py-2" />
      </label>
      <div className="text-sm">
        <span className="block mb-1">Dias de folga (reservados)</span>
        <div className="flex gap-1">
          {DIAS.map((d, w) => (
            <button key={w} type="button" onClick={() => toggleDia(w)}
              className={`px-2 py-1 rounded text-xs border ${
                folga.includes(w) ? "bg-primary/10 border-primary/40 text-primary"
                                  : "bg-surface-2 border-border/60 text-fg-muted"}`}>
              {d}
            </button>
          ))}
        </div>
        <p className="text-xs text-fg-faint mt-1">Sábado fica como dia de estudo por padrão; marque para reservar.</p>
      </div>
      <label className="block text-sm">Buffer de reta final (dias)
        <input type="number" min={0} max={120} value={buffer}
          onChange={(e) => setBuffer(Number(e.target.value))}
          className="mt-1 w-full bg-surface-2 border border-border/60 rounded px-3 py-2" />
      </label>
      <div className="space-y-1 text-sm">
        {[["Revisão espaçada das erradas", revisao, setRevisao],
          ["Discursivas (temas via IA)", discursivas, setDiscursivas],
          ["Simulados", simulados, setSimulados]].map(([label, val, set]: any) => (
          <label key={label} className="flex items-center gap-2">
            <input type="checkbox" checked={val} onChange={(e) => set(e.target.checked)} />
            {label}
          </label>
        ))}
      </div>
      {err && <p className="text-error text-sm">{err}</p>}
      <button onClick={submit} disabled={busy}
        className="w-full bg-primary text-black font-semibold rounded py-2 disabled:opacity-50">
        {busy ? "Gerando…" : submitLabel}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
git add fontend/app/q/caderno/[id]/cronograma/components/ConfigForm.tsx
git commit -m "feat(cronograma): formulário de configuração (frontend)"
```

---

## Task 12: Frontend — dashboard (KPIs, timeline, revisar hoje, discursivas, simulados) + página

**Files:**
- Create: `fontend/app/q/caderno/[id]/cronograma/components/KpiStrip.tsx`
- Create: `fontend/app/q/caderno/[id]/cronograma/components/TimelineTable.tsx`
- Create: `fontend/app/q/caderno/[id]/cronograma/components/RevisarHoje.tsx`
- Create: `fontend/app/q/caderno/[id]/cronograma/components/DiscursivasList.tsx`
- Create: `fontend/app/q/caderno/[id]/cronograma/components/SimuladosList.tsx`
- Create: `fontend/app/q/caderno/[id]/cronograma/page.tsx`

- [ ] **Step 1: KpiStrip** (`StatCard` do DS em `fontend/app/components/ds/StatCard.tsx`)

```tsx
"use client";
import type { Kpis } from "../api";

export function KpiStrip({ kpis, diasAteProva }: { kpis: Kpis; diasAteProva: number }) {
  const saldo = kpis.saldo;
  const saldoLabel = saldo >= 0 ? `+${saldo} adiantado` : `${saldo} atrasado`;
  const cards = [
    { label: "Conclusão", value: `${Math.round(kpis.pct_conclusao * 100)}%`,
      sub: `${kpis.resolvidas}/${kpis.total}` },
    { label: "Acerto", value: `${Math.round(kpis.pct_acerto * 100)}%`,
      sub: `${kpis.acertos} acertos` },
    { label: "Saldo vs meta", value: saldoLabel,
      sub: `meta hoje: ${kpis.meta_hoje}` },
    { label: "Ritmo necessário", value: `${kpis.questoes_dia_necessarias}/dia`,
      sub: `${kpis.dias_uteis_restantes} dias úteis` },
    { label: "Dias até a prova", value: String(diasAteProva), sub: "" },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="bg-surface border border-border/60 rounded-lg p-3">
          <div className="text-xs text-fg-faint">{c.label}</div>
          <div className={`text-lg font-semibold ${
            c.label === "Saldo vs meta" && saldo < 0 ? "text-error" : "text-fg"}`}>{c.value}</div>
          <div className="text-xs text-fg-muted">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: TimelineTable** (destaca `hoje`, traduz fase)

```tsx
"use client";
import type { DiaPlano } from "../api";

const FASE: Record<string, string> = {
  "1volta": "1ª volta", folga: "Folga", buffer: "Buffer", prova: "PROVA",
};

export function TimelineTable({ plano }: { plano: DiaPlano[] }) {
  return (
    <div className="overflow-auto max-h-[480px] border border-border/60 rounded-lg">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface-2 text-fg-muted text-xs">
          <tr>
            {["Data", "Fase", "Meta dia", "Meta acum."].map((h) => (
              <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {plano.map((d) => (
            <tr key={d.data} className={`border-t border-border/40 ${
              d.hoje ? "bg-primary/10" : ""}`}>
              <td className="px-3 py-1.5">{d.data.slice(5)}{d.hoje && " ◀ hoje"}</td>
              <td className="px-3 py-1.5 text-fg-muted">{FASE[d.fase] ?? d.fase}</td>
              <td className="px-3 py-1.5">{d.questoes_novas || "—"}</td>
              <td className="px-3 py-1.5">{d.meta_acumulada}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: RevisarHoje, DiscursivasList, SimuladosList**

`RevisarHoje.tsx`:
```tsx
"use client";
import type { RevisaoItem } from "../api";
export function RevisarHoje({ itens }: { itens: RevisaoItem[] }) {
  if (!itens.length) return <p className="text-sm text-fg-faint">Nada para revisar hoje. 🎉</p>;
  return (
    <ul className="space-y-1 text-sm">
      {itens.map((i) => (
        <li key={`${i.questao_id}-${i.intervalo}`}
            className="flex justify-between bg-surface border border-border/60 rounded px-3 py-1.5">
          <a className="text-primary" href={`/q/questao/${i.questao_id}`}>Questão #{i.questao_id}</a>
          <span className="text-fg-faint">{i.intervalo} · vence {i.revisar_em.slice(5)}</span>
        </li>
      ))}
    </ul>
  );
}
```

`DiscursivasList.tsx` (status editável via `patchDiscursiva`, regenerar):
```tsx
"use client";
import { useState } from "react";
import type { Discursiva } from "../api";
import { patchDiscursiva, regenerarDiscursivas } from "../api";

const STATUS = ["Pendente", "Feita", "Rever", "Reescrita"];

export function DiscursivasList({ id, itens, onChange }:
  { id: string; itens: Discursiva[]; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  if (!itens.length) {
    return (
      <button disabled={busy} onClick={async () => { setBusy(true); await regenerarDiscursivas(id); onChange(); setBusy(false); }}
        className="text-sm text-primary">{busy ? "Gerando temas…" : "Gerar temas por IA"}</button>
    );
  }
  return (
    <div className="space-y-2">
      {itens.map((d) => (
        <div key={d.id} className="bg-surface border border-border/60 rounded px-3 py-2 text-sm">
          <div className="flex justify-between gap-2">
            <span className="text-fg-faint">{d.data.slice(5)}</span>
            <select defaultValue={d.status}
              onChange={async (e) => { await patchDiscursiva(id, d.id, { status: e.target.value }); onChange(); }}
              className="bg-surface-2 border border-border/60 rounded text-xs px-1">
              {STATUS.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <p className="mt-1">{d.tema}</p>
        </div>
      ))}
    </div>
  );
}
```

`SimuladosList.tsx` (registra `resultado_objetiva` via `patchSimulado`):
```tsx
"use client";
import type { Simulado } from "../api";
import { patchSimulado } from "../api";
export function SimuladosList({ id, itens, onChange }:
  { id: string; itens: Simulado[]; onChange: () => void }) {
  if (!itens.length) return <p className="text-sm text-fg-faint">Sem simulados.</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-fg-muted text-xs">
        <tr><th className="text-left py-1">Data</th><th className="text-left">Tipo</th>
        <th className="text-left">Meta</th><th className="text-left">Resultado</th></tr>
      </thead>
      <tbody>
        {itens.map((s) => (
          <tr key={s.id} className="border-t border-border/40">
            <td className="py-1">{s.data.slice(5)}</td>
            <td>{s.tipo}</td>
            <td>{s.meta_objetiva}</td>
            <td>
              <input type="number" defaultValue={s.resultado_objetiva ?? ""}
                onBlur={async (e) => { await patchSimulado(id, s.id,
                  { resultado_objetiva: e.target.value ? Number(e.target.value) : null }); onChange(); }}
                className="w-16 bg-surface-2 border border-border/60 rounded px-1" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: page.tsx** (orquestra criação vs dashboard; download .xlsx via blob)

```tsx
"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import {
  getCronograma, criarCronograma, recalcular, exportUrl,
  type CronogramaResp, type CronogramaInput,
} from "./api";
import { ConfigForm } from "./components/ConfigForm";
import { KpiStrip } from "./components/KpiStrip";
import { TimelineTable } from "./components/TimelineTable";
import { RevisarHoje } from "./components/RevisarHoje";
import { DiscursivasList } from "./components/DiscursivasList";
import { SimuladosList } from "./components/SimuladosList";

export default function CronogramaPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<CronogramaResp | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setData(await getCronograma(id));
    setLoading(false);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  async function onCreate(input: CronogramaInput) {
    setData(await criarCronograma(id, input));
  }
  async function baixarXlsx() {
    const r = await apiFetch(`/api/q/cadernos/${id}/cronograma/export.xlsx`);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `cronograma_${id}.xlsx`; a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <div className="p-6 text-fg-muted">Carregando…</div>;
  if (!data) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold mb-4">Criar cronograma</h1>
        <ConfigForm submitLabel="Gerar cronograma" onSubmit={onCreate} />
      </div>
    );
  }

  const diasAteProva = Math.max(
    0, Math.ceil((+new Date(data.config.data_prova) - Date.now()) / 86400000));

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Cronograma</h1>
        <div className="flex gap-2">
          <button onClick={() => recalcular(id).then(setData)}
            className="text-sm border border-border/60 rounded px-3 py-1.5">Recalcular automático</button>
          <button onClick={baixarXlsx}
            className="text-sm bg-primary text-black font-semibold rounded px-3 py-1.5">Baixar .xlsx</button>
        </div>
      </div>
      <KpiStrip kpis={data.kpis} diasAteProva={diasAteProva} />
      <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Plano diário</h2>
        <TimelineTable plano={data.plano} /></section>
      {data.config.incluir_revisao && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Revisar hoje</h2>
          <RevisarHoje itens={data.revisar_hoje} /></section>)}
      {data.config.incluir_discursivas && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Discursivas</h2>
          <DiscursivasList id={id} itens={data.discursivas} onChange={load} /></section>)}
      {data.config.incluir_simulados && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Simulados</h2>
          <SimuladosList id={id} itens={data.simulados} onChange={load} /></section>)}
    </div>
  );
}
```

- [ ] **Step 5: Lint + smoke manual**

Run: `cd fontend && pnpm lint` (sem erros novos).
Smoke manual (com `./dev.sh up`): criar um caderno, abrir `/q/caderno/<id>/cronograma`, gerar com uma data de prova futura, conferir KPIs/timeline, resolver algumas questões e ver o saldo mudar, baixar o `.xlsx` e abrir no Excel/LibreOffice.

- [ ] **Step 6: Commit**

```bash
git add fontend/app/q/caderno/[id]/cronograma/
git commit -m "feat(cronograma): página viva (KPIs, timeline, revisões, discursivas, simulados, export)"
```

---

## Task 13: Pontos de entrada (player + sidebar Planejamento)

**Files:**
- Modify: `fontend/app/q/caderno/[id]/page.tsx` (header do player)
- Modify: `fontend/app/Sidebar.tsx:33`
- Create: `fontend/app/planejamento/page.tsx`

- [ ] **Step 1: Botão no player**

Em `fontend/app/q/caderno/[id]/page.tsx`, no breadcrumb/header do player (perto do nome do caderno), adicionar um link para o cronograma:

```tsx
<a href={`/q/caderno/${caderno.id}/cronograma`}
   className="text-xs border border-border/60 rounded px-2 py-1 text-primary hover:bg-primary/10">
  📅 Cronograma
</a>
```
(Inserir junto aos controles do cabeçalho existente; conferir o nome da variável do caderno na página — `caderno.id` ou o `id` do `useParams`.)

- [ ] **Step 2: Sidebar aponta para /planejamento**

Em `fontend/app/Sidebar.tsx:33`, trocar:
```tsx
{ href: "/em-breve?f=Planejamento", label: "Planejamento", icon: "calendar_month" },
```
por:
```tsx
{ href: "/planejamento", label: "Planejamento", icon: "calendar_month" },
```

- [ ] **Step 3: Página de listagem de cronogramas**

Criar `fontend/app/planejamento/page.tsx`. Lista cadernos com cronograma. Como não há endpoint de "listar cronogramas do usuário", reaproveitar `GET /api/q/cadernos` (cadernos do usuário) e, para cada, mostrar atalho ao cronograma — MVP simples:

```tsx
"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Caderno = { id: number; nome: string; pasta: string | null; total: number };

export default function PlanejamentoPage() {
  const [cadernos, setCadernos] = useState<Caderno[]>([]);
  useEffect(() => {
    apiFetch("/api/q/cadernos").then((r) => r.json()).then((d) =>
      setCadernos(Array.isArray(d) ? d : d.cadernos ?? []));
  }, []);
  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Planejamento</h1>
      <p className="text-sm text-fg-muted mb-4">Abra um caderno e gere seu cronograma de estudo.</p>
      <div className="grid gap-2">
        {cadernos.map((c) => (
          <a key={c.id} href={`/q/caderno/${c.id}/cronograma`}
             className="bg-surface border border-border/60 rounded-lg px-4 py-3 flex justify-between hover:border-primary/40">
            <span>{c.nome}</span>
            <span className="text-fg-faint text-sm">{c.total} questões · cronograma →</span>
          </a>
        ))}
      </div>
    </div>
  );
}
```
> Conferir o shape real de `GET /api/q/cadernos` (lista direta vs `{cadernos: [...]}`) em `fontend/app/q/cadernos/page.tsx:85` e ajustar o parse.

- [ ] **Step 4: Lint + smoke**

Run: `cd fontend && pnpm lint`.
Smoke: clicar "Planejamento" na sidebar → lista; clicar um caderno → cai no cronograma; no player, o botão 📅 leva ao cronograma.

- [ ] **Step 5: Commit**

```bash
git add fontend/app/q/caderno/[id]/page.tsx fontend/app/Sidebar.tsx fontend/app/planejamento/page.tsx
git commit -m "feat(cronograma): pontos de entrada (botão no player + sidebar Planejamento)"
```

---

## Task 14: Deploy (workflow obrigatório do projeto)

- [ ] **Step 1: Rodar a suíte de testes do backend**

Run (de `backend/`): `python -m pytest tests/test_cronograma_core.py tests/test_cronograma_router.py tests/test_cronograma_xlsx.py tests/test_cronograma_models.py tests/test_alembic_no_drift.py -v`
Expected: tudo PASS.

- [ ] **Step 2: Lint frontend**

Run: `cd fontend && pnpm lint`
Expected: sem erros.

- [ ] **Step 3: Push + deploy**

```bash
git push
./build.sh
```
O `db_prepare`/Alembic no startup aplica a migration `cronograma` em produção. Conferir `git status` limpo ao final (mover os `.xlsx` soltos não relacionados para fora ou deixá-los como estão — não commitar).

---

## Self-Review (preenchido pelo autor do plano)

**Spec coverage:**
- Página viva → Tasks 6, 12. Export .xlsx → Task 9. Ritmo automático/buffer/folgas → Task 2. Saldo vivo/KPIs → Task 3 + 6. Revisão espaçada auto → Task 3 + 6. Discursivas IA → Task 8. Simulados → Tasks 4, 7, 8. Recalcular automático (rebaseline) → Task 7. Toggle de dias de folga → Task 11. Modelo de dados (3 tabelas) → Task 5. Pontos de entrada (player + sidebar) → Task 13. Tudo coberto.
- Fora de escopo (composição por matéria/pesos do edital) — corretamente ausente.

**Placeholder scan:** sem TBD/TODO; cada step de código traz o código. O frontend tem trechos completos por componente; pontos a confirmar contra o código existente estão marcados com `>` (shape de `apiFetch`/`GET /api/q/cadernos`).

**Type consistency:** `gerar_plano`/`DiaPlano`/`calcular_kpis`/`PainelKPIs`/`derivar_revisoes`/`ItemRevisao`/`agendar_discursivas`/`gerar_simulados` usados de forma consistente entre core, router e xlsx. Models `Cronograma`/`CronogramaDiscursiva`/`CronogramaSimulado` idem. Tipos do `api.ts` espelham as chaves da resposta de `_montar_resposta`.

**Pontos de atenção para o executor:**
- Os testes de `test_cronograma_models.py`/`test_cronograma_router.py` dependem das tabelas existirem no banco de teste. Confirmar como o conftest provisiona o schema do `studia_test` (migration aplicada vs `create_all`); se necessário, rodar `alembic upgrade head` apontando para o banco de teste antes da suíte.
- `gerar_plano` é chamado a cada GET — custo O(dias) (~80), trivial.
