"""Testes do parser de flashcards (backend/parser.py)."""

from parser import parse_markdown


def test_parse_markdown_lowercase_markers():
    """Marcadores em minúsculo (flashcard:/frente:/verso:) devem ser reconhecidos."""
    text = """
flashcard:FUNDACOES PROFUNDAS:Estaca Strauss

frente:
Quais sao as caracteristicas da Estaca Strauss?

verso:
Resposta sobre a Strauss.

flashcard:FUNDACOES PROFUNDAS:Estaca Broca

frente:
Qual a carga maxima da Estaca Broca?

verso:
Resposta sobre a Broca.
"""
    cards = parse_markdown(text)

    assert len(cards) == 2
    assert cards[0]["tema"] == "FUNDACOES PROFUNDAS"
    assert cards[0]["assunto"] == "Estaca Strauss"
    assert "Strauss" in cards[0]["frente"]
    assert cards[1]["assunto"] == "Estaca Broca"


def test_parse_markdown_mixed_case_in_same_file():
    """Um arquivo pode misturar 'Flashcard:' e 'flashcard:' entre blocos."""
    text = """
Flashcard: Direito Civil: Posse

Frente: O que e posse?

Verso: Resposta sobre posse.

flashcard: Direito Civil: Propriedade

frente: O que e propriedade?

verso: Resposta sobre propriedade.
"""
    cards = parse_markdown(text)

    assert len(cards) == 2
    assert cards[0]["assunto"] == "Posse"
    assert cards[1]["assunto"] == "Propriedade"


def test_parse_markdown_bold_frente_verso_labels():
    """Marcadores 'frente:'/'verso:' envoltos em negrito (**frente:**) devem ser aceitos."""
    text = """
flashcard:GERENCIAMENTO DE PROJETOS:Dimensoes do BIM (3D ao 8D)

**frente:**
**Quais sao os conceitos agregados a cada dimensao do BIM?**

**verso:**
O BIM adiciona camadas de dados a geometria do projeto.
"""
    cards = parse_markdown(text)

    assert len(cards) == 1
    assert cards[0]["tema"] == "GERENCIAMENTO DE PROJETOS"
    assert "BIM" in cards[0]["frente"]
    assert "camadas de dados" in cards[0]["verso"]


def test_parse_markdown_parenthesized_tema_header():
    """Cabecalho '(Tema: X)' com parenteses nao pode virar tema '(Tema'."""
    text = """
Flashcard: (Tema: Geotecnia / Prova de Carga Direta - NBR 6489)

Frente: Pergunta sobre prova de carga?

Verso: Resposta sobre prova de carga.
"""
    cards = parse_markdown(text)

    assert len(cards) == 1
    assert cards[0]["tema"] == "Geotecnia / Prova de Carga Direta - NBR 6489"
    assert cards[0]["assunto"] == "Geotecnia / Prova de Carga Direta - NBR 6489"


def test_parse_markdown_bold_tema_label_in_header():
    """Cabecalho com negrito markdown e label literal 'Tema:' nao deve virar lixo."""
    text = """
Flashcard: **Tema: NBR 6122 / Controle de Cravacao**

Frente: Pergunta sobre cravacao?

Verso: Resposta sobre cravacao.
"""
    cards = parse_markdown(text)

    assert len(cards) == 1
    assert cards[0]["tema"] == "NBR 6122 / Controle de Cravacao"
    assert cards[0]["assunto"] == "NBR 6122 / Controle de Cravacao"
    assert "*" not in cards[0]["tema"]
