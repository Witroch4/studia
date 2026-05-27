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


def parse_markdown(text: str) -> list[FlashcardData]:
    """Parseia texto markdown e retorna lista de flashcards."""
    # Divide em blocos por "Flashcard:"
    # Usa lookahead para não consumir o delimitador
    blocks = re.split(r"(?=^Flashcard:)", text.strip(), flags=re.MULTILINE)
    blocks = [b.strip() for b in blocks if b.strip()]

    cards: list[FlashcardData] = []

    for block in blocks:
        card = _parse_block(block)
        if card:
            cards.append(card)

    return cards


def _parse_block(block: str) -> FlashcardData | None:
    """Parseia um bloco individual de flashcard."""
    # Extrai header: "Flashcard: Tema: Assunto"
    header_match = re.match(r"^Flashcard:\s*(.+)", block, re.MULTILINE)
    if not header_match:
        return None

    header = header_match.group(1).strip()
    parts = header.split(":", 1)
    tema = parts[0].strip()
    assunto = parts[1].strip() if len(parts) > 1 else tema

    # Extrai frente: tudo entre "Frente:" e "Verso:"
    frente_match = re.search(
        r"^Frente:\s*(.+?)(?=^Verso:)", block, re.MULTILINE | re.DOTALL
    )
    frente = frente_match.group(1).strip() if frente_match else ""

    # Extrai verso: tudo após "Verso:"
    verso_match = re.search(r"^Verso:\s*(.+)", block, re.MULTILINE | re.DOTALL)
    verso = verso_match.group(1).strip() if verso_match else ""

    if not frente and not verso:
        return None

    return FlashcardData(tema=tema, assunto=assunto, frente=frente, verso=verso)
