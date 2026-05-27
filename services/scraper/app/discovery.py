"""Modo discovery: bate endpoints suspeitos e dumpa raw JSON para inspeção.

Use antes de apertar os schemas. Captura uma amostra real do payload da
TecConcursos para que `schemas.py` e `persistir.py` reflitam a estrutura
verdadeira.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger

log = get_logger(__name__)


def _save(name: str, payload: dict | list) -> Path:
    out = get_settings().discovery_dump_dir
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("discovery.saved", file=str(path), bytes=path.stat().st_size)
    return path


def _record_response(name: str, r: httpx.Response) -> Path:
    try:
        body = r.json()
    except Exception:
        body = {"_raw_text": r.text[:5000]}
    return _save(
        name,
        {
            "url": str(r.request.url),
            "status": r.status_code,
            "headers": dict(r.headers),
            "body": body,
        },
    )


async def descobrir_questao(client: TcClient, qid: int, *, caderno_id: int | None = None) -> Path:
    """Captura GET /api/questoes/{id}/deslogado bruto."""
    referer = (
        f"{get_settings().tc_base}/questoes/cadernos/{caderno_id}"
        if caderno_id
        else None
    )
    r = await client.get(f"/api/questoes/{qid}/deslogado", referer=referer)
    return _record_response(f"questao-{qid}", r)


async def descobrir_caderno(client: TcClient, caderno_id: int) -> list[Path]:
    """Tenta múltiplas hipóteses do endpoint de IDs do caderno e salva todas as respostas."""
    paths: list[Path] = []
    tentativas = [
        ("GET", f"/api/cadernos/{caderno_id}/questoes/ids", None),
        ("GET", f"/api/cadernos/{caderno_id}", None),
        ("GET", f"/api/cadernos/{caderno_id}/questoes", None),
        ("POST", f"/api/cadernos/{caderno_id}/questoes", {"pagina": 1, "tamanho": 200}),
    ]
    for method, path, body in tentativas:
        try:
            if method == "GET":
                r = await client.get(path)
            else:
                r = await client.post(path, json_body=body)
        except Exception as e:  # noqa: BLE001
            log.warning("discovery.caderno.fail", method=method, path=path, err=str(e))
            continue
        safe = path.strip("/").replace("/", "_")
        paths.append(_record_response(f"caderno-{caderno_id}-{method}-{safe}", r))
    return paths


async def descobrir_contagem(client: TcClient, filtros: dict | None = None) -> Path:
    """Bate /api/questoes/contagem/filtros (o 'mágico' do TC)."""
    r = await client.post("/api/questoes/contagem/filtros", json_body=filtros or {})
    return _record_response("contagem-filtros", r)


async def descobrir_lista(client: TcClient, filtros: dict | None = None) -> Path:
    """Bate /api/questoes/filtros."""
    r = await client.post("/api/questoes/filtros", json_body=filtros or {})
    return _record_response("lista-filtros", r)
