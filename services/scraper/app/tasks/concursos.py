"""Coleta de concursos do TC: descoberta paginada (busca avançada) + download
dos arquivos (edital/gabarito/etc.) de cada concurso encontrado.

Duas tasks:
  - `descobrir_concursos`: pagina a busca avançada, grava units (1/concurso)
    no ledger e enfileira a 1ª unit de download.
  - `coletar_arquivos_concurso`: baixa os arquivos de 1 concurso (via CDN
    público, sem sessão TC), sobe no MinIO (bucket privado) e importa no
    backend. Encadeia a próxima unit ao final (sucesso ou falha).

Hooks substituíveis (`_lease/_mark_done/_mark_failed/_is_paused/_release/
_enqueue_next/_download/_put_minio/_stat_minio/_post_import`) — mesmo desenho
de `comentarios.py` — permitem testar `_processar_unit_concurso` sem DB/MinIO/
rede (monkeypatch nos atributos do módulo, lookup via `import
app.tasks.concursos as _self`).
"""
from __future__ import annotations

import asyncio
import inspect
import os
import random
import re
from io import BytesIO
from typing import Any

import httpx
from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import (
    NoEligibleTcAccount,
    TC_TASK_GUIA,
    load_cookies_for_httpx,
    login_and_save_state,
    select_tc_account_for_task,
)
from app.client import TcClient
from app.config import get_settings
from app.observability import get_logger
from app.schemas import SessionExpired
from app.scrapers.tc_concursos import CDN_ARQUIVO_URL, fetch_busca_avancada, parse_busca_page
from app.tasks.brokers.studia import broker_studia_default
from app.tasks.enqueue import enqueue
from app.tasks.ledger import (
    ensure_ledger_schema,
    is_concursos_paused,
    lease_concurso_unit,
    list_enqueueable_concurso_units,
    mark_concurso_unit_done,
    mark_concurso_unit_failed,
    refresh_concursos_job_status,
    release_concurso_unit_to_pending,
    set_concursos_job_discovery,
    upsert_concurso_units,
)

log = get_logger(__name__)

MAX_PAGINAS_DESCOBERTA = 100  # teto rígido de segurança

_EXT_BY_CT = {
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
}


def _object_key(uuid: str, content_type: str | None, filename: str | None) -> str:
    ext = _EXT_BY_CT.get((content_type or "").split(";")[0].strip().lower())
    if not ext and filename and "." in filename:
        ext = os.path.splitext(filename)[1].lower()[:8] or None
    return f"concursos/{uuid}{ext or ''}"


async def _download(url: str) -> tuple[bytes, str | None, str | None]:
    """GET público no CDN (sem cookies TC). Retorna (bytes, content_type, filename).

    Async (httpx.AsyncClient, espelha imagens._download_image) — um PDF/ZIP de
    edital pode levar minutos (read timeout 300s); um client síncrono aqui
    bloquearia o event loop inteiro do worker."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10, read=300, write=30, pool=310),
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as c:
        r = await c.get(url)
        r.raise_for_status()
        cd = r.headers.get("content-disposition") or ""
        m = re.search(r'filename="?([^";]+)', cd)
        return r.content, r.headers.get("content-type"), (m.group(1) if m else None)


def _minio_client() -> Minio:
    return Minio(
        os.environ.get("MINIO_ENDPOINT") or "minio:9000",
        access_key=os.environ.get("MINIO_ACCESS_KEY") or "witalo",
        secret_key=os.environ.get("MINIO_SECRET_KEY") or "",
        secure=(os.environ.get("MINIO_SECURE") or "false").lower() == "true",
    )


def _pdf_bucket() -> str:
    return os.environ.get("MINIO_PDF_BUCKET") or "studia-pdfs"


async def _put_minio(key: str, data: bytes, ct: str | None) -> None:
    client = _minio_client()
    bucket = _pdf_bucket()
    if not await asyncio.to_thread(client.bucket_exists, bucket):
        await asyncio.to_thread(client.make_bucket, bucket)
    # Bucket privado: NENHUMA policy pública é aplicada (diferente de imagens.py).
    await asyncio.to_thread(
        client.put_object,
        bucket,
        key,
        BytesIO(data),
        len(data),
        content_type=ct or "application/octet-stream",
    )


async def _stat_minio(key: str) -> dict[str, Any] | None:
    """`key` aqui é um PREFIXO (ex: `concursos/{uuid}`) — lista o bucket por
    esse prefixo e devolve metadados do primeiro objeto encontrado, ou None.

    O SDK do MinIO é síncrono → chamadas rodam em thread (asyncio.to_thread,
    como `_put_minio`) pra não bloquear o event loop do worker. Erro vira None
    (trata como "não existe" → re-baixa, idempotente) mas LOGA warning: falha
    sistêmica de credencial/rede do MinIO precisa aparecer nos logs."""
    client = _minio_client()
    bucket = _pdf_bucket()
    try:
        objs = await asyncio.to_thread(
            lambda: list(client.list_objects(bucket, prefix=key, recursive=False))
        )
    except Exception as exc:  # noqa: BLE001 — bucket ainda não existe, etc.
        log.warning("concursos.stat_minio_falhou", key=key, erro=str(exc)[:120])
        return None
    if not objs:
        return None
    obj = objs[0]
    try:
        st = await asyncio.to_thread(client.stat_object, bucket, obj.object_name)
    except Exception as exc:  # noqa: BLE001
        log.warning("concursos.stat_minio_falhou", key=key, erro=str(exc)[:120])
        return None
    return {
        "key": obj.object_name,
        "content_type": st.content_type,
        "size": st.size,
    }


async def _post_import(payload: dict[str, Any], *, _sleep: Any = asyncio.sleep) -> dict[str, Any]:
    s = get_settings()
    url = f"{s.backend_url}/api/q/concursos/importar"
    headers = {"X-Internal-Token": s.studia_internal_token}
    ultimo: Exception | None = None
    for tentativa in range(3):  # 1 + 2 retries
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=180, write=10, pool=185)
        ) as c:
            r = await c.post(url, headers=headers, json=payload)
            if r.status_code < 500:
                r.raise_for_status()  # 4xx → falha imediata
                return r.json()
            ultimo = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
        if tentativa < 2:
            res = _sleep(3.0)
            if inspect.isawaitable(res):
                await res
    raise ultimo  # 5xx persistente após retries


def _engine_session():
    eng = create_async_engine(get_settings().database_url)
    return eng, async_sessionmaker(eng, expire_on_commit=False)


# ─── hooks do ledger (substituíveis em testes) ────────────────────────────────

async def _lease(*, job_id: int, concurso_id: int) -> dict | None:
    eng, S = _engine_session()
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)
        async with S.begin() as s:
            return await lease_concurso_unit(
                s, job_id=job_id, concurso_id=concurso_id, ack_wait_seconds=600
            )
    finally:
        await eng.dispose()


async def _mark_done(*, unit_id: int, job_id: int, arquivos_ok: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await mark_concurso_unit_done(
                s, unit_id=unit_id, job_id=job_id, arquivos_ok=arquivos_ok
            )
    finally:
        await eng.dispose()


async def _mark_failed(*, unit_id: int, job_id: int, error: str) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await mark_concurso_unit_failed(s, unit_id=unit_id, job_id=job_id, error=error)
    finally:
        await eng.dispose()


async def _is_paused(*, job_id: int) -> bool:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            return await is_concursos_paused(s, job_id=job_id)
    finally:
        await eng.dispose()


async def _release(*, unit_id: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await release_concurso_unit_to_pending(s, unit_id=unit_id)
    finally:
        await eng.dispose()


async def _enqueue_next(*, job_id: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            units = await list_enqueueable_concurso_units(s, job_id=job_id, limit=1)
        for u in units:
            # isolated_broker: enfileirar de DENTRO da task do worker exige um broker
            # próprio (a conexão de consumo não publica → ConnectionClosedError mata o
            # worker e a cadeia só anda por redelivery ~ack_wait). Espelha comentarios.py.
            await enqueue(
                coletar_arquivos_concurso,
                priority="default",
                isolated_broker=True,
                job_id=job_id,
                concurso_id=u["concurso_id"],
            )
    finally:
        await eng.dispose()


async def _discovery_done(*, job_id: int) -> int:
    """Grava discovery=done, sincroniza total_units com as units reais e
    refresca o status do job. Retorna o total de units conhecidas."""
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await set_concursos_job_discovery(s, job_id=job_id, status="done")
            total = (
                await s.execute(
                    text(
                        """
                        UPDATE tc_jobs
                        SET total_units = (
                              SELECT count(*) FROM tc_concurso_units WHERE job_id = :job_id
                            ),
                            updated_at = now()
                        WHERE id = :job_id
                        RETURNING total_units
                        """
                    ),
                    {"job_id": job_id},
                )
            ).scalar_one()
            await refresh_concursos_job_status(s, job_id=job_id)
        return int(total or 0)
    finally:
        await eng.dispose()


async def _marcar_job_done(*, job_id: int) -> None:
    eng, S = _engine_session()
    try:
        async with S.begin() as s:
            await s.execute(
                text(
                    """
                    UPDATE tc_jobs
                    SET status = 'done', finished_at = now(), updated_at = now()
                    WHERE id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
    finally:
        await eng.dispose()


# ─── núcleo testável ──────────────────────────────────────────────────────────

async def _call(fn: Any, **kw: Any) -> Any:
    """Chama fn(**kw) e awaita se for coroutine (suporta hooks sync em testes)."""
    r = fn(**kw)
    return (await r) if inspect.isawaitable(r) else r


async def _finalizar_descoberta(job_id: int) -> int:
    """Fecha a descoberta: discovery=done + total_units sincronizado + refresh
    de status. Caso especial: `refresh_concursos_job_status` nunca finaliza um
    job com `total_units == 0` (a condição de done exige `total_units > 0`) —
    uma busca sem resultados ficaria 'running' pra sempre. Aqui fechamos
    explicitamente como 'done'. Retorna o total de units."""
    import app.tasks.concursos as _self  # noqa: PLC0415

    total = await _call(_self._discovery_done, job_id=job_id)
    if total == 0:
        await _call(_self._marcar_job_done, job_id=job_id)
    return total


async def _processar_unit_concurso(
    job_id: int,
    concurso_id: int,
    *,
    download: Any = None,
    put_minio: Any = None,
    stat_minio: Any = None,
    post: Any = None,
    sleep: Any = asyncio.sleep,
) -> dict[str, Any]:
    """Processa 1 unit (concurso): baixa cada arquivo (pulando os já presentes
    no MinIO), sobe no MinIO e posta o payload de import no backend."""
    # Usa lookup no módulo para que monkeypatch funcione nos hooks
    import app.tasks.concursos as _self  # noqa: PLC0415

    if download is None:
        download = _self._download
    if put_minio is None:
        put_minio = _self._put_minio
    if stat_minio is None:
        stat_minio = _self._stat_minio
    if post is None:
        post = _self._post_import

    leased = await _call(_self._lease, job_id=job_id, concurso_id=concurso_id)
    if leased is None:
        return {"status": "skipped"}

    if await _call(_self._is_paused, job_id=job_id):
        await _call(_self._release, unit_id=leased["unit_id"])
        return {"status": "paused"}  # solta a unit e NÃO encadeia

    payload = leased["payload"]
    concurso = payload["concurso"]
    arquivos_in = payload.get("arquivos") or []

    try:
        arquivos_out: list[dict[str, Any]] = []
        for arq in arquivos_in:
            uuid = arq["uuid"]
            prefix = f"concursos/{uuid}"
            existente = await _call(stat_minio, key=prefix)
            if existente is not None:
                key = existente["key"]
                content_type = existente.get("content_type")
                size = existente.get("size")
            else:
                data, content_type, filename = await _call(download, url=CDN_ARQUIVO_URL.format(uuid=uuid))
                key = _object_key(uuid, content_type, filename or arq.get("nome_arquivo"))
                await _call(put_minio, key=key, data=data, ct=content_type)
                size = len(data)
                res = sleep(random.uniform(1, 3))  # sleep pode ser sync (testes) ou async
                if inspect.isawaitable(res):
                    await res

            arquivos_out.append(
                {
                    **arq,
                    "minio_object_key": key,
                    "content_type": content_type,
                    "tamanho_bytes": size,
                }
            )

        import_payload = {"concurso": concurso, "arquivos": arquivos_out}
        await _call(post, payload=import_payload)
    except Exception as exc:  # noqa: BLE001 — registra e segue o chain
        await _call(
            _self._mark_failed,
            unit_id=leased["unit_id"],
            job_id=leased["job_id"],
            error=str(exc)[:300],
        )
        await _call(_self._enqueue_next, job_id=job_id)
        log.warning("concursos.unit.failed", concurso_id=concurso_id, erro=str(exc)[:120])
        return {"status": "failed"}

    await _call(
        _self._mark_done,
        unit_id=leased["unit_id"],
        job_id=leased["job_id"],
        arquivos_ok=len(arquivos_out),
    )
    await _call(_self._enqueue_next, job_id=job_id)
    return {"status": "done", "arquivos_ok": len(arquivos_out)}


# ─── task Taskiq ─────────────────────────────────────────────────────────────

@broker_studia_default.task
async def coletar_arquivos_concurso(job_id: int, concurso_id: int) -> dict[str, Any]:
    return await _processar_unit_concurso(job_id, concurso_id)


@broker_studia_default.task
async def descobrir_concursos(job_id: int, filtros: list[dict[str, Any]]) -> dict[str, Any]:
    """Pagina a busca avançada do TC (filtros de banca/profissão/etc.), grava
    as units de concurso encontradas no ledger e dispara a 1ª unit de
    download. Idempotente: pode ser reenfileirada (job reusado) e retoma."""
    eng, S = _engine_session()
    try:
        async with eng.begin() as c:
            await ensure_ledger_schema(c)

        async with S.begin() as s:
            await s.execute(
                text(
                    """
                    UPDATE tc_jobs
                    SET status = 'running', finished_at = NULL, updated_at = now()
                    WHERE id = :job_id
                    """
                ),
                {"job_id": job_id},
            )

        async with S.begin() as s:
            await set_concursos_job_discovery(s, job_id=job_id, status="running")

        try:
            account = select_tc_account_for_task(TC_TASK_GUIA)
        except NoEligibleTcAccount as exc:
            async with S.begin() as s:
                await set_concursos_job_discovery(s, job_id=job_id, status="failed", error=str(exc))
                await s.execute(
                    text("UPDATE tc_jobs SET status = 'failed', last_error = :error, updated_at = now() "
                         "WHERE id = :job_id"),
                    {"job_id": job_id, "error": str(exc)[:500]},
                )
            raise

        account_id = account["id"]
        cookies = load_cookies_for_httpx(account_id=account_id)

        total_pages: int | None = None
        pagina = 1
        # Não usamos `async with TcClient(...)` aqui porque o relogin precisa
        # TROCAR o cliente NO MEIO do loop (várias páginas depois) — um `async
        # with` aninhado só em torno do fetch de retry fecharia a conexão ao
        # sair do bloco, quebrando as páginas seguintes. Fechamos manualmente
        # (client antigo antes de recriar; o atual sempre no finally).
        relogou_uma_vez = False
        client = TcClient(cookies)
        try:
            while pagina <= MAX_PAGINAS_DESCOBERTA:
                try:
                    data = await fetch_busca_avancada(client, filtros, pagina)
                except SessionExpired:
                    if relogou_uma_vez:
                        raise
                    relogou_uma_vez = True
                    log.warning("concursos.descoberta.relogin_retry", job_id=job_id, pagina=pagina)
                    await client.aclose()
                    await login_and_save_state(headless=True, account_id=account_id)
                    cookies = load_cookies_for_httpx(account_id=account_id)
                    client = TcClient(cookies)
                    data = await fetch_busca_avancada(client, filtros, pagina)

                if total_pages is None:
                    total_pages = int(data.get("totalPages") or 1)

                units = parse_busca_page(data)
                async with S.begin() as s:
                    await upsert_concurso_units(s, job_id=job_id, units=units)
                    await refresh_concursos_job_status(s, job_id=job_id)

                if pagina >= total_pages:
                    break
                pagina += 1
                await asyncio.sleep(random.uniform(2, 5))
        except Exception as exc:  # noqa: BLE001
            async with S.begin() as s:
                await set_concursos_job_discovery(s, job_id=job_id, status="failed", error=str(exc)[:500])
                await s.execute(
                    text("UPDATE tc_jobs SET status = 'failed', last_error = :error, updated_at = now() "
                         "WHERE id = :job_id"),
                    {"job_id": job_id, "error": str(exc)[:500]},
                )
            log.warning("concursos.descoberta.failed", job_id=job_id, erro=str(exc)[:200])
            raise
        finally:
            await client.aclose()

        import app.tasks.concursos as _self  # noqa: PLC0415

        total_units = await _finalizar_descoberta(job_id)
        if total_units > 0:
            await _self._enqueue_next(job_id=job_id)
        return {
            "status": "done",
            "paginas": pagina,
            "total_pages": total_pages,
            "total_units": total_units,
        }
    finally:
        await eng.dispose()
