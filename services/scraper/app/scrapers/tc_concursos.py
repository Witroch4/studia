"""Busca avançada de concursos do TC + arquivos p/ download.

Contrato validado em 2026-07-02 (ver spec 2026-07-02-coleta-concursos-tc-design.md).
A busca exige sessão TC + headers XHR/Logado; o download dos arquivos é público
(cdn.tecconcursos.com.br/arquivos/{uuid}) e NÃO consome sessão.

`TcClient.get` só aceita `referer=` (sem `params=`/`headers=` arbitrários — ver
`app/client.py`), então aqui usamos `client._client.get(...)` cru + `client._check`,
igual `tc_gabarito.py`/`tc_guia.py`.
"""
from __future__ import annotations

from typing import Any

from app.client import TcClient

BUSCA_PATH = "/api/concursos/busca-avancada"
XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "Logado": "true",
    "Referer": "https://www.tecconcursos.com.br/concursos?tipoBusca=buscaavancada",
}
CDN_ARQUIVO_URL = "https://cdn.tecconcursos.com.br/arquivos/{uuid}"


def filtros_external_id(filtros: list[dict]) -> str:
    partes = sorted(f"{f['tipo'].upper()}:{f['id']}" for f in filtros)
    return "|".join(partes)


def _params_busca(filtros: list[dict], pagina: int) -> dict[str, str]:
    params: dict[str, str] = {}
    for i, f in enumerate(filtros):
        params[f"busca.geradorBuscaConcursoFiltros[{i}].id"] = str(f["id"])
        params[f"busca.geradorBuscaConcursoFiltros[{i}].tipo"] = str(f["tipo"]).upper()
    params["busca.pagina"] = str(pagina)
    return params


async def fetch_busca_avancada(client: TcClient, filtros: list[dict], pagina: int) -> dict[str, Any]:
    r = await client._client.get(  # noqa: SLF001
        BUSCA_PATH, params=_params_busca(filtros, pagina), headers=XHR_HEADERS
    )
    client._check(r)  # noqa: SLF001
    r.raise_for_status()
    return r.json()


def _normalizar_itens_filtro(raw: Any, inner_key: str) -> list[dict[str, str]]:
    """TC devolve {"bancas": [{id, nome, sigla, ...}]} / {"profissoes": [{id, nome}]}.
    A UI consome [{key, name}] — key = id (string), name pesquisável (sigla — nome)."""
    itens = raw.get(inner_key, raw) if isinstance(raw, dict) else raw
    out: list[dict[str, str]] = []
    for it in itens or []:
        if not isinstance(it, dict) or it.get("id") is None:
            continue
        nome = str(it.get("nome") or "").strip()
        sigla = str(it.get("sigla") or "").strip()
        name = f"{sigla} — {nome}" if sigla and nome and sigla.lower() != nome.lower() else (sigla or nome)
        if not name:
            continue
        out.append({"key": str(it["id"]), "name": name})
    return out


async def fetch_filtros_busca(client: TcClient) -> dict[str, Any]:
    r_bancas = await client._client.get(f"{BUSCA_PATH}/bancas", headers=XHR_HEADERS)  # noqa: SLF001
    client._check(r_bancas)  # noqa: SLF001
    r_bancas.raise_for_status()
    r_profissoes = await client._client.get(f"{BUSCA_PATH}/profissoes", headers=XHR_HEADERS)  # noqa: SLF001
    client._check(r_profissoes)  # noqa: SLF001
    r_profissoes.raise_for_status()
    return {
        "bancas": _normalizar_itens_filtro(r_bancas.json(), "bancas"),
        "profissoes": _normalizar_itens_filtro(r_profissoes.json(), "profissoes"),
    }


def parse_busca_page(data: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for item in data.get("list") or []:
        edital = item.get("edital") or {}
        for c in item.get("concursos") or []:
            arquivos = [
                {
                    "tipo": tipo,
                    "arquivo_id_externo": a["id"],
                    "uuid": a["uuid"],
                    "nome_arquivo": a.get("nomeArquivo") or a["uuid"],
                }
                for tipo, lst in (c.get("arquivosPorTipo") or {}).items()
                for a in (lst or [])
            ]
            units.append(
                {
                    "concurso_id": int(c["concursoId"]),
                    "payload": {
                        "concurso": {
                            "concurso_id_externo": int(c["concursoId"]),
                            "edital_id_externo": c.get("editalId") or edital.get("id"),
                            "nome_completo": c.get("nomeCompleto") or "",
                            "url_concurso": c.get("urlConcurso") or "",
                            "banca_nome": c.get("bancaNome") or edital.get("bancaSigla") or "",
                            "orgao_sigla": c.get("orgaoSigla") or edital.get("orgaoSigla") or "",
                            "orgao_nome": edital.get("orgaoNome") or "",
                            "edital_nome": c.get("editalNome") or edital.get("nome") or "",
                            "ano": edital.get("ano"),
                            "data_aplicacao": c.get("dataAplicacao"),
                            "escolaridade": c.get("escolaridade"),
                        },
                        "arquivos": arquivos,
                    },
                }
            )
    return units
