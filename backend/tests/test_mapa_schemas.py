"""Validação do JSON de extração do edital (shape tolerante a campos ausentes)."""
from mapa_schemas import EditalExtraido

FIXTURE = {
    "concurso": {"orgao": "Prefeitura X", "banca": "IDECAN",
                 "taxa_inscricao": "R$ 120,00", "data_prova": "2026-09-20"},
    "eventos": [
        {"titulo": "Inscrições", "data_inicio": "2026-07-01",
         "data_fim": "2026-07-30", "tipo": "inscricao"},
        {"titulo": "Prova objetiva", "data_inicio": "2026-09-20", "tipo": "prova"},
    ],
    "cargos": [
        {"nome": "Engenheiro Civil", "escolaridade": "Superior",
         "vagas": "2 + CR", "salario": "R$ 6.500,00",
         "conteudo_programatico": [
             {"materia": "Língua Portuguesa", "assuntos": ["Interpretação de texto", "Crase"]},
             {"materia": "Engenharia Civil", "assuntos": ["Fundações", "Concreto armado"]},
         ],
         "etapas": [{"nome": "Prova objetiva", "carater": "eliminatorio"}],
         "distribuicao_questoes": [{"materia": "Língua Portuguesa", "quantidade": 10, "peso": 1.0}]},
    ],
}


def test_parse_fixture_completa():
    ext = EditalExtraido.model_validate(FIXTURE)
    assert ext.concurso.data_prova == "2026-09-20"
    assert len(ext.eventos) == 2
    assert ext.eventos[1].data_fim is None
    assert ext.cargos[0].nome == "Engenheiro Civil"
    assert ext.cargos[0].conteudo_programatico[1].assuntos == ["Fundações", "Concreto armado"]
    # roundtrip JSON-safe (vai para coluna JSON)
    assert ext.model_dump(mode="json")["cargos"][0]["vagas"] == "2 + CR"


def test_parse_vazio_nao_quebra():
    ext = EditalExtraido.model_validate({})
    assert ext.concurso.data_prova is None
    assert ext.eventos == [] and ext.cargos == []


def test_tipo_evento_desconhecido_vira_outro():
    ext = EditalExtraido.model_validate(
        {"eventos": [{"titulo": "X", "tipo": "PROVA OBJETIVA!!"}]}
    )
    assert ext.eventos[0].tipo == "outro"


def test_data_invalida_vira_none():
    ext = EditalExtraido.model_validate(
        {"eventos": [{"titulo": "X", "data_inicio": "20/09/2026", "tipo": "prova"}]}
    )
    assert ext.eventos[0].data_inicio is None


def test_null_em_campo_str_nao_levanta():
    # IA devolve null onde se espera string: nunca ValidationError.
    ext = EditalExtraido.model_validate(
        {
            "concurso": {"orgao": None, "banca": None, "taxa_inscricao": None},
            "eventos": [{"titulo": None}],
            "cargos": [
                {"nome": None, "escolaridade": None, "vagas": None,
                 "salario": None, "requisitos": None, "jornada": None,
                 "conteudo_programatico": [{"materia": None, "assuntos": None}],
                 "etapas": [{"nome": None, "carater": None}],
                 "distribuicao_questoes": [{"materia": None}]},
            ],
        }
    )
    assert ext.concurso.orgao is None
    assert ext.eventos[0].titulo == ""  # obrigatório-com-default: null vira ""
    assert ext.cargos[0].nome == ""
    assert ext.cargos[0].vagas is None
    assert ext.cargos[0].conteudo_programatico[0].materia == ""
    assert ext.cargos[0].conteudo_programatico[0].assuntos == []  # não-lista vira []
    assert ext.cargos[0].etapas[0].carater is None


def test_numero_em_campo_str_vira_string():
    # IA devolve número onde se espera string: coage com str(), não levanta.
    ext = EditalExtraido.model_validate(
        {
            "concurso": {"taxa_inscricao": 120.0},
            "cargos": [{"nome": 42, "vagas": 2, "salario": 6500.0,
                        "conteudo_programatico": [
                            {"materia": "X", "assuntos": ["ok", 123]}]}],
        }
    )
    assert ext.concurso.taxa_inscricao == "120.0"
    assert ext.cargos[0].nome == "42"
    assert ext.cargos[0].vagas == "2"
    assert ext.cargos[0].salario == "6500.0"
    # item não-string em assuntos vira str
    assert ext.cargos[0].conteudo_programatico[0].assuntos == ["ok", "123"]


def test_numero_invalido_em_quantidade_peso_vira_none():
    ext = EditalExtraido.model_validate(
        {"cargos": [{"nome": "X", "distribuicao_questoes": [
            {"materia": "LP", "quantidade": "dez", "peso": "x"},
            {"materia": "Mat", "quantidade": "15", "peso": "2.5"},
        ]}]}
    )
    dq = ext.cargos[0].distribuicao_questoes
    assert dq[0].quantidade is None and dq[0].peso is None
    # string numérica ainda converte
    assert dq[1].quantidade == 15 and dq[1].peso == 2.5
