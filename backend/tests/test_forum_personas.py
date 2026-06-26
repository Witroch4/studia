from forum_personas import POOL, sortear_persona


def test_pool_tem_15_nomes_unicos():
    assert len(POOL) == 15
    assert len(set(POOL)) == 15
    assert "Albert Einstein" in POOL
    assert "Isaac Newton" in POOL


def test_sortear_retorna_do_pool():
    for _ in range(50):
        assert sortear_persona() in POOL


def test_sortear_respeita_excluir():
    excluir = set(POOL[:14])  # sobra 1
    for _ in range(20):
        assert sortear_persona(excluir) == POOL[14]


def test_sortear_fallback_quando_todos_excluidos():
    # Se todos estão excluídos, ignora a exclusão e ainda retorna do pool.
    assert sortear_persona(set(POOL)) in POOL
