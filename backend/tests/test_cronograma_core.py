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
