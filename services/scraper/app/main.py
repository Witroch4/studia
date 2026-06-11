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
from typing import Annotated, Any

import typer
from fastapi import FastAPI, HTTPException
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
from app.auth import login_and_save_state
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


class EnqueueCadernoBody(BaseModel):
    caderno_id: int
    expected_total: int | None = None
    page_size: int = 200
    requested_by: int | None = None
    enqueue_limit: int | None = 1
    discover_total: bool = False
    relogin: bool = False


class EnqueueCadernoResponse(BaseModel):
    job_id: int
    status: str
    total_units: int
    enqueued_units: int


class EnqueueImagensBody(BaseModel):
    enqueue_limit: int = 5


class EnqueueImagensResponse(BaseModel):
    discovered_urls: int
    assets_upserted: int
    enqueued_units: int


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class ResolverGuiaBody(BaseModel):
    url: str
    relogin: bool = False


class SalvarCadernosBody(BaseModel):
    tc_guia_id: int


async def _with_tc_client(coro_factory, *, relogin: bool = False):
    from app.auth import load_cookies_for_httpx

    if relogin:
        await login_and_save_state(headless=True)
    cookies = load_cookies_for_httpx()
    async with TcClient(cookies) as client:
        return await coro_factory(client)


@api.post("/guia/resolver")
async def resolver_guia_endpoint(body: ResolverGuiaBody) -> dict[str, Any]:
    """Resolve a URL base/cargo de um guia TC em guiaId + lista de cadernos."""
    from app.scrapers.tc_guia import resolver_guia

    guia = await _with_tc_client(
        lambda c: resolver_guia(c, body.url), relogin=body.relogin
    )
    return {
        "tc_guia_id": guia.tc_guia_id,
        "slug": guia.slug,
        "url": guia.url,
        "nome": guia.nome,
        "banca": guia.banca,
        "cadernos": [
            {
                "tc_caderno_id": c.tc_caderno_id,
                "caderno_base_id": c.caderno_base_id,
                "nome": c.nome,
                "total_questoes": c.total_questoes,
                "total_capitulos": c.total_capitulos,
                "ordem": c.ordem,
                "usuario_possui_salvo": c.usuario_possui_salvo,
            }
            for c in guia.cadernos
        ],
    }


@api.get("/guia/buscar")
async def buscar_guias_endpoint(termo: str) -> dict[str, Any]:
    """Busca guias do TC por palavra-chave (ex.: 'oab')."""
    from app.scrapers.tc_guia import buscar_guias

    resultados = await _with_tc_client(lambda c: buscar_guias(c, termo))
    return {"termo": termo, "guias": resultados}


@api.post("/guia/salvar-cadernos")
async def salvar_cadernos_endpoint(body: SalvarCadernosBody) -> dict[str, Any]:
    """Dispara 'Salvar todos os cadernos do guia' e devolve pasta + itens."""
    from app.scrapers.tc_guia import listar_itens_pasta, salvar_todos_cadernos

    async def _run(client: TcClient) -> dict[str, Any]:
        pasta_id = await salvar_todos_cadernos(client, body.tc_guia_id)
        itens = await listar_itens_pasta(client, pasta_id) if pasta_id else []
        return {"pasta_id": pasta_id, "itens": itens}

    return await _with_tc_client(_run)


@api.post("/enqueue/caderno", response_model=EnqueueCadernoResponse)
async def enqueue_caderno(body: EnqueueCadernoBody) -> EnqueueCadernoResponse:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.tasks.caderno import coletar_pagina_caderno_tc
    from app.tasks.enqueue import enqueue
    from app.tasks.ledger import (
        ensure_ledger_schema,
        get_caderno_job,
        list_enqueueable_caderno_units,
        upsert_caderno_job,
    )

    settings = get_settings()
    expected_total = body.expected_total
    if expected_total is None and body.discover_total:
        from app.scrapers.tc_total import discover_caderno_total

        expected_total = await discover_caderno_total(body.caderno_id)

    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            job = await upsert_caderno_job(
                session,
                caderno_id=body.caderno_id,
                expected_total=expected_total,
                page_size=body.page_size,
                requested_by=body.requested_by,
            )
            units = await list_enqueueable_caderno_units(
                session,
                caderno_id=body.caderno_id,
                limit=body.enqueue_limit,
            )

        enqueued_units = 0
        for unit in units:
            await enqueue(
                coletar_pagina_caderno_tc,
                priority="default",
                caderno_id=body.caderno_id,
                inicio=unit["inicio"],
                page_size=body.page_size,
                relogin=(
                    (body.relogin and enqueued_units == 0)
                    or (
                        unit.get("status") == "blocked"
                        and unit.get("block_reason") == "session_expired"
                    )
                ),
            )
            enqueued_units += 1

        async with Session.begin() as session:
            job = await get_caderno_job(session, job_id=job.id)

        return EnqueueCadernoResponse(
            job_id=job.id,
            status=job.status,
            total_units=job.total_units,
            enqueued_units=enqueued_units,
        )
    finally:
        await engine.dispose()


async def _set_job_paused(job_id: int, paused: bool) -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.tasks.ledger import ensure_ledger_schema, set_caderno_job_paused

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            ok = await set_caderno_job_paused(session, job_id=job_id, paused=paused)
        if not ok:
            raise HTTPException(404, "job não encontrado")
        return {"job_id": job_id, "paused": paused}
    finally:
        await engine.dispose()


@api.post("/job/{job_id}/pause")
async def pause_job(job_id: int) -> dict[str, Any]:
    """Pausa a coleta do job (supervisor para de enfileirar novas faixas)."""
    return await _set_job_paused(job_id, True)


@api.post("/job/{job_id}/resume")
async def resume_job(job_id: int) -> dict[str, Any]:
    """Retoma a coleta do job pausado."""
    return await _set_job_paused(job_id, False)


@api.post("/enqueue/imagens", response_model=EnqueueImagensResponse)
async def enqueue_imagens(body: EnqueueImagensBody) -> EnqueueImagensResponse:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.tasks.imagens import (
        discover_image_urls,
        enqueue_next_image_asset,
        upsert_image_assets,
    )
    from app.tasks.ledger import ensure_ledger_schema

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            urls = await discover_image_urls(session)
            assets_upserted = await upsert_image_assets(session, urls)

        enqueued_units = await enqueue_next_image_asset(
            Session,
            limit=body.enqueue_limit,
        )
        return EnqueueImagensResponse(
            discovered_urls=len(urls),
            assets_upserted=assets_upserted,
            enqueued_units=enqueued_units,
        )
    finally:
        await engine.dispose()


@api.post("/run/caderno")
async def run_caderno(body: CadernoBody) -> dict[str, int]:
    return await scrape_caderno(body.caderno_id)


class CadernoImprimirBody(BaseModel):
    caderno_id: int
    total: int | None = None
    page_size: int = 200
    relogin: bool = False


@api.post("/run/caderno-imprimir")
async def run_caderno_imprimir(body: CadernoImprimirBody) -> dict[str, int | str]:
    """Caminho OFICIAL — usa /ajaxCarregarQuestoesImpressao (200 quest./req, 100% gabarito).

    Se relogin=true, refaz login Playwright antes (recomendado quando trocou IP
    ou faz tempo desde a última coleta).
    """
    if body.relogin:
        await login_and_save_state(headless=True)
    return await scrape_caderno_imprimir(
        body.caderno_id, total=body.total, page_size=body.page_size,
    )


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


@cli.command("queue-supervisor")
def queue_supervisor(
    interval: Annotated[int, typer.Option(help="Segundos entre varreduras")] = 60,
    image_limit: Annotated[int, typer.Option(help="Imagens a enfileirar por varredura")] = 5,
    image_discovery_interval: Annotated[
        int,
        typer.Option(help="Segundos entre redescobertas de URLs de imagens"),
    ] = 600,
) -> None:
    """Mantem jobs TaskIQ andando sem depender da UI.

    O supervisor só publica unidades elegíveis pelo ledger. Ele não volta caderno
    do zero e não ignora cooldown de bloqueio do TC.
    """

    asyncio.run(
        _queue_supervisor_loop(
            interval=interval,
            image_limit=image_limit,
            image_discovery_interval=image_discovery_interval,
        )
    )


async def _queue_supervisor_loop(
    *,
    interval: int,
    image_limit: int,
    image_discovery_interval: int,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.tasks.caderno import coletar_pagina_caderno_tc
    from app.tasks.enqueue import enqueue
    from app.tasks.imagens import (
        discover_image_urls,
        enqueue_next_image_asset,
        upsert_image_assets,
    )
    from app.tasks.ledger import (
        ensure_ledger_schema,
        list_active_caderno_jobs,
        list_enqueueable_caderno_units,
        refresh_caderno_job_status,
    )

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    loop = asyncio.get_running_loop()
    last_image_discovery = 0.0

    try:
        while True:
            caderno_enqueued = 0
            images_discovered = 0
            image_assets_upserted = 0

            async with engine.begin() as conn:
                await ensure_ledger_schema(conn)

            async with Session.begin() as session:
                jobs = await list_active_caderno_jobs(session)
                for job in jobs:
                    await refresh_caderno_job_status(session, job_id=job.id)
                jobs = await list_active_caderno_jobs(session)

            for job in jobs:
                async with Session.begin() as session:
                    units = await list_enqueueable_caderno_units(
                        session,
                        caderno_id=job.caderno_id,
                        limit=1,
                    )
                for unit in units:
                    await enqueue(
                        coletar_pagina_caderno_tc,
                        priority="default",
                        caderno_id=job.caderno_id,
                        inicio=unit["inicio"],
                        page_size=unit["page_size"],
                        relogin=(
                            unit.get("status") == "blocked"
                            and unit.get("block_reason") == "session_expired"
                        ),
                    )
                    caderno_enqueued += 1

            now = loop.time()
            if image_limit > 0:
                if now - last_image_discovery >= image_discovery_interval:
                    async with Session.begin() as session:
                        urls = await discover_image_urls(session)
                        images_discovered = len(urls)
                        image_assets_upserted = await upsert_image_assets(session, urls)
                    last_image_discovery = now
                image_enqueued = await enqueue_next_image_asset(
                    Session,
                    limit=image_limit,
                )
            else:
                image_enqueued = 0

            log.info(
                "queue_supervisor.tick",
                caderno_jobs=len(jobs),
                caderno_enqueued=caderno_enqueued,
                images_discovered=images_discovered,
                image_assets_upserted=image_assets_upserted,
                image_enqueued=image_enqueued,
                interval=interval,
            )
            await asyncio.sleep(max(interval, 1))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    cli()
