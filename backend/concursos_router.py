"""Endpoints `/api/q/concursos/*` — Concursos coletados da busca avançada TC.

Espelha o padrão de `guias_router.py`: o scraper descobre concursos (edital +
arquivos: prova/gabarito/edital) e importa via `POST /importar` (service token
OU sessão admin). O backend só guarda os metadados + a referência ao objeto no
MinIO (os bytes já foram baixados pelo scraper) e serve como proxy fino para
disparar/acompanhar a coleta.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, get_current_user_opt, require_admin, require_user
from database import get_db
from minio_client import download_bytes
from models import AppSetting, TcConcurso, TcConcursoArquivo

router = APIRouter(prefix="/api/q/concursos", tags=["concursos"])


async def require_admin_or_service(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_opt),
) -> CurrentUser | None:
    """Autoriza se houver sessão de ADMIN válida OU header X-Internal-Token
    correto (mesmo padrão de `q_router.require_user_or_service`, mas aqui o
    resto do router é admin-only — `/importar` não pode ficar mais permissivo
    que `/coletar`, `/jobs`, etc. só porque é chamado pelo scraper).

    401 se não autenticado (sem sessão e sem token válido); 403 se autenticado
    mas não-admin — espelha `auth.require_admin`.
    """
    tok = os.getenv("STUDIA_INTERNAL_TOKEN") or ""
    if tok and request.headers.get("X-Internal-Token") == tok:
        return None  # chamada de serviço autorizada
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")
    if user.banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "conta suspensa")
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "acesso restrito a administradores")
    return user

SCRAPER_URL = os.getenv("SCRAPER_URL", "http://scraper:8090")

# Proxies curtos (padrão q_router.py:427-479): a UI não pode ficar presa
# esperando o scraper — se ele demorar, o job já foi registrado do lado dele
# (ou será retomado pelo supervisor) e a UI segue via polling de /jobs.
_ENQUEUE_TIMEOUT = httpx.Timeout(connect=3, read=8, write=5, pool=10)
_FILTROS_TIMEOUT = httpx.Timeout(connect=3, read=15, write=5, pool=20)

_SAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n]')
# Media type válido (token/token, simplificado do RFC 7231): qualquer coisa
# fora disso — inclusive CRLF de tentativa de header injection — vira
# application/octet-stream.
_SAFE_MEDIA_TYPE = re.compile(r"^[\w.+-]+/[\w.+-]+$")


# ─── Schemas ─────────────────────────────────────────────


class ArquivoImportarReq(BaseModel):
    tipo: str
    arquivo_id_externo: int
    uuid: str
    nome_arquivo: str
    minio_object_key: str
    content_type: str | None = None
    tamanho_bytes: int | None = None


class ConcursoImportarReq(BaseModel):
    concurso_id_externo: int
    edital_id_externo: int | None = None
    nome_completo: str
    url_concurso: str
    banca_nome: str | None = None
    orgao_sigla: str | None = None
    orgao_nome: str | None = None
    edital_nome: str | None = None
    ano: int | None = None
    data_aplicacao: str | None = Field(
        None, description='Data no formato TC: "%d/%m/%Y %H:%M:%S"'
    )
    escolaridade: str | None = None


class ImportarReq(BaseModel):
    concurso: ConcursoImportarReq
    arquivos: list[ArquivoImportarReq] = Field(default_factory=list)


class ColetarReq(BaseModel):
    filtros: list[dict[str, Any]] = Field(default_factory=list)


# ─── Helpers ─────────────────────────────────────────────


def _parse_data_aplicacao(valor: str | None) -> datetime | None:
    """Parseia a data no formato do TC; nunca derruba o import por data ruim."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def _sanitize_filename(nome: str) -> str:
    nome = _SAFE_FILENAME.sub("_", nome or "").strip()
    return nome or "arquivo"


def _sanitize_media_type(content_type: str | None) -> str:
    """content_type vem da fonte externa e vira header — só passa token/token."""
    ct = (content_type or "").strip()
    return ct if _SAFE_MEDIA_TYPE.match(ct) else "application/octet-stream"


def _build_content_disposition(nome_arquivo: str) -> str:
    """Content-Disposition seguro para nomes não-Latin-1.

    Starlette codifica headers em latin-1: um nome com "—"/"☂" estouraria
    UnicodeEncodeError (500). Emite `filename=` ASCII-safe (fallback universal)
    + `filename*=UTF-8''...` (RFC 5987) com o nome original URL-encoded — os
    navegadores modernos preferem o segundo.
    """
    nome = _sanitize_filename(nome_arquivo)
    ascii_nome = nome.encode("ascii", "ignore").decode("ascii").strip() or "arquivo"
    utf8_nome = urllib.parse.quote(nome, safe="")
    return f"attachment; filename=\"{ascii_nome}\"; filename*=UTF-8''{utf8_nome}"


def _arquivo_dict(a: TcConcursoArquivo) -> dict[str, Any]:
    return {
        "id": a.id,
        "tipo": a.tipo,
        "nome_arquivo": a.nome_arquivo,
        "content_type": a.content_type,
        "tamanho_bytes": a.tamanho_bytes,
    }


def _concurso_dict(c: TcConcurso) -> dict[str, Any]:
    return {
        "id": c.id,
        "concurso_id_externo": c.concurso_id_externo,
        "nome_completo": c.nome_completo,
        "url_concurso": c.url_concurso,
        "banca_nome": c.banca_nome,
        "orgao_sigla": c.orgao_sigla,
        "orgao_nome": c.orgao_nome,
        "edital_nome": c.edital_nome,
        "ano": c.ano,
        "data_aplicacao": c.data_aplicacao.isoformat() if c.data_aplicacao else None,
        "escolaridade": c.escolaridade,
        "arquivos": [_arquivo_dict(a) for a in c.arquivos],
    }


async def _table_exists(db: AsyncSession, qualified_name: str) -> bool:
    reg = (await db.execute(text("SELECT to_regclass(:n)"), {"n": qualified_name})).scalar()
    return reg is not None


# ─── Endpoints ───────────────────────────────────────────


@router.post("/importar")
async def importar_concurso(
    req: ImportarReq,
    _user: CurrentUser | None = Depends(require_admin_or_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upsert idempotente de um concurso + seus arquivos (service token OU admin).

    Casa por `concurso_id_externo`; arquivos casam por
    `(concurso_id, arquivo_id_externo)`. Reimportar atualiza os campos em vez
    de duplicar — o scraper pode reenviar o mesmo concurso a cada rodada de
    coleta sem medo.
    """
    dados = req.concurso
    concurso = (
        await db.execute(
            select(TcConcurso).where(
                TcConcurso.concurso_id_externo == dados.concurso_id_externo
            )
        )
    ).scalar_one_or_none()

    campos = dados.model_dump(exclude={"data_aplicacao"})
    campos["data_aplicacao"] = _parse_data_aplicacao(dados.data_aplicacao)
    raw = dados.model_dump()

    if concurso is None:
        concurso = TcConcurso(**campos, raw_json=raw)
        db.add(concurso)
    else:
        for k, v in campos.items():
            setattr(concurso, k, v)
        concurso.raw_json = raw
    await db.flush()

    # Nota: arquivo_id_externo duplicado DENTRO do mesmo payload não erra —
    # o SELECT com autoflush enxerga o primeiro insert e o segundo sobrescreve
    # (last wins). Aceitável: o scraper é a única fonte e não deve duplicar.
    for arq in req.arquivos:
        existente = (
            await db.execute(
                select(TcConcursoArquivo).where(
                    TcConcursoArquivo.concurso_id == concurso.id,
                    TcConcursoArquivo.arquivo_id_externo == arq.arquivo_id_externo,
                )
            )
        ).scalar_one_or_none()
        if existente is None:
            db.add(TcConcursoArquivo(concurso_id=concurso.id, **arq.model_dump()))
        else:
            for k, v in arq.model_dump().items():
                setattr(existente, k, v)

    await db.commit()
    return {"ok": True, "concurso_id": concurso.id, "arquivos": len(req.arquivos)}


@router.get("")
async def listar_concursos(
    busca: str | None = None,
    page: int = 1,
    page_size: int = 50,
    _user: CurrentUser = Depends(require_user),  # leitura: qualquer logado
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lista concursos importados (admin), paginado, mais recentes primeiro."""
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    base = select(TcConcurso)
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        base = base.where(
            or_(
                TcConcurso.nome_completo.ilike(termo),
                TcConcurso.orgao_nome.ilike(termo),
                TcConcurso.orgao_sigla.ilike(termo),
                TcConcurso.banca_nome.ilike(termo),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(TcConcurso.ano.desc().nullslast(), TcConcurso.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()

    return {"items": [_concurso_dict(c) for c in rows], "total": int(total)}


@router.get("/catalogo")
async def catalogo_concursos(
    busca: str | None = None,
    page: int = 1,
    page_size: int = 24,
    _user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Catálogo para o Mapa da Aprovação (qualquer usuário logado).

    Diferente de `listar_concursos` (admin), só mostra concursos que têm
    arquivo de EDITAL — sem edital não há o que extrair.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    tem_edital = select(TcConcursoArquivo.concurso_id).where(
        TcConcursoArquivo.tipo == "EDITAL"
    )
    base = select(TcConcurso).where(TcConcurso.id.in_(tem_edital))
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        base = base.where(
            or_(
                TcConcurso.nome_completo.ilike(termo),
                TcConcurso.orgao_nome.ilike(termo),
                TcConcurso.orgao_sigla.ilike(termo),
                TcConcurso.banca_nome.ilike(termo),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(TcConcurso.ano.desc().nullslast(), TcConcurso.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()
    return {"items": [_concurso_dict(c) for c in rows], "total": int(total)}


@router.get("/jobs")
async def listar_jobs_concursos(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Progresso dos jobs de coleta de concursos para a UI acompanhar. (admin)

    Consulta o ledger do scraper (`tc_jobs`, `kind='concursos'`) — tabela que
    NÃO existe via Alembic (é criada/migrada pelo scraper). Antes da primeira
    coleta o backend ainda não viu essa tabela: devolve lista vazia em vez de
    500.
    """
    if not await _table_exists(db, "public.tc_jobs"):
        return {"jobs": []}

    rows = (
        await db.execute(
            text(
                """
                SELECT j.id AS job_id, j.status,
                       COALESCE(j.paused_by_user, false) AS paused,
                       j.params ->> 'discovery' AS discovery,
                       j.params -> 'filtros' AS filtros,
                       j.total_units, j.done_units, j.failed_units, j.blocked_units,
                       j.updated_at
                FROM tc_jobs j
                WHERE j.kind = 'concursos'
                ORDER BY j.updated_at DESC, j.id DESC
                """
            )
        )
    ).mappings().all()

    jobs = [
        {
            "job_id": r["job_id"],
            "status": r["status"],
            "paused": bool(r["paused"]),
            "filtros": r["filtros"],
            "discovery": r["discovery"],
            "total_units": r["total_units"],
            "done_units": r["done_units"],
            "failed_units": r["failed_units"],
            "blocked_units": r["blocked_units"],
            "atualizado_em": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]
    return {"jobs": jobs}


@router.post("/coletar", status_code=status.HTTP_202_ACCEPTED)
async def coletar_concursos(
    req: ColetarReq,
    _admin: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    """Enfileira a descoberta+coleta de concursos no scraper. (admin)

    Passthrough puro do retorno do scraper: `{job_id,status,total_units,
    enqueued_units,message}`.
    """
    try:
        async with httpx.AsyncClient(timeout=_ENQUEUE_TIMEOUT) as c:
            r = await c.post(
                f"{SCRAPER_URL}/enqueue/concursos", json={"filtros": req.filtros}
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            504,
            "scraper demorou para confirmar o job; tente novamente em alguns segundos.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc

    if r.status_code != 200:
        status_code = 409 if r.status_code == 409 else 502
        raise HTTPException(status_code, f"scraper falhou: {r.status_code} {r.text[:300]}")
    return r.json()


# Cache dos filtros (bancas/profissões) em app_settings: cada miss custa 2
# requests na sessão TC do scraper, e a lista muda raramente — 72h de TTL.
FILTROS_CACHE_KEY = "tc_concursos.filtros_cache"
FILTROS_CACHE_TTL = timedelta(hours=72)


def _utcnow_naive() -> datetime:
    """UTC naive (colunas DateTime sem tz), sem o utcnow() deprecado do 3.12."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/filtros")
async def filtros_concursos(
    refresh: bool = False,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bancas/profissões disponíveis para filtrar a coleta. (admin)

    Servido do cache em `app_settings` (TTL 72h); só consulta o scraper (que
    vai à fonte externa com sessão) em miss/expiração ou `?refresh=true`.
    Scraper indisponível + cache existente (mesmo vencido) → serve o cache.
    """
    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == FILTROS_CACHE_KEY))
    ).scalar_one_or_none()
    agora = _utcnow_naive()
    if (
        row is not None
        and not refresh
        and row.updated_at is not None
        and agora - row.updated_at < FILTROS_CACHE_TTL
    ):
        return json.loads(row.value)

    try:
        async with httpx.AsyncClient(timeout=_FILTROS_TIMEOUT) as c:
            r = await c.get(f"{SCRAPER_URL}/tc/concursos/filtros")
        if r.status_code != 200:
            raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:300]}")
        data = r.json()
    except HTTPException:
        if row is not None:
            return json.loads(row.value)  # cache velho é melhor que erro
        raise
    except httpx.TimeoutException as exc:
        if row is not None:
            return json.loads(row.value)
        raise HTTPException(504, "scraper demorou para responder os filtros.") from exc
    except httpx.HTTPError as exc:
        if row is not None:
            return json.loads(row.value)
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc

    valor = json.dumps(data, ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=FILTROS_CACHE_KEY, value=valor, updated_at=agora))
    else:
        row.value = valor
        # updated_at explícito: se o payload vier idêntico, o onupdate não
        # dispara (sem UPDATE) e o cache pareceria eternamente vencido.
        row.updated_at = agora
    await db.commit()
    return data


@router.get("/arquivo/{arquivo_id}")
async def baixar_arquivo(
    arquivo_id: int,
    _user: CurrentUser = Depends(require_user),  # download local (MinIO), nunca aciona a fonte
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream do arquivo (edital/prova/gabarito) hospedado no MinIO. (admin)"""
    arq = (
        await db.execute(
            select(TcConcursoArquivo).where(TcConcursoArquivo.id == arquivo_id)
        )
    ).scalar_one_or_none()
    if not arq:
        raise HTTPException(404, "Arquivo não encontrado")

    try:
        data = download_bytes(arq.minio_object_key)
    except Exception as exc:  # objeto ausente/MinIO fora do ar
        raise HTTPException(502, f"falha ao baixar arquivo do MinIO: {exc}") from exc

    return Response(
        content=data,
        media_type=_sanitize_media_type(arq.content_type),
        headers={"Content-Disposition": _build_content_disposition(arq.nome_arquivo)},
    )
