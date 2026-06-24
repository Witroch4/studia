"""Scraper do gabarito/desempenho do usuário num caderno TC.

Endpoint: ``GET /api/cadernos/{cid}/gabarito?pagina=N`` — 30 itens por página
(tamanho fixo; params de tamanho são ignorados). A resposta traz ``totalPages``
e ``resultCount`` para paginar até o fim.

Cada item (por questão do caderno)::

    {"posicaoCaderno":1, "idQuestao":3643888, "alternativa":1, "acertou":true,
     "data":"24/05/2026 00:00:00", "tipoQuestao":"MULTIPLA_ESCOLHA",
     "anulada":false, "favorita":false, "anotada":false}

- ``idQuestao``  → casa com ``Questao.id_externo`` no studIA.
- ``alternativa`` 1-5 → A-E (em CERTO_ERRADO: 1=Certo, 2=Errado).
- ``acertou`` bool; **ausente** (sem ``alternativa``/``data``) = "não resolvida".
- ``data`` "DD/MM/AAAA HH:MM:SS" → quando o usuário respondeu.

Diferente da coleta de questões, isto é desempenho — depende da sessão do
usuário logado (a conta TC do scraper).
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.client import TcClient
from app.observability import get_logger

log = get_logger(__name__)

MAX_PAGINAS = 2000  # trava de segurança (60k questões); cadernos reais são bem menores
# Espaçamento fixo entre páginas. O gabarito é uma leitura leve (o próprio SPA do
# TC pagina rápido ao clicar "próxima") — não usamos o "human mode" do TcClient
# (pausas de 3-120s), que tornaria ~30 páginas síncronas inviáveis. Sequencial e
# educado, sem rajada.
DELAY_ENTRE_PAGINAS_S = 1.2


async def fetch_gabarito(client: TcClient, caderno_id: int) -> dict[str, Any]:
    """Pagina o gabarito inteiro do caderno e devolve a lista agregada."""
    referer = f"https://www.tecconcursos.com.br/questoes/cadernos/{caderno_id}"
    base = f"/api/cadernos/{caderno_id}/gabarito"

    itens: list[dict[str, Any]] = []
    pagina = 1
    total_pages = 1
    result_count = 0

    while pagina <= MAX_PAGINAS:
        if pagina > 1:
            await asyncio.sleep(DELAY_ENTRE_PAGINAS_S)
        # Caminho leve: httpx cru + _check (classifica 401/302→login p/ relogin
        # automático via _with_tc_client), sem o throttle de coleta.
        r = await client._client.get(
            f"{base}?pagina={pagina}", headers=client._build_headers(referer, None)
        )
        client._check(r)
        data = r.json()
        lista = data.get("list") or []
        itens.extend(lista)
        try:
            total_pages = int(data.get("totalPages") or 1)
        except (TypeError, ValueError):
            total_pages = pagina
        try:
            result_count = int(data.get("resultCount") or len(itens))
        except (TypeError, ValueError):
            result_count = len(itens)

        if pagina >= total_pages or not lista:
            break
        pagina += 1

    log.info(
        "tc.gabarito.fetched",
        caderno_id=caderno_id,
        paginas=pagina,
        itens=len(itens),
        result_count=result_count,
    )
    return {"caderno_id": caderno_id, "total": result_count, "itens": itens}
