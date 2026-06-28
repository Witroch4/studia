"""Status da questão deve marcar ANULADA mesmo quando o TC mente anulada=false
(a anulação real vem no prefixo 'ANULADA_' do gabarito)."""
from app.persistir import _derivar_status


def test_anulada_via_gabarito_mesmo_com_anulada_false():
    # caso real: TC retorna anulada=false, mas gabarito ANULADA_*
    assert _derivar_status("ANULADA_MULTIPLA_ESCOLHA", False, False) == "ANULADA"
    assert _derivar_status("ANULADA_CERTO_ERRADO", False, False) == "ANULADA"


def test_anulada_via_flag():
    assert _derivar_status("A", True, False) == "ANULADA"


def test_desatualizada():
    assert _derivar_status("B", False, True) == "DESATUALIZADA"


def test_ativa_normal():
    assert _derivar_status("C", False, False) == "ATIVA"
    assert _derivar_status("CERTO", False, False) == "ATIVA"


def test_gabarito_none_nao_quebra():
    assert _derivar_status(None, False, False) == "ATIVA"
