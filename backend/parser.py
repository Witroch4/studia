"""
Parser de flashcards a partir de markdown.

Formato esperado:
    Flashcard: Tema: Assunto
    Frente: conteúdo da pergunta
    Verso:
    conteúdo da resposta (markdown + LaTeX + tags XML)

Tags XML suportadas (passadas raw para o frontend renderizar):
    <atencao>texto</atencao>
    <destaque>texto</destaque>
    <resumo>texto</resumo>
"""

import re
from typing import TypedDict


class FlashcardData(TypedDict):
    tema: str
    assunto: str
    frente: str
    verso: str


_BLOCK_FLAGS = re.MULTILINE | re.IGNORECASE


def parse_markdown(text: str) -> list[FlashcardData]:
    """Parseia texto markdown e retorna lista de flashcards."""
    # Divide em blocos por "Flashcard:" (case-insensitive: "flashcard:" também vale)
    # Usa lookahead para não consumir o delimitador
    blocks = re.split(r"(?=^flashcard:)", text.strip(), flags=_BLOCK_FLAGS)
    blocks = [b.strip() for b in blocks if b.strip()]

    cards: list[FlashcardData] = []

    for block in blocks:
        card = _parse_block(block)
        if card:
            cards.append(card)

    return cards


def _strip_markdown_emphasis(value: str) -> str:
    """Remove `**negrito**`/`*itálico*` que envolve o valor inteiro."""
    return value.strip().strip("*").strip()


def _parse_block(block: str) -> FlashcardData | None:
    """Parseia um bloco individual de flashcard."""
    # Extrai header: "Flashcard: Tema: Assunto" (case-insensitive)
    header_match = re.match(r"^flashcard:\s*(.+)", block, _BLOCK_FLAGS)
    if not header_match:
        return None

    header = _strip_markdown_emphasis(header_match.group(1))
    # Tolera label literal "Tema:" dentro do cabeçalho, ex.: "**Tema: Assunto**"
    header = re.sub(r"(?i)^tema:\s*", "", header).strip()

    parts = header.split(":", 1)
    tema = _strip_markdown_emphasis(parts[0])
    assunto = _strip_markdown_emphasis(parts[1]) if len(parts) > 1 else tema

    # Extrai frente: tudo entre "Frente:" e "Verso:" (case-insensitive)
    frente_match = re.search(
        r"^frente:\s*(.+?)(?=^verso:)", block, _BLOCK_FLAGS | re.DOTALL
    )
    frente = frente_match.group(1).strip() if frente_match else ""

    # Extrai verso: tudo após "Verso:" (case-insensitive)
    verso_match = re.search(r"^verso:\s*(.+)", block, _BLOCK_FLAGS | re.DOTALL)
    verso = verso_match.group(1).strip() if verso_match else ""

    if not frente and not verso:
        return None

    return FlashcardData(tema=tema, assunto=assunto, frente=frente, verso=verso)
