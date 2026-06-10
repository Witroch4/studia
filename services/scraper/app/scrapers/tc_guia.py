"""Resolução e leitura de Guias de estudo do TecConcursos.

Fluxo (descoberto via intercept Playwright, ver memória `tc-guia-pasta-api`):

1. `GET /guias/{slug}` (HTML base) — pode não ter `jsonGuiaId`; tem o link
   `/guias/{slug}/{cargo}/-/-` para a página de cargo.
2. `GET /guias/{slug}/{cargo}/-/-` (HTML) — contém `var jsonGuiaId = "6818"`.
3. `GET /api/caderno-guia/listar-pelo-guia/{guiaId}` → cadernos-guia.
4. `POST /api/caderno-guia/salvar-todos-cadernos-do-guia/{guiaId}` →
   `{pastaCadernosQuestoes:{id}}`.
5. `GET /api/pastas-cadernos/{pastaId}/itens?ordenacao=nome&pagina=N&paginar=true`.

Todas as chamadas reusam a sessão httpx autenticada (`TcClient`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger

log = get_logger(__name__)

_GUIA_ID_RE = re.compile(r"var\s+jsonGuiaId\s*=\s*\"?(\d+)\"?")
_GUIA_HREF_RE = re.compile(r'href="((?:https?://[^"]+)?/guias/[^"]+/-/-)"')
_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.S)
_BANCA_RE = re.compile(r"(FGV|CESPE|CEBRASPE|FCC|VUNESP|QUADRIX|IBFC|FUNDATEC|CONSULPLAN|IDECAN|INSTITUTO\s+\w+)", re.I)


class GuiaResolveError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CadernoGuia:
    tc_caderno_id: int          # cadernoQuestaoRecenteId (id do caderno de questões)
    caderno_base_id: int | None
    nome: str
    total_questoes: int
    total_capitulos: int
    ordem: int | None
    usuario_possui_salvo: bool


@dataclass(frozen=True, slots=True)
class GuiaResolvido:
    tc_guia_id: int
    slug: str
    url: str
    nome: str
    banca: str | None
    cadernos: list[CadernoGuia]


def _normalize_guia_url(url_or_slug: str) -> str:
    base = get_settings().tc_base.rstrip("/")
    s = (url_or_slug or "").strip()
    if not s:
        raise GuiaResolveError("URL/slug do guia vazio")
    if s.startswith("http"):
        return s
    return f"{base}/guias/{s.lstrip('/').removeprefix('guias/')}"


async def _get_html(client: TcClient, url: str) -> str:
    path = url.replace(get_settings().tc_base.rstrip("/"), "") or "/"
    r = await client._client.get(  # noqa: SLF001
        path, headers={"Accept": "text/html,application/xhtml+xml"}
    )
    client._check(r)  # noqa: SLF001
    r.raise_for_status()
    return r.text


def _extract_slug(url: str) -> str:
    m = re.search(r"/guias/([^?#]+)", url)
    slug = m.group(1).strip("/") if m else url
    # normaliza "oab-2026/nacional-unificado-oab/-/-" -> "oab-2026/nacional-unificado-oab"
    return re.sub(r"/-/-$", "", slug)


async def resolver_guia(client: TcClient, url_or_slug: str) -> GuiaResolvido:
    """Resolve a URL base (ou de cargo) do guia em `GuiaResolvido` completo."""
    url = _normalize_guia_url(url_or_slug)
    html = await _get_html(client, url)

    guia_id_match = _GUIA_ID_RE.search(html)
    if not guia_id_match:
        # É a página base do guia — segue o link de cargo.
        href = _GUIA_HREF_RE.search(html)
        if not href:
            raise GuiaResolveError(
                f"jsonGuiaId não encontrado e nenhum link de cargo em {url}"
            )
        url = _normalize_guia_url(href.group(1))
        html = await _get_html(client, url)
        guia_id_match = _GUIA_ID_RE.search(html)
        if not guia_id_match:
            raise GuiaResolveError(f"jsonGuiaId não encontrado em {url}")

    tc_guia_id = int(guia_id_match.group(1))
    title = _TITLE_RE.search(html)
    nome = (title.group(1) if title else f"Guia {tc_guia_id}").strip()
    banca_match = _BANCA_RE.search(html)
    banca = banca_match.group(1).upper() if banca_match else None

    cadernos = await listar_cadernos_guia(client, tc_guia_id)
    log.info(
        "tc_guia.resolved",
        tc_guia_id=tc_guia_id,
        nome=nome,
        banca=banca,
        cadernos=len(cadernos),
    )
    return GuiaResolvido(
        tc_guia_id=tc_guia_id,
        slug=_extract_slug(url),
        url=url,
        nome=nome,
        banca=banca,
        cadernos=cadernos,
    )


async def listar_cadernos_guia(client: TcClient, tc_guia_id: int) -> list[CadernoGuia]:
    r = await client._client.get(  # noqa: SLF001
        f"/api/caderno-guia/listar-pelo-guia/{tc_guia_id}",
        headers={"Accept": "application/json, text/plain, */*"},
    )
    client._check(r)  # noqa: SLF001
    r.raise_for_status()
    data = r.json()
    cadernos: list[CadernoGuia] = []
    for item in data.get("cadernosGuia", []):
        tc_caderno_id = item.get("cadernoQuestaoRecenteId")
        if not tc_caderno_id:
            # caderno-guia ainda não entregue (sem caderno de questões) — pula
            continue
        cadernos.append(
            CadernoGuia(
                tc_caderno_id=int(tc_caderno_id),
                caderno_base_id=item.get("cadernoBaseId"),
                nome=str(item.get("disciplina") or f"Caderno {tc_caderno_id}"),
                total_questoes=int(item.get("totalQuestoes") or 0),
                total_capitulos=int(item.get("totalCapitulos") or 0),
                ordem=item.get("ordem"),
                usuario_possui_salvo=bool(item.get("usuarioPossuiCadernoSalvo")),
            )
        )
    return cadernos


async def salvar_todos_cadernos(client: TcClient, tc_guia_id: int) -> int | None:
    """Dispara 'Salvar todos os cadernos do guia'. Retorna o pastaId, se houver.

    Idempotente: se já estavam salvos, o TC apenas confirma.
    """
    r = await client._client.post(  # noqa: SLF001
        f"/api/caderno-guia/salvar-todos-cadernos-do-guia/{tc_guia_id}",
        headers={"Accept": "application/json, text/plain, */*"},
    )
    client._check(r)  # noqa: SLF001
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return None
    pasta = data.get("pastaCadernosQuestoes") if isinstance(data, dict) else None
    pasta_id = pasta.get("id") if isinstance(pasta, dict) else None
    log.info("tc_guia.salvar_todos", tc_guia_id=tc_guia_id, pasta_id=pasta_id)
    return int(pasta_id) if pasta_id else None


async def buscar_guias(client: TcClient, termo: str, *, max_paginas: int = 10) -> list[dict[str, Any]]:
    """Busca guias por palavra-chave via `/api/guias/busca`.

    Retorna `[{tc_edital_id, slug, ano, orgao, banca, data_prova}]`.
    """
    base = get_settings().tc_base.rstrip("/")
    resultados: list[dict[str, Any]] = []
    pagina = 1
    while pagina <= max_paginas:
        r = await client._client.get(  # noqa: SLF001
            "/api/guias/busca",
            params={"busca": termo, "pagina": pagina},
            headers={"Accept": "application/json, text/plain, */*"},
        )
        client._check(r)  # noqa: SLF001
        r.raise_for_status()
        data = r.json()
        page_list = data.get("list", []) if isinstance(data, dict) else []
        if not page_list:
            break
        for item in page_list:
            slug = item.get("editalUrl")
            if not slug:
                continue
            resultados.append(
                {
                    "tc_edital_id": item.get("editalId"),
                    "slug": slug,
                    "url": f"{base}/guias/{slug}",
                    "ano": item.get("editalAno"),
                    "orgao": item.get("orgaoSigla"),
                    "banca": item.get("bancaSigla"),
                    "data_prova": item.get("menorDataProva"),
                    "qtd_cargos": item.get("quantidadeCargos"),
                }
            )
        total_paginas = data.get("totalPages") if isinstance(data, dict) else None
        if total_paginas and pagina >= int(total_paginas):
            break
        pagina += 1
    return resultados


async def listar_itens_pasta(client: TcClient, pasta_id: int) -> list[dict[str, Any]]:
    """Lista todos os itens (cadernos) de uma pasta, paginando."""
    itens: list[dict[str, Any]] = []
    pagina = 1
    while True:
        r = await client._client.get(  # noqa: SLF001
            f"/api/pastas-cadernos/{pasta_id}/itens",
            params={"ordenacao": "nome", "pagina": pagina, "paginar": "true"},
            headers={"Accept": "application/json, text/plain, */*"},
        )
        client._check(r)  # noqa: SLF001
        r.raise_for_status()
        data = r.json()
        page_itens = data.get("itens", []) if isinstance(data, dict) else []
        if not page_itens:
            break
        itens.extend(page_itens)
        if len(page_itens) < 20:  # página padrão do TC
            break
        pagina += 1
        if pagina > 50:  # guarda contra loop
            break
    return itens
