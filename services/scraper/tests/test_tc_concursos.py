from app.scrapers.tc_concursos import filtros_external_id, parse_busca_page

PAGE = {
    "resultCount": 49, "currentPage": 1, "pageSize": 5, "totalPages": 10,
    "list": [
        {
            "edital": {
                "id": 19626, "nome": "Nº 01/2026, DE 21 DE MAIO DE 2026",
                "ano": 2026, "orgaoNome": "Assembleia Legislativa do Ceará",
                "orgaoSigla": "ALECE", "orgaoRegiao": "Estadual",
                "bancaSigla": "IDECAN",
                "bancaNome": "Instituto de Desenvolvimento Educacional...",
            },
            "concursos": [
                {
                    "concursoId": 174930, "editalId": 19626,
                    "dataAplicacao": "16/08/2026 00:00:00",
                    "escolaridade": "Superior", "bancaNome": "IDECAN",
                    "editalNome": "Nº 01/2026, DE 21 DE MAIO DE 2026",
                    "orgaoSigla": "ALECE",
                    "nomeCompleto": "Analista Legislativo (ALECE)/2026 - Engenharia - Civil",
                    "arquivosPorTipo": {
                        "EDITAL": [{"id": 452178, "nomeArquivo": "1.edital.pdf",
                                    "uuid": "af4483d1-650a-4d18-ac99-785cf983d926"}],
                        "PROVA_OBJETIVA": [{"id": 1, "nomeArquivo": "prova.pdf", "uuid": "u-prova"}],
                    },
                    "urlConcurso": "analista-legislativo-alece-engenharia-civil-2026",
                },
                # mesmo edital, segundo cargo SEM arquivos
                {"concursoId": 174931, "editalId": 19626, "nomeCompleto": "Outro cargo",
                 "urlConcurso": "outro-cargo-2026", "arquivosPorTipo": {}},
            ],
        }
    ],
}


def test_parse_busca_page_achata_concursos():
    units = parse_busca_page(PAGE)
    assert [u["concurso_id"] for u in units] == [174930, 174931]
    c = units[0]["payload"]["concurso"]
    assert c["nome_completo"].startswith("Analista Legislativo")
    assert c["url_concurso"] == "analista-legislativo-alece-engenharia-civil-2026"
    assert c["ano"] == 2026 and c["orgao_nome"].startswith("Assembleia")
    arqs = units[0]["payload"]["arquivos"]
    assert {a["tipo"] for a in arqs} == {"EDITAL", "PROVA_OBJETIVA"}
    assert arqs[0]["uuid"] and arqs[0]["arquivo_id_externo"] and arqs[0]["nome_arquivo"]
    assert units[1]["payload"]["arquivos"] == []  # concurso sem arquivo é válido


def test_external_id_canonico_e_estavel():
    a = filtros_external_id([{"id": "6", "tipo": "PROFISSAO"}, {"id": "95", "tipo": "BANCA"}])
    b = filtros_external_id([{"id": 95, "tipo": "BANCA"}, {"id": 6, "tipo": "PROFISSAO"}])
    assert a == b == "BANCA:95|PROFISSAO:6"


def test_normalizar_itens_filtro_shape_ui():
    from app.scrapers.tc_concursos import _normalizar_itens_filtro

    bancas_raw = {"bancas": [
        {"id": 95, "nome": "Instituto de Desenvolvimento Educacional", "sigla": "IDECAN"},
        {"id": 1, "nome": "Sem Sigla"},
        {"id": None, "nome": "invalida"},
        "lixo",
    ]}
    out = _normalizar_itens_filtro(bancas_raw, "bancas")
    assert out[0] == {"key": "95", "name": "IDECAN — Instituto de Desenvolvimento Educacional"}
    assert out[1] == {"key": "1", "name": "Sem Sigla"}
    assert len(out) == 2  # id None e não-dict descartados

    profs_raw = {"profissoes": [{"id": 6, "nome": "Engenharia Civil"}]}
    assert _normalizar_itens_filtro(profs_raw, "profissoes") == [
        {"key": "6", "name": "Engenharia Civil"}
    ]
    # lista crua (sem wrapper) também funciona
    assert _normalizar_itens_filtro([{"id": 2, "nome": "X"}], "bancas") == [{"key": "2", "name": "X"}]
