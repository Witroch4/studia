"""[DEPRECATED] — orquestração antiga por posição.

Mantido apenas por compatibilidade com chamadas externas existentes. O
caminho oficial é `tc_imprimir.scrape_caderno_imprimir` que usa o endpoint
`/ajaxCarregarQuestoesImpressao` (200 questões por request, gabarito
completo, zero rate limit).

Veja README.md → "Caminho oficial: scrape imprimir".
"""

from __future__ import annotations

from app.observability import get_logger
from app.scrapers.tc_imprimir import scrape_caderno_imprimir

log = get_logger(__name__)


async def scrape_caderno(
    caderno_id: int,
    *,
    limite: int | None = None,
    total: int | None = None,
    state=None,
) -> dict[str, int]:
    """Shim para o caminho oficial (imprimir). `limite` redireciona pra page_size."""
    log.warning(
        "tecconcursos.scrape_caderno é deprecado; redirecionando para tc_imprimir.scrape_caderno_imprimir"
    )
    page_size = limite if (limite and limite < 200) else 200
    return await scrape_caderno_imprimir(
        caderno_id, total=total, page_size=page_size, state=state
    )


async def scrape_ids(ids, *, caderno_id=None, state=None):
    raise NotImplementedError(
        "API TC indexa por posição, não por ID. Use `scrape_caderno_imprimir` "
        "(endpoint /ajaxCarregarQuestoesImpressao)."
    )
