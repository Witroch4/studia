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
