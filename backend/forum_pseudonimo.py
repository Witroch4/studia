"""Pseudônimo estável para autores importados do TC.

Mesmo autor (mesma `seed`) → sempre o mesmo nome fake, mantendo as threads
coerentes. Determinístico entre processos: usa hashlib (NUNCA hash() do Python,
que é salgado por processo).
"""

from __future__ import annotations

import hashlib

# Pool curado de nomes PT-BR (nome + sobrenome).
POOL: list[str] = [
    "Ana Ribeiro", "Bruno Carvalho", "Camila Nogueira", "Diego Fontes",
    "Elaine Macedo", "Felipe Andrade", "Gabriela Pires", "Henrique Bastos",
    "Isabela Moraes", "João Tavares", "Karina Lemos", "Lucas Barreto",
    "Mariana Cordeiro", "Natália Vasques", "Otávio Peixoto", "Patrícia Coelho",
    "Rafael Quintana", "Sabrina Dorneles", "Thiago Marinho", "Vanessa Aragão",
    "William Sarmento", "Yara Bittencourt", "André Vilela", "Beatriz Couto",
    "Caio Rezende", "Daniela Brito", "Eduardo Sales", "Fernanda Lira",
    "Gustavo Pacheco", "Helena Drummond", "Igor Sampaio", "Juliana Furtado",
]


def pseudonimo(seed: str) -> str:
    """Nome fake determinístico para `seed` (ex.: nome original do autor no TC)."""
    digest = hashlib.sha1((seed or "").encode("utf-8")).hexdigest()
    return POOL[int(digest, 16) % len(POOL)]
