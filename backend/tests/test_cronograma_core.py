from datetime import date

from cronograma_core import distribuir_carga


def test_distribuir_carga_exata_soma_total():
    cargas = distribuir_carga(total=100, n_dias=7)
    assert sum(cargas) == 100
    assert len(cargas) == 7
    assert max(cargas) - min(cargas) <= 1
    assert cargas == [15, 15, 14, 14, 14, 14, 14]


def test_distribuir_carga_divisivel():
    assert distribuir_carga(total=80, n_dias=8) == [10] * 8


def test_distribuir_carga_um_dia():
    assert distribuir_carga(total=42, n_dias=1) == [42]


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
    assert dias[0].data == date(2026, 6, 1)
    assert dias[-1].data == date(2026, 6, 28)
    assert dias[-1].fase == "prova"
    domingos = [d for d in dias if d.data.weekday() == 6 and d.fase != "prova"]
    assert all(d.questoes_novas == 0 and d.fase == "folga" for d in domingos)
    assert sum(d.questoes_novas for d in dias) == 120
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


from cronograma_core import calcular_kpis, derivar_revisoes, PainelKPIs, ItemRevisao


def _plano_simples():
    return gerar_plano(date(2026, 6, 1), date(2026, 6, 28), 120, [6], 7)


def test_calcular_kpis_saldo_adiantado():
    plano = _plano_simples()
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


from cronograma_core import agendar_discursivas, gerar_simulados


def test_agendar_discursivas_tercas_e_quintas():
    temas = [f"tema {i}" for i in range(6)]
    agenda = agendar_discursivas(
        temas, data_inicio=date(2026, 6, 1), fim_1volta=date(2026, 6, 28), por_semana=2
    )
    assert len(agenda) == 6
    assert all(d.weekday() in (1, 3) for d, _ in agenda)
    assert [t for _, t in agenda] == temas
    assert [d for d, _ in agenda] == sorted(d for d, _ in agenda)


def test_agendar_discursivas_sem_temas():
    assert agendar_discursivas([], date(2026, 6, 1), date(2026, 6, 28), 2) == []


def test_gerar_simulados_marcos():
    sims = gerar_simulados(
        data_inicio=date(2026, 5, 25), data_prova=date(2026, 8, 16), buffer_dias=21
    )
    assert len(sims) >= 2
    datas = [s["data"] for s in sims]
    assert datas == sorted(datas)
    assert datas[0] >= date(2026, 5, 25)
    assert datas[-1] <= date(2026, 8, 16)
    assert any(s["tipo"].startswith("Simulado completo") for s in sims)


# ─────────────────────────── progresso_diario ───────────────────────────

from cronograma_core import progresso_diario


def test_progresso_diario_acumula_distintas_na_primeira_resolucao():
    d1, d2, d3 = date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 5)
    resolucoes = [
        (10, True, d1),
        (11, False, d1),
        (10, False, d2),   # re-tentativa: não conta de novo
        (12, True, d3),
        (13, True, d2),
    ]
    curva = progresso_diario(resolucoes)
    assert curva == [
        {"data": "2026-06-01", "resolvidas": 2},
        {"data": "2026-06-02", "resolvidas": 3},
        {"data": "2026-06-05", "resolvidas": 4},
    ]


def test_progresso_diario_vazio():
    assert progresso_diario([]) == []
