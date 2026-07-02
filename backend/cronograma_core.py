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


def progresso_diario(
    resolucoes: list[tuple[int, bool, date]],
) -> list[dict]:
    """Curva real acumulada: questões DISTINTAS resolvidas até cada dia.

    Cada questão conta uma vez, na data da sua PRIMEIRA resolução (re-tentativas
    não inflam a curva). Saída ordenada por data: [{data, resolvidas}].
    """
    primeira: dict[int, date] = {}
    for qid, _acertou, dt in resolucoes:
        if qid not in primeira or dt < primeira[qid]:
            primeira[qid] = dt

    por_dia: dict[date, int] = {}
    for dt in primeira.values():
        por_dia[dt] = por_dia.get(dt, 0) + 1

    out: list[dict] = []
    acumulado = 0
    for dt in sorted(por_dia):
        acumulado += por_dia[dt]
        out.append({"data": dt.isoformat(), "resolvidas": acumulado})
    return out


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
    for offset, label in ((7, "Simulado completo"), (-7, "Simulado completo final")):
        d = (fim_1volta + timedelta(days=7)) if offset == 7 else (data_prova - timedelta(days=7))
        if data_inicio <= d <= data_prova:
            sims.append({"data": d, "tipo": label,
                         "objetivas_planejadas": 70, "meta_objetiva": 100,
                         "discursiva_planejada": 2})
    sims.sort(key=lambda s: s["data"])
    return sims
