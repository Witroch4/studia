from forum_pseudonimo import pseudonimo, POOL


def test_pseudonimo_e_estavel_para_o_mesmo_seed():
    assert pseudonimo("João da Silva") == pseudonimo("João da Silva")


def test_pseudonimo_vem_do_pool():
    assert pseudonimo("qualquer-autor") in POOL


def test_seeds_diferentes_tendem_a_nomes_diferentes():
    nomes = {pseudonimo(f"autor-{i}") for i in range(20)}
    assert len(nomes) > 1  # não colapsa tudo num nome só


def test_seed_vazio_nao_quebra():
    assert pseudonimo("") in POOL
