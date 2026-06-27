"""Disjunctive faceting em /api/q/count: cada grupo conta ignorando os filtros
do próprio grupo (mantendo tipo/status_excluir/favoritas/q globais).

Testa a função pura `_build_count_queries` — sem Meili nem DB.
"""

from q_router import FACET_GROUPS, MEILI_INDEX, _build_count_queries, _to_meili_filter


def _grupo(queries, facets):
    """Retorna a sub-query cujo `facets` é exatamente `facets`."""
    return next(q for q in queries if q.get("facets") == facets)


def test_uma_query_base_mais_uma_por_grupo():
    queries = _build_count_queries({"tipo": ["MULTIPLA_ESCOLHA"]}, q="", fav_filter=None)
    assert len(queries) == 1 + len(FACET_GROUPS)
    base = queries[0]
    assert "facets" not in base  # base não pede facetas; só serve ao total


def test_base_mantem_todos_os_filtros():
    filtros = {
        "assuntos": ["Crase"],
        "banca": ["CESGRANRIO"],
        "tipo": ["MULTIPLA_ESCOLHA"],
        "status_excluir": ["ANULADA"],
    }
    base = _build_count_queries(filtros, q="", fav_filter=None)[0]
    assert 'assuntos = "Crase"' in base["filter"]
    assert 'banca = "CESGRANRIO"' in base["filter"]
    assert 'tipo = "MULTIPLA_ESCOLHA"' in base["filter"]
    assert 'status != "ANULADA"' in base["filter"]


def test_grupo_materia_assunto_omite_materia_e_assuntos_mantendo_resto():
    filtros = {
        "assuntos": ["Crase"],
        "materia": ["Língua Portuguesa (Português)"],
        "banca": ["CESGRANRIO"],
        "tipo": ["MULTIPLA_ESCOLHA"],
    }
    queries = _build_count_queries(filtros, q="", fav_filter=None)
    g = _grupo(queries, ["materia", "assuntos"])
    # o próprio grupo sai do filtro (é o que conserta o "tudo zera ao marcar")
    assert "assuntos =" not in g["filter"]
    assert "materia =" not in g["filter"]
    # filtros de OUTROS grupos / globais permanecem
    assert 'banca = "CESGRANRIO"' in g["filter"]
    assert 'tipo = "MULTIPLA_ESCOLHA"' in g["filter"]


def test_grupo_banca_omite_banca_mas_mantem_assuntos():
    filtros = {"assuntos": ["Crase"], "banca": ["CESGRANRIO"]}
    g = _grupo(_build_count_queries(filtros, q="", fav_filter=None), ["banca"])
    assert "banca =" not in g["filter"]
    assert 'assuntos = "Crase"' in g["filter"]


def test_grupo_orgao_cargo_omite_ambos():
    filtros = {"orgao": ["TJ"], "cargo": ["Analista"], "ano": [2024]}
    g = _grupo(_build_count_queries(filtros, q="", fav_filter=None), ["orgao", "cargo"])
    assert "orgao =" not in g["filter"]
    assert "cargo =" not in g["filter"]
    assert "ano = 2024" in g["filter"]  # outro grupo permanece


def test_escapa_aspas_no_nome_do_assunto():
    # Nomes como `Vocábulo "Como"` quebravam a query (Meili 400) por aspas não
    # escapadas → todo o /count caía pra 0. Devem virar \" dentro da string.
    f = _to_meili_filter({"assuntos": ['Vocábulo "Como"']})
    assert f == '(assuntos = "Vocábulo \\"Como\\"")'


def test_escapa_barra_invertida():
    f = _to_meili_filter({"banca": ["A\\B"]})
    assert f == '(banca = "A\\\\B")'


def test_valor_sem_aspas_inalterado():
    assert _to_meili_filter({"banca": ["CESGRANRIO"]}) == '(banca = "CESGRANRIO")'


def test_favoritas_e_q_e_index_sao_globais_em_todas_as_queries():
    queries = _build_count_queries(
        {"banca": ["CESGRANRIO"]}, q="contrato", fav_filter="id IN [1, 2]"
    )
    for qy in queries:
        assert qy["q"] == "contrato"
        assert qy["indexUid"] == MEILI_INDEX
        assert qy["limit"] == 0
        assert "id IN [1, 2]" in qy["filter"]  # favoritas nunca é dropado
