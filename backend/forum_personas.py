"""Personas de cientistas famosos para os posts do admin no fórum dos professores.

Quando o admin (dono) escreve no quadro `professores`, sorteamos um nome deste
pool e gravamos em `questao_comentarios.persona_nome` — dando a sensação de
vários professores renomados respondendo. A persona fica fixa naquele comentário.
"""

import random

POOL: list[str] = [
    "Albert Einstein", "Isaac Newton", "Niels Bohr", "Gottfried Leibniz",
    "J. Robert Oppenheimer", "Werner Heisenberg", "Ernest Rutherford",
    "Marie Curie", "Galileu Galilei", "Nikola Tesla", "Richard Feynman",
    "Max Planck", "Erwin Schrödinger", "Paul Dirac", "Michael Faraday",
]


def sortear_persona(excluir: set[str] | None = None) -> str:
    """Sorteia um cientista do pool, evitando os de `excluir` quando possível.

    Se todos estiverem excluídos, ignora a exclusão (fallback) — sempre retorna
    um nome válido do pool.
    """
    disponiveis = [n for n in POOL if not excluir or n not in excluir]
    if not disponiveis:
        disponiveis = POOL
    return random.choice(disponiveis)
