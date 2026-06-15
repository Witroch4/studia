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
