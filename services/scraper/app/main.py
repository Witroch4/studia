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
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from app.auth import (
    NoEligibleTcAccount,
    TC_TASK_CADERNO,
    TC_TASK_FORUM_LAZY,
    TC_TASK_FORUM_MASS,
    TC_TASK_GABARITO,
    TC_TASK_GUIA,
    TC_TASK_IMAGEM,
    clear_tc_session,
    login_and_save_state,
    select_tc_account_for_task,
    save_runtime_credentials,
    tc_auth_status,
    update_tc_account_capabilities,
)
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


class TcAuthLoginBody(BaseModel):
    email: str | None = None
    password: str | None = None
    account_id: str | None = None
    capabilities: dict[str, bool] | None = None


class TcAuthCapabilitiesBody(BaseModel):
    capabilities: dict[str, bool]


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


@api.get("/tc/auth/status")
async def tc_auth_status_endpoint() -> dict[str, Any]:
    return tc_auth_status()


@api.post("/tc/auth/login")
async def tc_auth_login_endpoint(body: TcAuthLoginBody) -> dict[str, Any]:
    email = (body.email or "").strip()
    password = body.password or ""
    has_new_credentials = bool(email or password)
    if has_new_credentials and (not email or not password):
        raise HTTPException(422, "email e senha do TC são obrigatórios")
    try:
        login_kwargs: dict[str, Any] = {"headless": True}
        if has_new_credentials:
            login_kwargs.update({"email": email, "password": password})
        elif body.account_id:
            login_kwargs["account_id"] = body.account_id
        await login_and_save_state(**login_kwargs)
    except Exception as exc:
        raise HTTPException(502, f"login TC falhou: {exc}") from exc
    if has_new_credentials:
        save_runtime_credentials(email, password, capabilities=body.capabilities)
    return {"ok": True, **tc_auth_status()}


@api.delete("/tc/auth/session")
async def tc_auth_logout_endpoint(account_id: str | None = None) -> dict[str, Any]:
    try:
        removed = clear_tc_session(account_id=account_id)
    except KeyError as exc:
        raise HTTPException(404, "conta TC não encontrada") from exc
    return {"ok": True, "storage_state_removed": removed, **tc_auth_status()}


@api.patch("/tc/auth/accounts/{account_id}/capabilities")
async def tc_auth_capabilities_endpoint(
    account_id: str, body: TcAuthCapabilitiesBody
) -> dict[str, Any]:
    try:
        update_tc_account_capabilities(account_id, body.capabilities)
    except KeyError as exc:
        raise HTTPException(404, "conta TC não encontrada") from exc
    return {"ok": True, **tc_auth_status()}


class ResolverGuiaBody(BaseModel):
    url: str
    relogin: bool = False


class SalvarCadernosBody(BaseModel):
    tc_guia_id: int


async def _with_tc_client(
    coro_factory,
    *,
    relogin: bool = False,
    task: str = TC_TASK_CADERNO,
):
    from app.auth import load_cookies_for_httpx
    from app.schemas import SessionExpired

    try:
        account = select_tc_account_for_task(task)
    except NoEligibleTcAccount as exc:
        raise HTTPException(409, str(exc)) from exc
    account_id = account["id"]
    if relogin:
        await login_and_save_state(headless=True, account_id=account_id)
    cookies = load_cookies_for_httpx(account_id=account_id)
    async with TcClient(cookies) as client:
        try:
            return await coro_factory(client)
        except SessionExpired:
            # Sessão queimada no meio da operação (401/302 → login). Reloga uma
            # vez e retenta com cookies novos — as ops de guia (resolver/salvar)
            # passam a se auto-curar igual à coleta de caderno.
            log.warning("tc_with_client.relogin_retry", task=task, account_id=account_id)
            await login_and_save_state(headless=True, account_id=account_id)
            async with TcClient(load_cookies_for_httpx(account_id=account_id)) as client2:
                return await coro_factory(client2)


@api.get("/caderno/{caderno_id}/gabarito")
async def gabarito_endpoint(caderno_id: int, relogin: bool = False) -> dict[str, Any]:
    """Gabarito/desempenho do usuário (acertou/errou/alternativa/data por questão).

    Pagina ``GET /api/cadernos/{id}/gabarito`` na sessão TC e devolve a lista
    agregada. O backend mapeia ``idQuestao`` → questão studIA e grava resoluções.
    """
    from app.scrapers.tc_gabarito import fetch_gabarito

    return await _with_tc_client(
        lambda c: fetch_gabarito(c, caderno_id),
        relogin=relogin,
        task=TC_TASK_GABARITO,
    )


# Domínios TC: aceita subdomínios (.tecconcursos.com.br) mas S3 deve ser EXATO
# (evita SSRF via evil.s3-sa-east-1.amazonaws.com).
_TC_SUBDOM_HOSTS = ("tecconcursos.com.br",)   # match exato OU subdomínio
_TC_EXACT_HOSTS  = ("s3-sa-east-1.amazonaws.com",)  # somente match exato


def _host_permitido(host: str) -> bool:
    return (
        any(host == h or host.endswith("." + h) for h in _TC_SUBDOM_HOSTS)
        or host in _TC_EXACT_HOSTS
    )


@api.get("/questao/{id_questao}/comentarios")
async def comentarios_endpoint(
    id_questao: int,
    quadro: str = "alunos",
    relogin: bool = False,
    task: str = TC_TASK_FORUM_LAZY,
) -> dict[str, Any]:
    from app.scrapers.tc_comentarios import fetch_comentarios
    if quadro not in ("alunos", "professores"):
        raise HTTPException(422, "quadro inválido")
    if task not in (TC_TASK_FORUM_LAZY, TC_TASK_FORUM_MASS):
        raise HTTPException(422, "task inválida")
    return await _with_tc_client(
        lambda c: fetch_comentarios(c, id_questao, quadro),
        relogin=relogin,
        task=task,
    )


@api.get("/tc/imagem")
async def tc_imagem_endpoint(u: str) -> Response:
    """Baixa uma imagem do TC pela sessão autenticada (proxy p/ re-host no MinIO)."""
    from urllib.parse import urlparse
    host = (urlparse(u).hostname or "").lower()
    if not _host_permitido(host):
        raise HTTPException(400, "host de imagem não permitido")

    async def _baixar(client: TcClient) -> Response:
        r = await client._client.get(u, headers=client._build_headers(
            "https://www.tecconcursos.com.br/", None))
        client._check(r)
        return Response(content=r.content,
                        media_type=r.headers.get("content-type", "image/png"))

    return await _with_tc_client(_baixar, task=TC_TASK_IMAGEM)


@api.post("/guia/resolver")
async def resolver_guia_endpoint(body: ResolverGuiaBody) -> dict[str, Any]:
    """Resolve a URL base/cargo de um guia TC em guiaId + lista de cadernos."""
    from app.scrapers.tc_guia import resolver_guia

    guia = await _with_tc_client(
        lambda c: resolver_guia(c, body.url),
        relogin=body.relogin,
        task=TC_TASK_GUIA,
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

    resultados = await _with_tc_client(lambda c: buscar_guias(c, termo), task=TC_TASK_GUIA)
    return {"termo": termo, "guias": resultados}


@api.post("/guia/salvar-cadernos")
async def salvar_cadernos_endpoint(body: SalvarCadernosBody) -> dict[str, Any]:
    """Dispara 'Salvar todos os cadernos do guia' e devolve pasta + itens."""
    from app.scrapers.tc_guia import listar_itens_pasta, salvar_todos_cadernos

    async def _run(client: TcClient) -> dict[str, Any]:
        pasta_id = await salvar_todos_cadernos(client, body.tc_guia_id)
        itens = await listar_itens_pasta(client, pasta_id) if pasta_id else []
        return {"pasta_id": pasta_id, "itens": itens}

    return await _with_tc_client(_run, task=TC_TASK_GUIA)


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
    try:
        select_tc_account_for_task(TC_TASK_CADERNO, touch_usage=False)
    except NoEligibleTcAccount as exc:
        raise HTTPException(409, str(exc)) from exc
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


class EnqueueComentariosBody(BaseModel):
    caderno_id: int
    questao_ids: list[int]
    requested_by: int | None = None


@api.post("/enqueue/comentarios", response_model=EnqueueCadernoResponse)
async def enqueue_comentarios(body: EnqueueComentariosBody) -> EnqueueCadernoResponse:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.tasks.comentarios import coletar_comentarios_questao
    from app.tasks.enqueue import enqueue
    from app.tasks.ledger import (
        ensure_ledger_schema,
        get_caderno_job,
        list_enqueueable_comentario_units,
        upsert_comentario_job,
    )

    settings = get_settings()
    try:
        select_tc_account_for_task(TC_TASK_FORUM_MASS, touch_usage=False)
    except NoEligibleTcAccount as exc:
        raise HTTPException(409, str(exc)) from exc
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            job = await upsert_comentario_job(
                session, caderno_id=body.caderno_id,
                questao_ids=body.questao_ids, requested_by=body.requested_by)
            units = await list_enqueueable_comentario_units(
                session, caderno_id=body.caderno_id, limit=1)
        enqueued = 0
        for u in units:
            await enqueue(coletar_comentarios_questao, priority="default",
                          questao_id=u["questao_id"], caderno_id=body.caderno_id)
            enqueued += 1
        async with Session.begin() as session:
            job = await get_caderno_job(session, job_id=job.id)
        return EnqueueCadernoResponse(job_id=job.id, status=job.status,
                                      total_units=job.total_units, enqueued_units=enqueued)
    finally:
        await engine.dispose()


class EnqueueConcursosBody(BaseModel):
    filtros: list[dict[str, Any]]
    requested_by: int | None = None


@api.post("/enqueue/concursos", response_model=EnqueueCadernoResponse)
async def enqueue_concursos(body: EnqueueConcursosBody) -> EnqueueCadernoResponse:
    """Dispara a descoberta paginada da busca avançada de concursos do TC para
    um conjunto de filtros (banca/profissão/etc.). Síncrono e rápido: só faz
    upsert do job + enfileira a task de descoberta (que grava as units e
    dispara o download da 1ª)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.scrapers.tc_concursos import filtros_external_id
    from app.tasks.concursos import descobrir_concursos
    from app.tasks.enqueue import enqueue
    from app.tasks.ledger import ensure_ledger_schema, upsert_concursos_job

    if not body.filtros:
        raise HTTPException(422, "informe ao menos um filtro")
    if any(not isinstance(f, dict) or "id" not in f or "tipo" not in f for f in body.filtros):
        raise HTTPException(422, "cada filtro precisa de 'id' e 'tipo'")
    try:
        select_tc_account_for_task(TC_TASK_GUIA, touch_usage=False)
    except NoEligibleTcAccount as exc:
        raise HTTPException(409, str(exc)) from exc
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            await ensure_ledger_schema(conn)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session.begin() as session:
            job = await upsert_concursos_job(
                session, external_id=filtros_external_id(body.filtros),
                filtros=body.filtros, requested_by=body.requested_by)
        await enqueue(descobrir_concursos, priority="default",
                      job_id=job.id, filtros=body.filtros)
        return EnqueueCadernoResponse(job_id=job.id, status=job.status,
                                      total_units=job.total_units, enqueued_units=1)
    finally:
        await engine.dispose()


@api.get("/tc/concursos/filtros")
async def tc_concursos_filtros() -> dict[str, Any]:
    """Opções de filtro (bancas/profissões) da busca avançada de concursos do TC."""
    from app.scrapers.tc_concursos import fetch_filtros_busca

    return await _with_tc_client(fetch_filtros_busca, task=TC_TASK_GUIA)


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

            async def _eq(questao_id, caderno_id):
                from app.tasks.comentarios import coletar_comentarios_questao
                await enqueue(coletar_comentarios_questao, priority="default",
                              questao_id=questao_id, caderno_id=caderno_id)

            comentarios_enqueued = await _supervisor_tick_comentarios(Session, _eq)

            async def _eq_concursos(job_id, concurso_id):
                from app.tasks.concursos import coletar_arquivos_concurso
                await enqueue(coletar_arquivos_concurso, priority="default",
                              job_id=job_id, concurso_id=concurso_id)

            concursos_enqueued = await _supervisor_tick_concursos(Session, _eq_concursos)

            log.info(
                "queue_supervisor.tick",
                caderno_jobs=len(jobs),
                caderno_enqueued=caderno_enqueued,
                images_discovered=images_discovered,
                image_assets_upserted=image_assets_upserted,
                image_enqueued=image_enqueued,
                comentarios_enqueued=comentarios_enqueued,
                concursos_enqueued=concursos_enqueued,
                interval=interval,
            )
            await asyncio.sleep(max(interval, 1))
    finally:
        await engine.dispose()


async def _supervisor_tick_comentarios(Session, enqueue_fn) -> int:
    from app.tasks.ledger import (
        list_active_comentario_jobs,
        list_enqueueable_comentario_units,
        refresh_comentario_job_status,
    )

    enfileiradas = 0
    async with Session.begin() as session:
        jobs = await list_active_comentario_jobs(session)
        for job in jobs:
            await refresh_comentario_job_status(session, job_id=job.id)
        jobs = await list_active_comentario_jobs(session)
    for job in jobs:
        async with Session.begin() as session:
            units = await list_enqueueable_comentario_units(
                session, caderno_id=job.caderno_id, limit=1
            )
        for u in units:
            await enqueue_fn(questao_id=u["questao_id"], caderno_id=job.caderno_id)
            enfileiradas += 1
    return enfileiradas


async def _supervisor_tick_concursos(Session, enqueue_fn) -> int:
    """Análogo a `_supervisor_tick_comentarios` p/ jobs `kind='concursos'`.

    Só considera jobs com a descoberta paginada já concluída
    (`params->>'discovery' = 'done'`) — enquanto isso, `descobrir_concursos`
    ainda está gravando units e já mantém a esteira andando sozinha."""
    from sqlalchemy import text

    from app.tasks.ledger import list_enqueueable_concurso_units, refresh_concursos_job_status

    select_active_sql = text(
        """
        SELECT id
        FROM tc_jobs
        WHERE kind = 'concursos'
          AND status IN ('pending', 'running', 'blocked')
          AND paused_by_user IS NOT TRUE
          AND COALESCE(params->>'discovery', '') = 'done'
        ORDER BY id
        """
    )

    enfileiradas = 0
    async with Session.begin() as session:
        job_ids = [int(r) for r in (await session.execute(select_active_sql)).scalars().all()]
        for job_id in job_ids:
            await refresh_concursos_job_status(session, job_id=job_id)
        job_ids = [int(r) for r in (await session.execute(select_active_sql)).scalars().all()]
    for job_id in job_ids:
        async with Session.begin() as session:
            units = await list_enqueueable_concurso_units(session, job_id=job_id, limit=1)
        for u in units:
            await enqueue_fn(job_id=job_id, concurso_id=u["concurso_id"])
            enfileiradas += 1
    return enfileiradas


if __name__ == "__main__":
    cli()
