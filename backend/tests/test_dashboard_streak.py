"""Testes da função pura _compute_streak (dias consecutivos de estudo)."""
from __future__ import annotations

from datetime import date, timedelta


def test_streak_vazio_eh_zero():
    from q_router import _compute_streak

    assert _compute_streak(set(), date(2026, 6, 13)) == 0


def test_streak_conta_dias_consecutivos_ate_hoje():
    from q_router import _compute_streak

    hoje = date(2026, 6, 13)
    dias = {hoje, hoje - timedelta(days=1), hoje - timedelta(days=2)}
    assert _compute_streak(dias, hoje) == 3


def test_streak_so_hoje_eh_um():
    from q_router import _compute_streak

    hoje = date(2026, 6, 13)
    assert _compute_streak({hoje}, hoje) == 1


def test_streak_sem_hoje_mas_ontem_conta_a_partir_de_ontem():
    from q_router import _compute_streak

    hoje = date(2026, 6, 13)
    ontem = hoje - timedelta(days=1)
    anteontem = hoje - timedelta(days=2)
    assert _compute_streak({ontem, anteontem}, hoje) == 2


def test_streak_quebra_com_buraco():
    from q_router import _compute_streak

    hoje = date(2026, 6, 13)
    dias = {hoje, hoje - timedelta(days=1), hoje - timedelta(days=4)}
    assert _compute_streak(dias, hoje) == 2


def test_streak_zero_se_ultima_atividade_antiga():
    from q_router import _compute_streak

    hoje = date(2026, 6, 13)
    assert _compute_streak({hoje - timedelta(days=5)}, hoje) == 0
