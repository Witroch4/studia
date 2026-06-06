"""Entrada do scraper — CLI (typer) + API FastAPI minimal.

Comandos:
    python -m app.main login                       # Playwright login → storage_state.json
    python -m app.main discover questao <id>       # Dump raw JSON de uma questão
    python -m app.main discover caderno <id>       # Testa hipóteses de listagem
    python -m app.main scrape caderno <id>         # Scrape completo do caderno
    python -m app.main scrape questoes <id> <id>...
    python -m app.main api                         # Sobe FastAPI em :8090

FastAPI:
    POST /run/caderno         body: {caderno_id: int}
    POST /run/questoes        body: {ids: [int, ...]}
    POST /discover/questao    body: {id: int, caderno_id: int|null}
    GET  /health
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from fastapi import FastAPI
from pydantic import BaseModel

from app.auth import login_and_save_state
from app.client import TcClient
from app.config import get_settings
from app.discovery import (
    descobrir_caderno,
    descobrir_contagem,
    descobrir_lista,
    descobrir_questao,
)
from app.observability import configure_logging, get_logger
from app.scrapers.tc_imprimir import scrape_caderno_imprimir
from app.scrapers.tecconcursos import scrape_caderno, scrape_ids
from app.state import ScrapeState

configure_logging()
log = get_logger(__name__)

cli = typer.Typer(help="witdev-tec-master scraper CLI", no_args_is_help=True)
discover_app = typer.Typer(help="Inspeção de endpoints (salva raw em ./discovery/)")
scrape_app = typer.Typer(help="Coleta efetiva e persistência")
cli.add_typer(discover_app, name="discover")
cli.add_typer(scrape_app, name="scrape")


# ─── CLI: auth ───────────────────────────────────────────────────


@cli.command()
def login(
    headless: Annotated[bool, typer.Option(help="Rodar Chromium headless")] = False,
) -> None:
    """Loga em TecConcursos e salva storage_state.json."""
    path = asyncio.run(login_and_save_state(headless=headless))
    typer.echo(f"ok: {path}")


# ─── CLI: discovery ──────────────────────────────────────────────


async def _with_client(coro_factory):
    from app.auth import load_cookies_for_httpx

    cookies = load_cookies_for_httpx()
    async with TcClient(cookies) as client:
        return await coro_factory(client)


@discover_app.command("questao")
def discover_questao(
    qid: int,
    caderno_id: Annotated[int | None, typer.Option(help="Caderno de origem (Referer)")] = None,
) -> None:
    path = asyncio.run(_with_client(lambda c: descobrir_questao(c, qid, caderno_id=caderno_id)))
    typer.echo(str(path))


@discover_app.command("caderno")
def discover_caderno(caderno_id: int) -> None:
    paths = asyncio.run(_with_client(lambda c: descobrir_caderno(c, caderno_id)))
    for p in paths:
        typer.echo(str(p))


@discover_app.command("contagem")
def discover_contagem() -> None:
    path = asyncio.run(_with_client(lambda c: descobrir_contagem(c)))
    typer.echo(str(path))


@discover_app.command("lista")
def discover_lista() -> None:
    path = asyncio.run(_with_client(lambda c: descobrir_lista(c)))
    typer.echo(str(path))


# ─── CLI: scrape ─────────────────────────────────────────────────


@scrape_app.command("caderno")
def cli_scrape_caderno(
    caderno_id: int,
    limite: Annotated[int | None, typer.Option(help="Smoke test: scrape apenas N primeiras posições")] = None,
    total: Annotated[int | None, typer.Option(help="Total de questões (skip binary search inicial)")] = None,
) -> None:
    result = asyncio.run(scrape_caderno(caderno_id, limite=limite, total=total))
    typer.echo(str(result))


@scrape_app.command("imprimir")
def cli_scrape_imprimir(
    caderno_id: int,
    total: Annotated[int | None, typer.Option(help="Total esperado (opcional, pra parar cedo)")] = None,
    page_size: Annotated[int, typer.Option(help="Questões por página")] = 200,
) -> None:
    """Scrape via endpoint /ajaxCarregarQuestoesImpressao (recomendado).

    200 questões por request, JSON estruturado, gabarito completo,
    sem rate-limit issues. Caderno de 876 = 5 requests.
    """
    result = asyncio.run(scrape_caderno_imprimir(caderno_id, total=total, page_size=page_size))
    typer.echo(str(result))


@scrape_app.command("questoes")
def cli_scrape_questoes(
    ids: list[int],
    caderno_id: Annotated[int | None, typer.Option(help="Caderno de origem")] = None,
) -> None:
    result = asyncio.run(scrape_ids(ids, caderno_id=caderno_id))
    typer.echo(str(result))


@cli.command()
def status() -> None:
    """Resumo do ScrapeState (quantas coletadas, erros, etc)."""
    st = ScrapeState()
    typer.echo(
        f"ok={st.contar('ok')} missing={st.contar('missing')} "
        f"erro_prefix={st.contar_prefix('erro')}"
    )
    st.close()


# ─── API FastAPI ─────────────────────────────────────────────────


api = FastAPI(title="witdev-tec-scraper", version="0.1.0")


class CadernoBody(BaseModel):
    caderno_id: int


class QuestoesBody(BaseModel):
    ids: list[int]
    caderno_id: int | None = None


class DiscoverQuestaoBody(BaseModel):
    id: int
    caderno_id: int | None = None


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@api.post("/run/caderno")
async def run_caderno(body: CadernoBody) -> dict[str, int]:
    return await scrape_caderno(body.caderno_id)


@api.post("/run/questoes")
async def run_questoes(body: QuestoesBody) -> dict[str, int]:
    return await scrape_ids(body.ids, caderno_id=body.caderno_id)


@api.post("/discover/questao")
async def api_discover_questao(body: DiscoverQuestaoBody) -> dict[str, str]:
    from app.auth import load_cookies_for_httpx

    cookies = load_cookies_for_httpx()
    async with TcClient(cookies) as client:
        path = await descobrir_questao(client, body.id, caderno_id=body.caderno_id)
    return {"path": str(path)}


@cli.command()
def api_serve(
    host: Annotated[str, typer.Option()] = "0.0.0.0",
    port: Annotated[int, typer.Option()] = 8090,
) -> None:
    """Sobe FastAPI control-plane."""
    import uvicorn

    uvicorn.run(api, host=host, port=port, log_level=get_settings().log_level.lower())


if __name__ == "__main__":
    cli()
