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
