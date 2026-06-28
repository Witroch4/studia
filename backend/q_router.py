"""Endpoints `/api/q/*` para witdev-tec-master.

Proxy fino sobre Meilisearch + Postgres. Replicam o padrão arquitetural do TC:
- `/api/q/count` → contagem leve + facetas (cacheável)
- `/api/q/search` → lista paginada
- `/api/q/{id}` → detalhe de questão
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import Integer, bindparam, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import CurrentUser, get_current_user_opt, require_admin, require_user
from forum_personas import sortear_persona
from forum_pseudonimo import pseudonimo
from database import get_db
from entitlements import acesso_pro_ativo, garantir_pode_resolver, meta_diaria_status, resumo_limite
from models import (
    Alternativa,
    Banca,
    CalculadoraHistorico,
    CadernoQuestoes,
    CadernoSalvo,
    Cargo,
    ComentarioVoto,
    Guia,
    GuiaCaderno,
    Materia,
    Orgao,
    Questao,
    QuestaoAnotacao,
    QuestaoComentario,
    QuestaoFavorita,
    QuestaoTcImport,
    Resolucao,
)

import re as _re
import uuid as _uuid
from minio_client import upload_bytes, get_presigned_url

router = APIRouter(prefix="/api/q", tags=["questoes"])

MEILI_URL = os.getenv("MEILI_URL", "http://localhost:7700")
MEILI_KEY = os.getenv("MEILI_KEY", "dev_master_key_studia_2026")
SCRAPER_URL = os.getenv("SCRAPER_URL", "http://scraper:8090")

KNOWN_TC_CADERNO_TOTALS: dict[int, int] = {
    95872872: 29_774,
    95872884: 15_298,
    95872821: 22_455,
    95872853: 11_364,
}

DEFAULT_FACETS = [
    "banca", "orgao", "cargo", "ano", "materia", "assuntos", "tipo", "status",
    "area", "formacao", "escolaridade", "regiao",
]

MEILI_INDEX = "questoes"

# Grupos de facetas para disjunctive faceting (padrão TC): a contagem de cada
# grupo é calculada IGNORANDO os filtros do próprio grupo (mas respeitando os
# demais). Sem isso, marcar 1 assunto zera todas as outras matérias/bancas.
# `tipo` e `status_excluir` NÃO entram em nenhum grupo → ficam globais (o radio
# objetivas/discursivas e "remover anuladas" valem para todas as contagens).
FACET_GROUPS: dict[str, list[str]] = {
    "materia_assunto": ["materia", "assuntos"],  # a árvore ignora ambos
    "banca": ["banca"],
    "orgao_cargo": ["orgao", "cargo"],
    "ano": ["ano"],
    "area": ["area"],
    "escolaridade": ["escolaridade"],
    "formacao": ["formacao"],
    "regiao": ["regiao"],
}

# Pasta padrão onde cadernos avulsos importados do TC são montados.
PASTA_IMPORTADOS = "Importados do TC"


_CADERNO_RE = _re.compile(r"/cadernos/(\d+)")


def extrair_caderno_id(url_ou_id: str) -> int:
    """Aceita URL completa TC ou só o número."""
    s = (url_ou_id or "").strip()
    if s.isdigit():
        return int(s)
    m = _CADERNO_RE.search(s)
    if not m:
        raise HTTPException(400, f"URL/ID de caderno inválido: {s!r}")
    return int(m.group(1))


# ─── Schemas ─────────────────────────────────────────────


class CountReq(BaseModel):
    filtros: dict[str, list[str] | list[int]] = Field(default_factory=dict)
    q: str = ""
    favoritas: bool = False


class SearchReq(CountReq):
    page: int = 1
    page_size: int = 20
    sort: list[str] | None = None


def _meili_quote(v: str) -> str:
    """Valor string para filtro Meili, com aspas e escapes corretos.

    Nomes de assunto podem conter aspas duplas (ex.: `Vocábulo "Como"`). Sem
    escapar `\\` e `"`, o filtro vira sintaxe inválida e o Meili responde 400 —
    derrubando a query inteira (count/search/gerar caderno).
    """
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _to_meili_filter(filtros: dict[str, list]) -> str | None:
    parts: list[str] = []
    for k, vals in filtros.items():
        if not vals:
            continue
        quoted = [_meili_quote(v) if isinstance(v, str) else str(v) for v in vals]
        if k == "status_excluir":
            # ["ANULADA", ...] → status != "ANULADA" AND ...
            parts.append("(" + " AND ".join(f"status != {v}" for v in quoted) + ")")
        else:
            parts.append("(" + " OR ".join(f"{k} = {v}" for v in quoted) + ")")
    return " AND ".join(parts) if parts else None


async def _filtro_favoritas(db: AsyncSession, owner_uid: str) -> str | None:
    """Filtro Meili `id IN [...]` com as favoritas DO usuário; None se não há nenhuma."""
    ids = (
        await db.execute(
            select(QuestaoFavorita.questao_id).where(QuestaoFavorita.owner_uid == owner_uid)
        )
    ).scalars().all()
    if not ids:
        return None
    return "id IN [" + ", ".join(str(i) for i in ids) + "]"


async def _caderno_acessivel(
    db: AsyncSession, caderno_id: int, user: CurrentUser
) -> CadernoQuestoes:
    """Carrega um caderno se o usuário pode acessá-lo, senão 404.

    Acesso = é dono (owner_uid == user.id) OU o caderno faz parte do catálogo
    compartilhado (existe um GuiaCaderno apontando para ele — estudo via aba
    Guias). Caso contrário, 404 (não revela cadernos privados de outros).

    Guias PRO only: se o caderno só aparece em guias pro-only, exige conta PRO
    (admin/assinatura/voucher); 403 caso contrário. Basta um guia NÃO pro-only
    conter o caderno para liberar a todos.
    """
    cad = (
        await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))
    ).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    if cad.owner_uid == user.id:
        return cad
    # Guias do catálogo que contêm este caderno (com a flag pro_only de cada um).
    pro_flags = (
        await db.execute(
            select(Guia.pro_only)
            .join(GuiaCaderno, GuiaCaderno.guia_id == Guia.id)
            .where(GuiaCaderno.caderno_id == caderno_id)
        )
    ).scalars().all()
    if not pro_flags:
        raise HTTPException(404, "caderno não encontrado")
    if any(not p for p in pro_flags):
        return cad  # algum guia livre contém o caderno → liberado a todos
    # Só guias pro-only: exige PRO (admin sempre passa).
    if user.is_admin or await acesso_pro_ativo(db, user.id):
        return cad
    raise HTTPException(403, "Conteúdo exclusivo para assinantes PRO.")


def _as_date(value: Any) -> date:
    """Normaliza o retorno de func.date (str no SQLite, date no Postgres) p/ date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _compute_streak(active_days: set[date], today: date) -> int:
    """Dias consecutivos de estudo terminando em hoje (ou ontem, com tolerância).

    `active_days` = conjunto de dias (date) com ≥1 resolução. Se não houve
    atividade hoje nem ontem, o streak está zerado. Caso contrário, conta para
    trás a partir do dia mais recente com atividade (hoje ou ontem).
    """
    if not active_days:
        return 0
    ontem = today - timedelta(days=1)
    if today in active_days:
        cursor = today
    elif ontem in active_days:
        cursor = ontem
    else:
        return 0
    streak = 0
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def _meili_search(payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(
            f"{MEILI_URL}/indexes/{MEILI_INDEX}/search",
            headers={"Authorization": f"Bearer {MEILI_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()


async def _meili_multi_search(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(
            f"{MEILI_URL}/multi-search",
            headers={"Authorization": f"Bearer {MEILI_KEY}"},
            json={"queries": queries},
        )
        r.raise_for_status()
        return r.json().get("results", [])


def _build_count_queries(
    filtros: dict[str, list], q: str, fav_filter: str | None
) -> list[dict[str, Any]]:
    """Monta as queries do `/multi-search` para contagem com disjunctive faceting.

    - Query 0 = base: filtro completo, `limit:0`, sem facets → `total`.
    - Demais = 1 por grupo de `FACET_GROUPS`, removendo do filtro os campos do
      próprio grupo (mantendo `tipo`/`status_excluir`/favoritas/`q` globais) e
      pedindo só as facetas daquele grupo. Cada grupo conta ignorando seus
      próprios filtros — assim selecionar um assunto não zera as outras matérias.
    """
    def _filtro(drop: set[str]) -> str | None:
        sub = {k: v for k, v in filtros.items() if k not in drop}
        f = _to_meili_filter(sub)
        if fav_filter:
            f = f"{f} AND {fav_filter}" if f else fav_filter
        return f

    base: dict[str, Any] = {"indexUid": MEILI_INDEX, "q": q, "limit": 0}
    base_filter = _filtro(set())
    if base_filter:
        base["filter"] = base_filter
    queries = [base]

    for campos in FACET_GROUPS.values():
        sub: dict[str, Any] = {
            "indexUid": MEILI_INDEX, "q": q, "limit": 0, "facets": campos,
        }
        sub_filter = _filtro(set(campos))
        if sub_filter:
            sub["filter"] = sub_filter
        queries.append(sub)
    return queries


# ─── Dependência de auth: sessão OU token de serviço ─────


async def require_user_or_service(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_opt),
) -> CurrentUser | None:
    """Autoriza se houver sessão válida OU header X-Internal-Token correto.

    Permite que o worker do scraper (Fase 2) chame endpoints de importação sem
    sessão de usuário. Um token vazio/não configurado NUNCA autoriza.
    """
    if user is not None:
        return user
    tok = os.getenv("STUDIA_INTERNAL_TOKEN") or ""
    if tok and request.headers.get("X-Internal-Token") == tok:
        return None  # chamada de serviço autorizada
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")


# ─── Endpoints ───────────────────────────────────────────


@router.post("/count")
async def count(
    req: CountReq,
    user: CurrentUser | None = Depends(get_current_user_opt),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Padrão TC: contagem leve + facetas (disjunctive) para painel UI.

    Usa `/multi-search`: o `total` vem da query base (todos os filtros) e cada
    grupo de facetas é contado ignorando os filtros do próprio grupo. Assim
    marcar um assunto não zera as outras matérias/bancas na árvore.
    """
    fav_filter: str | None = None
    if req.favoritas:
        fav_filter = await _filtro_favoritas(db, user.id) if user else None
        if fav_filter is None:
            return {"total": 0, "facets": {}, "ms": 0}

    queries = _build_count_queries(req.filtros, req.q, fav_filter)
    results = await _meili_multi_search(queries)
    if not results:
        return {"total": 0, "facets": {}, "ms": 0}

    facets: dict[str, Any] = {}
    ms = 0
    for res in results:
        ms = max(ms, res.get("processingTimeMs", 0))
        for campo, dist in (res.get("facetDistribution") or {}).items():
            facets[campo] = dist
    return {
        "total": results[0].get("estimatedTotalHits", 0),
        "facets": facets,
        "ms": ms,
    }


@router.post("/search")
async def search(
    req: SearchReq,
    user: CurrentUser | None = Depends(get_current_user_opt),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lista paginada de questões + facetas."""
    payload = {
        "q": req.q,
        "limit": req.page_size,
        "offset": (req.page - 1) * req.page_size,
        "facets": DEFAULT_FACETS,
        "attributesToRetrieve": [
            "id", "id_externo", "enunciado", "banca", "orgao",
            "cargo", "ano", "materia", "assuntos", "tipo", "gabarito", "status",
        ],
    }
    f = _to_meili_filter(req.filtros)
    if req.favoritas:
        fav = await _filtro_favoritas(db, user.id) if user else None
        if fav is None:
            return {"hits": [], "total": 0, "facets": {}, "ms": 0}
        f = f"{f} AND {fav}" if f else fav
    if f:
        payload["filter"] = f
    if req.sort:
        payload["sort"] = req.sort
    data = await _meili_search(payload)
    return {
        "hits": data.get("hits", []),
        "total": data.get("estimatedTotalHits", 0),
        "facets": data.get("facetDistribution", {}),
        "ms": data.get("processingTimeMs", 0),
    }


class ColetarReq(BaseModel):
    url: str = Field(..., description="URL do caderno TC ou apenas o ID")
    relogin: bool = Field(False, description="Refazer login antes (se trocou IP)")
    expected_total: int | None = Field(None, description="Total conhecido do caderno, se já houver")
    page_size: int = Field(200, ge=1, le=200, description="Tamanho da faixa TC")


@router.post("/coletar", status_code=status.HTTP_202_ACCEPTED)
async def coletar(req: ColetarReq, _admin: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Enfileira a coleta de um caderno TC no scraper TaskIQ/NATS. (admin)"""
    caderno_id = extrair_caderno_id(req.url)
    expected_total = req.expected_total or KNOWN_TC_CADERNO_TOTALS.get(caderno_id)

    if expected_total is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Informe o total esperado do caderno. A UI nao faz descoberta sincrona no TC.",
        )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=3, read=8, write=5, pool=10)) as c:
            r = await c.post(
                f"{SCRAPER_URL}/enqueue/caderno",
                json={
                    "caderno_id": caderno_id,
                    "expected_total": expected_total,
                    "page_size": req.page_size,
                    "enqueue_limit": 1,
                    "discover_total": False,
                    "relogin": req.relogin,
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            504,
            "scraper demorou para confirmar o job; a UI nao ficou presa. Tente novamente em alguns segundos.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponivel: {exc}") from exc

    if r.status_code != 200:
        raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:300]}")
    job = r.json()

    message = "job registrado; processamento segue em background"
    if job.get("status") == "blocked":
        message = "job registrado; TC esta em cooldown/bloqueio e o supervisor retomara a faixa exata automaticamente"
    elif job.get("enqueued_units", 0) > 0:
        message = "job registrado; primeira faixa enfileirada e UI liberada"

    return {
        "caderno_id": caderno_id,
        "expected_total": expected_total,
        "job_id": job["job_id"],
        "status": job["status"],
        "total_units": job["total_units"],
        "enqueued_units": job["enqueued_units"],
        "message": message,
    }


@router.post("/cadernos/{caderno_id}/importar-comentarios-tc", status_code=status.HTTP_202_ACCEPTED)
async def importar_comentarios_caderno(
    caderno_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Enfileira a coleta em massa de comentários do caderno no scraper (admin).

    Comportamento idempotente intencional: re-despachar um caderno cujo job de
    comentários já está "done" retorna status="done", enqueued_units=0 sem 409.
    O índice UNIQUE sobre job ativo e as unidades já "done" garantem que nada
    novo é enfileirado — não é bug, é dedup pelo scraper.
    """
    cad = (await db.execute(
        select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id)
    )).scalar_one_or_none()
    if cad is None:
        raise HTTPException(404, "caderno não encontrado")
    qids = list(cad.question_ids or [])
    if not qids:
        raise HTTPException(422, "caderno sem questões")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3, read=15, write=5, pool=20)
        ) as c:
            r = await c.post(
                f"{SCRAPER_URL}/enqueue/comentarios",
                json={"caderno_id": caderno_id, "questao_ids": qids},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:300]}")
    job = r.json()
    return {
        "caderno_id": caderno_id,
        "job_id": job["job_id"],
        "status": job["status"],
        "total_units": job["total_units"],
        "enqueued_units": job["enqueued_units"],
    }


@router.get("/coletar/jobs")
async def listar_jobs_coleta(
    caderno_id: int | None = None,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Resumo dos jobs ativos de coleta TC para a UI acompanhar progresso real. (admin)"""
    caderno_where = ""
    params: dict[str, Any] = {}
    if caderno_id is not None:
        caderno_where = "AND CAST(j.external_id AS INTEGER) = :caderno_id"
        params["caderno_id"] = caderno_id

    job_rows = (
        await db.execute(
            text(
                f"""
                SELECT
                  j.id AS job_id,
                  CAST(j.external_id AS INTEGER) AS caderno_id,
                  j.status,
                  COALESCE(j.paused_by_user, false) AS paused,
                  j.expected_total,
                  j.total_units,
                  j.done_units,
                  j.failed_units,
                  j.blocked_units,
                  j.updated_at,
                  j.params ->> 'caderno_nome' AS caderno_nome,
                  EXISTS (
                    SELECT 1 FROM tc_caderno_questoes m
                    WHERE m.caderno_id = CAST(j.external_id AS INTEGER)
                  ) AS pode_montar,
                  COALESCE(SUM(CASE WHEN u.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_units,
                  COALESCE(SUM(CASE WHEN u.status = 'queued' THEN 1 ELSE 0 END), 0) AS queued_units,
                  COALESCE(SUM(CASE WHEN u.status = 'running' THEN 1 ELSE 0 END), 0) AS running_units,
                  COALESCE(SUM(CASE WHEN u.status = 'done' THEN u.questoes_ok ELSE 0 END), 0) AS questoes_ok_done
                FROM tc_jobs j
                LEFT JOIN tc_caderno_units u ON u.job_id = j.id
                WHERE j.kind = 'caderno'
                  AND (
                    j.status IN ('pending', 'running', 'blocked')
                    OR (
                      j.status = 'done'
                      AND NOT EXISTS (
                        SELECT 1 FROM cadernos_questoes cq
                        WHERE cq.tc_caderno_id = CAST(j.external_id AS INTEGER)
                      )
                    )
                  )
                  {caderno_where}
                GROUP BY
                  j.id,
                  j.external_id,
                  j.status,
                  j.paused_by_user,
                  j.expected_total,
                  j.total_units,
                  j.done_units,
                  j.failed_units,
                  j.blocked_units,
                  j.updated_at,
                  j.params
                ORDER BY j.updated_at DESC, j.id DESC
                """
            ),
            params,
        )
    ).mappings().all()

    if not job_rows:
        return {"jobs": []}

    job_ids = [int(row["job_id"]) for row in job_rows]
    unit_rows = (
        await db.execute(
            text(
                """
                SELECT
                  job_id,
                  inicio,
                  page_size,
                  status,
                  attempts,
                  block_reason,
                  blocked_until,
                  leased_until
                FROM tc_caderno_units
                WHERE job_id IN :job_ids
                  AND status IN ('blocked', 'running', 'queued')
                ORDER BY job_id, inicio
                """
            ).bindparams(bindparam("job_ids", expanding=True)),
            {"job_ids": job_ids},
        )
    ).mappings().all()

    units_by_job: dict[int, list[dict[str, Any]]] = {}
    for row in unit_rows:
        units_by_job.setdefault(int(row["job_id"]), []).append(
            {
                "inicio": int(row["inicio"]),
                "page_size": int(row["page_size"]),
                "status": str(row["status"]),
                "attempts": int(row["attempts"] or 0),
                "block_reason": row["block_reason"],
                "blocked_until": row["blocked_until"],
                "leased_until": row["leased_until"],
            }
        )

    jobs: list[dict[str, Any]] = []
    for row in job_rows:
        total_units = int(row["total_units"] or 0)
        done_units = int(row["done_units"] or 0)
        expected_total = int(row["expected_total"] or 0)
        questoes_ok_done = int(row["questoes_ok_done"] or 0)
        blocked_ranges = [
            unit for unit in units_by_job.get(int(row["job_id"]), []) if unit["status"] == "blocked"
        ]
        running_ranges = [
            unit for unit in units_by_job.get(int(row["job_id"]), []) if unit["status"] == "running"
        ]
        queued_ranges = [
            unit for unit in units_by_job.get(int(row["job_id"]), []) if unit["status"] == "queued"
        ]
        jobs.append(
            {
                "job_id": int(row["job_id"]),
                "caderno_id": int(row["caderno_id"]),
                "caderno_nome": row["caderno_nome"] or None,
                "pode_montar": bool(row["pode_montar"]),
                "status": str(row["status"]),
                "paused": bool(row["paused"]),
                "expected_total": expected_total,
                "total_units": total_units,
                "done_units": done_units,
                "failed_units": int(row["failed_units"] or 0),
                "blocked_units": int(row["blocked_units"] or 0),
                "pending_units": int(row["pending_units"] or 0),
                "queued_units": int(row["queued_units"] or 0),
                "running_units": int(row["running_units"] or 0),
                "questoes_ok_done": questoes_ok_done,
                "pct_units_done": round((done_units / total_units) * 100, 2) if total_units else 0.0,
                "pct_questions_done": round((questoes_ok_done / expected_total) * 100, 2)
                if expected_total
                else 0.0,
                "updated_at": row["updated_at"],
                "blocked_ranges": blocked_ranges,
                "running_ranges": running_ranges,
                "queued_ranges": queued_ranges,
            }
        )

    return {"jobs": jobs}


@router.get("/coletar/comentario-jobs")
async def listar_comentario_jobs(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Jobs de coleta de comentários para a UI acompanhar. (admin)"""
    rows = (await db.execute(text(
        """
        SELECT j.id AS job_id, CAST(j.external_id AS INTEGER) AS caderno_id,
               j.status, COALESCE(j.paused_by_user,false) AS paused,
               j.total_units, j.done_units, j.failed_units, j.blocked_units,
               j.created_at, j.updated_at,
               COALESCE(SUM(CASE WHEN u.status='pending' THEN 1 ELSE 0 END),0) AS pending_units,
               COALESCE(SUM(CASE WHEN u.status='queued'  THEN 1 ELSE 0 END),0) AS queued_units,
               COALESCE(SUM(CASE WHEN u.status='running' THEN 1 ELSE 0 END),0) AS running_units,
               COALESCE(SUM(u.coments_alunos + u.coments_professores),0) AS coments_total,
               (SELECT u2.questao_id FROM tc_comentario_units u2
                 WHERE u2.job_id = j.id AND u2.status IN ('running','queued')
                 ORDER BY u2.updated_at DESC LIMIT 1) AS questao_atual
        FROM tc_jobs j
        LEFT JOIN tc_comentario_units u ON u.job_id = j.id
        WHERE j.kind='comentarios'
          AND j.status IN ('pending','running','blocked','done')
        GROUP BY j.id, j.external_id, j.status, j.paused_by_user,
                 j.total_units, j.done_units, j.failed_units, j.blocked_units,
                 j.created_at, j.updated_at
        ORDER BY j.updated_at DESC, j.id DESC
        """
    ))).mappings().all()
    jobs = []
    for r in rows:
        total = r["total_units"] or 0
        pct = round((r["done_units"] or 0) / total * 100, 2) if total else 0.0
        jobs.append({**{k: r[k] for k in (
            "job_id", "caderno_id", "status", "paused", "total_units", "done_units",
            "failed_units", "blocked_units", "pending_units", "queued_units",
            "running_units", "coments_total")},
            "pct_units_done": pct,
            "questao_atual": r["questao_atual"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        })
    return {"jobs": jobs}


@router.get("/coletar/comentario-jobs/{job_id}/eventos")
async def comentario_job_eventos(
    job_id: int, limit: int = 20,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Últimas units (eventos) de um job de comentários, p/ o feed da UI. (admin)"""
    limit = max(1, min(limit, 50))
    rows = (await db.execute(text(
        """
        SELECT u.questao_id, q.id_externo, u.status, u.coments_alunos,
               u.coments_professores, u.block_reason, u.last_error, u.updated_at
        FROM tc_comentario_units u
        LEFT JOIN questoes q ON q.id = u.questao_id
        WHERE u.job_id = :job_id
        ORDER BY u.updated_at DESC
        LIMIT :lim
        """
    ), {"job_id": job_id, "lim": limit})).mappings().all()
    eventos = [{
        "questao_id": r["questao_id"], "id_externo": r["id_externo"],
        "status": r["status"], "coments_alunos": r["coments_alunos"],
        "coments_professores": r["coments_professores"],
        "block_reason": r["block_reason"], "last_error": r["last_error"],
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    } for r in rows]
    return {"eventos": eventos}


class MaterializarCadernoReq(BaseModel):
    nome: str | None = None
    forcar: bool = False


@router.post("/coletar/{caderno_id}/materializar")
async def materializar_caderno_avulso(
    caderno_id: int,
    req: MaterializarCadernoReq | None = None,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Monta um caderno avulso do TC como `CadernoQuestoes` na pasta padrão.

    Usa a ordem real das questões coletadas (`tc_caderno_questoes.posicao`) e o
    nome capturado do TC (`tc_jobs.params.caderno_nome`), editável via `nome`.
    Idempotente por `tc_caderno_id`. Por padrão exige coleta concluída (job
    `done`); use `forcar=true` para montar parcial.
    """
    forcar = bool(req and req.forcar)

    ids = (
        await db.execute(
            text(
                """
                SELECT questao_id
                FROM tc_caderno_questoes
                WHERE caderno_id = :cid
                ORDER BY posicao
                """
            ),
            {"cid": caderno_id},
        )
    ).scalars().all()
    ids = [int(i) for i in ids]

    job = (
        await db.execute(
            text(
                """
                SELECT status, done_units, params ->> 'caderno_nome' AS caderno_nome
                FROM tc_jobs
                WHERE kind = 'caderno' AND external_id = :cid
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"cid": str(caderno_id)},
        )
    ).mappings().first()

    if not ids:
        # Coleta antiga (anterior ao registro de ordem das questões): as questões
        # existem no banco, mas falta o mapeamento caderno→questão. Re-coletar
        # grava o membership e habilita a montagem.
        if job and int(job["done_units"] or 0) > 0:
            raise HTTPException(
                409,
                "Este caderno foi coletado antes do registro da ordem das questões. "
                "Re-colete o caderno (cole a URL e colete de novo) para poder montá-lo na pasta.",
            )
        raise HTTPException(400, "Nenhuma questão coletada para este caderno ainda.")
    if job and job["status"] != "done" and not forcar:
        raise HTTPException(
            409,
            "Coleta ainda não concluída. Use forçar para montar com o que já foi coletado.",
        )

    nome = (
        (req.nome.strip() if req and req.nome and req.nome.strip() else None)
        or (job["caderno_nome"] if job else None)
        or f"Caderno {caderno_id}"
    )

    caderno = (
        await db.execute(
            select(CadernoQuestoes).where(CadernoQuestoes.tc_caderno_id == caderno_id)
        )
    ).scalar_one_or_none()
    if caderno is None:
        # Caderno avulso do TC é pessoal do admin que coletou (entra em Minhas Pastas).
        caderno = CadernoQuestoes(
            owner_uid=_admin.id, nome=nome, pasta=PASTA_IMPORTADOS, tc_caderno_id=caderno_id
        )
        db.add(caderno)
    caderno.nome = nome
    caderno.pasta = PASTA_IMPORTADOS
    caderno.question_ids = ids
    caderno.total = len(ids)
    await db.commit()
    await db.refresh(caderno)

    return {
        "id": caderno.id,
        "nome": caderno.nome,
        "pasta": caderno.pasta,
        "total": caderno.total,
        "primeira_questao_id": ids[0],
        "redirect": f"/q/caderno/{caderno.id}",
    }


@router.post("/coletar/{caderno_id}/recoletar")
async def recoletar_caderno(
    caderno_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reprocessa um caderno já concluído para registrar a ordem das questões.

    Cadernos coletados antes do registro de membership (`tc_caderno_questoes`)
    não podem ser montados na pasta. Resetar as faixas para `pending` faz o
    supervisor reprocessá-las — agora gravando o membership. Re-fetch no TC é
    inevitável (a ordem só vem de lá); para cadernos grandes leva tempo.
    """
    job = (
        await db.execute(
            text(
                """
                SELECT id, total_units
                FROM tc_jobs
                WHERE kind = 'caderno' AND external_id = :cid
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"cid": str(caderno_id)},
        )
    ).mappings().first()
    if not job:
        raise HTTPException(404, "Nenhum job de coleta para este caderno.")

    await db.execute(
        text(
            """
            UPDATE tc_caderno_units
            SET status = 'pending', leased_until = NULL, task_id = NULL,
                attempts = 0, finished_at = NULL, questoes_ok = 0,
                block_reason = NULL, blocked_until = NULL, last_error = NULL,
                updated_at = now()
            WHERE job_id = :jid
            """
        ),
        {"jid": int(job["id"])},
    )
    await db.execute(
        text(
            """
            UPDATE tc_jobs
            SET status = 'running', done_units = 0, failed_units = 0,
                blocked_units = 0, finished_at = NULL, paused_by_user = FALSE,
                updated_at = now()
            WHERE id = :jid
            """
        ),
        {"jid": int(job["id"])},
    )
    await db.commit()
    return {
        "caderno_id": caderno_id,
        "faixas": int(job["total_units"] or 0),
        "message": "re-coleta agendada; o supervisor vai reprocessar as faixas e registrar a ordem das questões",
    }


async def _scraper_job_action(job_id: int, action: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=3, read=10, write=5, pool=12)) as c:
            r = await c.post(f"{SCRAPER_URL}/job/{job_id}/{action}")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc
    if r.status_code == 404:
        raise HTTPException(404, "job não encontrado")
    if r.status_code != 200:
        raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:200]}")
    return r.json()


@router.post("/coletar/jobs/{job_id}/pausar")
async def pausar_job(job_id: int, _admin: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Pausa a coleta de um job — supervisor para de enfileirar novas faixas. (admin)"""
    return await _scraper_job_action(job_id, "pause")


@router.post("/coletar/jobs/{job_id}/retomar")
async def retomar_job(job_id: int, _admin: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Retoma a coleta de um job pausado. (admin)"""
    return await _scraper_job_action(job_id, "resume")


async def _meili_reindex_recentes(db: AsyncSession, limit: int = 500) -> int:
    """Reindex as N mais recentes (pós-coleta). Simples e idempotente."""
    from sqlalchemy import desc
    from models import Alternativa  # noqa: F401

    stmt = (
        select(Questao)
        .options(selectinload(Questao.assuntos))
        .order_by(desc(Questao.updated_at))
        .limit(max(limit, 200))
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Pre-carrega taxonomia
    bancas = {b.id: b for b in (await db.execute(select(Banca))).scalars().all()}
    orgaos = {o.id: o for o in (await db.execute(select(Orgao))).scalars().all()}
    cargos = {c.id: c for c in (await db.execute(select(Cargo))).scalars().all()}
    materias = {m.id: m for m in (await db.execute(select(Materia))).scalars().all()}

    def _strip(s: str | None) -> str:
        if not s:
            return ""
        return _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", s)).strip()[:8000]

    docs = []
    for q in rows:
        banca = bancas.get(q.banca_id) if q.banca_id else None
        orgao = orgaos.get(q.orgao_id) if q.orgao_id else None
        cargo = cargos.get(q.cargo_id) if q.cargo_id else None
        materia = materias.get(q.materia_id) if q.materia_id else None
        docs.append({
            "id": q.id,
            "id_externo": q.id_externo,
            "enunciado": _strip(q.enunciado_md or q.enunciado_html),
            "gabarito": q.gabarito,
            "tipo": q.tipo,
            "status": q.status,
            "banca": banca.sigla or banca.nome if banca else None,
            "orgao": orgao.sigla or orgao.nome if orgao else None,
            "cargo": cargo.nome if cargo else None,
            "ano": cargo.ano if cargo else None,
            "materia": materia.nome if materia else None,
            "assuntos": [a.nome for a in q.assuntos],
            "tem_alternativas": 0,
        })

    if not docs:
        return 0

    async with httpx.AsyncClient(timeout=30.0) as c:
        await c.post(
            f"{MEILI_URL}/indexes/questoes/documents",
            headers={
                "Authorization": f"Bearer {MEILI_KEY}",
                "Content-Type": "application/json",
            },
            json=docs,
        )
    return len(docs)


@router.get("/categorias-arvore")
async def categorias_arvore(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Árvore Matéria → Assuntos (para o componente FacetSidebar)."""
    from models import Assunto

    materias = (await db.execute(select(Materia).order_by(Materia.nome))).scalars().all()
    assuntos = (await db.execute(select(Assunto).order_by(Assunto.nome))).scalars().all()
    by_materia: dict[int, list[dict]] = {}
    for a in assuntos:
        by_materia.setdefault(a.materia_id or -1, []).append({"id": a.id, "nome": a.nome})
    return [
        {
            "id": m.id,
            "nome": m.nome,
            "assuntos": by_materia.get(m.id, []),
        }
        for m in materias
    ]


class GerarCadernoReq(BaseModel):
    nome: str = Field(default="Caderno de Estudo")
    pasta: str | None = None
    filtros: dict[str, list[str] | list[int]] = Field(default_factory=dict)
    q: str = ""
    favoritas: bool = False
    limite: int = Field(default=500, ge=1, le=30000)
    ordem: str = Field(default="aleatoria", description="aleatoria | id | ano")
    # IDs studIA explícitos: se vier, pula o Meili e usa direto (ex.: caderno de
    # 1 questão a partir da busca por ID). Tem precedência sobre filtros/q.
    question_ids: list[int] | None = None


@router.post("/cadernos")
async def gerar_caderno(
    req: GerarCadernoReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cria um caderno materializando os IDs das questões que matcham os filtros.

    Replica o padrão TC: armazena IDs concretos (não apenas a query) — assim o
    histórico do caderno fica estável mesmo se novas questões forem adicionadas.
    O caderno é pessoal: gravamos `owner_uid = user.id` (entra em "Minhas Pastas").
    """
    # 0. IDs explícitos (ex.: caderno de 1 questão pela busca por ID) — pula o Meili.
    if req.question_ids:
        ids_validos = (await db.execute(
            select(Questao.id).where(Questao.id.in_(req.question_ids))
        )).scalars().all()
        ids = [qid for qid in req.question_ids if qid in set(ids_validos)]
        if not ids:
            raise HTTPException(400, "Nenhuma questão válida nos IDs informados.")
        caderno = CadernoQuestoes(
            owner_uid=user.id, nome=req.nome.strip() or "Caderno de Estudo",
            pasta=req.pasta, filtros=req.filtros, question_ids=ids, total=len(ids),
        )
        db.add(caderno)
        await db.commit()
        await db.refresh(caderno)
        return {"id": caderno.id, "nome": caderno.nome, "total": caderno.total,
                "primeira_questao_id": ids[0], "redirect": f"/q/caderno/{caderno.id}"}

    # 1. Busca IDs via Meili
    payload = {
        "q": req.q,
        "limit": req.limite,
        "offset": 0,
        "attributesToRetrieve": ["id"],
    }
    f = _to_meili_filter(req.filtros)
    if req.favoritas:
        fav = await _filtro_favoritas(db, user.id)
        if fav is None:
            raise HTTPException(400, "Nenhuma questão favoritada ainda.")
        f = f"{f} AND {fav}" if f else fav
    if f:
        payload["filter"] = f
    if req.ordem == "id":
        payload["sort"] = ["id:asc"]
    elif req.ordem == "ano":
        payload["sort"] = ["ano:desc"]
    data = await _meili_search(payload)
    ids = [int(h["id"]) for h in data.get("hits", [])]

    if not ids:
        raise HTTPException(400, "Nenhuma questão matcha os filtros.")

    if req.ordem == "aleatoria":
        import random
        random.shuffle(ids)

    # 2. Persiste o caderno (pessoal do usuário)
    caderno = CadernoQuestoes(
        owner_uid=user.id,
        nome=req.nome.strip() or "Caderno de Estudo",
        pasta=req.pasta,
        filtros=req.filtros,
        question_ids=ids,
        total=len(ids),
    )
    db.add(caderno)
    await db.commit()
    await db.refresh(caderno)

    return {
        "id": caderno.id,
        "nome": caderno.nome,
        "total": caderno.total,
        "primeira_questao_id": ids[0] if ids else None,
        "redirect": f"/q/caderno/{caderno.id}",
    }


@router.get("/questoes/buscar-externo/{id_externo}")
async def buscar_questao_externo(
    id_externo: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Busca uma questão pelo `id_externo` (ID do TC) + cadernos do usuário que a contêm."""
    row = (await db.execute(
        select(
            Questao.id, Questao.id_externo, Questao.status, Questao.gabarito, Questao.tipo,
            Banca.sigla.label("banca"), Materia.nome.label("materia"),
            func.substring(Questao.enunciado_md, 1, 240).label("preview"),
        )
        .outerjoin(Banca, Banca.id == Questao.banca_id)
        .outerjoin(Materia, Materia.id == Questao.materia_id)
        .where(Questao.id_externo == id_externo)
    )).mappings().first()
    if row is None:
        return {"found": False}
    qid = row["id"]
    cad_rows = (await db.execute(text(
        """
        SELECT id, nome, pasta FROM cadernos_questoes
        WHERE owner_uid = :uid
          AND cast(question_ids as jsonb) @> to_jsonb(cast(:qid as integer))
        ORDER BY created_at DESC
        """
    ), {"uid": user.id, "qid": qid})).mappings().all()
    return {
        "found": True,
        "questao": {
            "id": qid, "id_externo": row["id_externo"], "status": row["status"],
            "gabarito": row["gabarito"], "tipo": row["tipo"], "banca": row["banca"],
            "materia": row["materia"], "preview": (row["preview"] or "").strip(),
        },
        "cadernos": [{"id": c["id"], "nome": c["nome"], "pasta": c["pasta"]} for c in cad_rows],
    }


class DerivarCadernoReq(BaseModel):
    tipo: str = Field(..., description="resolvidas | acertadas | erradas")
    nome: str = Field(default="", description="nome do novo caderno (vazio = automático)")


@router.post("/cadernos/{caderno_id}/derivar")
async def derivar_caderno(
    caderno_id: int,
    req: DerivarCadernoReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cria um caderno novo com o subconjunto das questões que o usuário
    resolveu/acertou/errou neste caderno. Snapshot dos IDs (estilo TC)."""
    if req.tipo not in ("resolvidas", "acertadas", "erradas"):
        raise HTTPException(422, "tipo inválido (resolvidas | acertadas | erradas)")
    cad = await _caderno_acessivel(db, caderno_id, user)

    rows = (await db.execute(
        select(Resolucao.questao_id, Resolucao.acertou)
        .where(Resolucao.usuario_uid == user.id, Resolucao.caderno_id == caderno_id)
        .order_by(Resolucao.created_at.desc())
    )).all()
    acertou_por_q: dict[int, Any] = {}
    for r in rows:
        if r.questao_id not in acertou_por_q:  # desc → mantém a mais recente
            acertou_por_q[r.questao_id] = r.acertou

    def incluir(qid: int) -> bool:
        if qid not in acertou_por_q:
            return False
        if req.tipo == "resolvidas":
            return True
        if req.tipo == "acertadas":
            return acertou_por_q[qid] is True
        return acertou_por_q[qid] is False  # erradas

    # Preserva a ordem original do caderno.
    ids = [qid for qid in (cad.question_ids or []) if incluir(qid)]
    if not ids:
        raise HTTPException(400, "Nenhuma questão nessa categoria ainda.")

    label = {"resolvidas": "Resolvidas", "acertadas": "Acertadas", "erradas": "Erradas"}[req.tipo]
    nome = (req.nome or "").strip() or f"{label} — {cad.nome}"
    novo = CadernoQuestoes(
        owner_uid=user.id,
        nome=nome[:512],
        pasta=cad.pasta,
        question_ids=ids,
        total=len(ids),
    )
    db.add(novo)
    await db.commit()
    await db.refresh(novo)
    return {
        "id": novo.id,
        "nome": novo.nome,
        "total": novo.total,
        "redirect": f"/q/caderno/{novo.id}",
    }


@router.get("/cadernos/{caderno_id}")
async def detalhe_caderno(
    caderno_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_acessivel(db, caderno_id, user)
    return {
        "id": cad.id,
        "nome": cad.nome,
        "pasta": cad.pasta,
        "filtros": cad.filtros,
        "total": cad.total,
        "question_ids": cad.question_ids or [],
        "created_at": cad.created_at.isoformat() if cad.created_at else None,
    }


class RenomearCadernoReq(BaseModel):
    nome: str = Field(min_length=1, max_length=512)


@router.patch("/cadernos/{caderno_id}")
async def renomear_caderno(
    caderno_id: int,
    req: RenomearCadernoReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Renomeia um caderno. Só o dono (owner_uid) pode; cadernos de catálogo
    (de guia) não são renomeáveis pelo usuário comum."""
    cad = (
        await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))
    ).scalar_one_or_none()
    if not cad or cad.owner_uid != user.id:
        raise HTTPException(404, "caderno não encontrado")
    nome = req.nome.strip()
    if not nome:
        raise HTTPException(422, "nome não pode ser vazio")
    cad.nome = nome[:512]
    await db.commit()
    return {"id": cad.id, "nome": cad.nome}


@router.get("/cadernos")
async def listar_cadernos(
    pasta: str | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Minhas Pastas: cadernos do usuário. `?pasta=Nome` filtra, `?pasta=` → sem classificação.

    Inclui cadernos próprios (`owner_uid`) E cadernos do catálogo (de guia) que
    o usuário salvou (`cadernos_salvos`)."""
    from sqlalchemy import desc, or_

    salvos_subq = select(CadernoSalvo.caderno_id).where(CadernoSalvo.usuario_uid == user.id)
    stmt = (
        select(CadernoQuestoes)
        .where(
            or_(
                CadernoQuestoes.owner_uid == user.id,
                CadernoQuestoes.id.in_(salvos_subq),
            )
        )
        .order_by(desc(CadernoQuestoes.created_at))
        .limit(200)
    )
    if pasta is not None:
        if pasta == "":
            stmt = stmt.where(or_(CadernoQuestoes.pasta.is_(None), CadernoQuestoes.pasta == ""))
        else:
            stmt = stmt.where(CadernoQuestoes.pasta == pasta)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {"id": c.id, "nome": c.nome, "total": c.total, "pasta": c.pasta,
         "created_at": c.created_at.isoformat() if c.created_at else None}
        for c in rows
    ]


@router.get("/pastas")
async def listar_pastas(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Agrupa os cadernos DO usuário por pasta (estilo TC "Minhas pastas").

    Considera cadernos próprios E os do catálogo salvos pelo usuário."""
    from sqlalchemy import or_

    salvos_subq = select(CadernoSalvo.caderno_id).where(CadernoSalvo.usuario_uid == user.id)
    pasta_norm = func.nullif(func.coalesce(CadernoQuestoes.pasta, ""), "")
    rows = (
        await db.execute(
            select(
                pasta_norm.label("pasta"),
                func.count(CadernoQuestoes.id),
                func.coalesce(func.sum(CadernoQuestoes.total), 0),
            )
            .where(
                or_(
                    CadernoQuestoes.owner_uid == user.id,
                    CadernoQuestoes.id.in_(salvos_subq),
                )
            )
            .group_by(pasta_norm)
            .order_by(pasta_norm.asc().nulls_last())
        )
    ).all()
    return [
        {"pasta": pasta, "cadernos": n, "total_questoes": int(tq)}
        for pasta, n, tq in rows
    ]


class ResponderReq(BaseModel):
    resposta: str = Field(..., description="Letra (A-E) ou Certo/Errado")
    tempo_segundos: int | None = None
    caderno_id: int | None = None


def _empty_canvas() -> dict[str, Any]:
    return {"version": 1, "cardSize": None, "strokes": []}


def _empty_strikes() -> dict[str, Any]:
    return {"version": 1, "targets": []}


class AnnotationReq(BaseModel):
    canvas_json: dict[str, Any] = Field(default_factory=_empty_canvas)
    strikes_json: dict[str, Any] = Field(default_factory=_empty_strikes)


class CalculatorHistoryReq(BaseModel):
    expression: str = Field(..., min_length=1, max_length=512)
    result: str = Field(..., min_length=1, max_length=512)
    caderno_id: int | None = None
    questao_id: int | None = None


def _annotation_response(row: QuestaoAnotacao | None, caderno_id: int, questao_id: int) -> dict[str, Any]:
    return {
        "id": row.id if row else None,
        "usuario_uid": row.usuario_uid if row else None,
        "caderno_id": caderno_id,
        "questao_id": questao_id,
        "canvas_json": row.canvas_json if row else _empty_canvas(),
        "strikes_json": row.strikes_json if row else _empty_strikes(),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def _annotation_scope(caderno_id: int, questao_id: int, owner_uid: str):
    return select(QuestaoAnotacao).where(
        QuestaoAnotacao.usuario_uid == owner_uid,
        QuestaoAnotacao.caderno_id == caderno_id,
        QuestaoAnotacao.questao_id == questao_id,
    )


@router.get("/limite")
async def limite_diario(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Estado do limite diário do usuário (para o contador "7/10 hoje" na UI)."""
    return await resumo_limite(db, user)


@router.post("/{questao_id}/responder")
async def responder(
    questao_id: int,
    req: ResponderReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (await db.execute(
        select(Questao).options(selectinload(Questao.alternativas)).where(Questao.id == questao_id)
    )).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "questao não encontrada")

    # Idempotência: uma questão já resolvida pelo usuário NESTE caderno não pode
    # ser respondida de novo. Sem isso, voltar à questão (ou cliques-fantasma)
    # gravava Resolucao duplicada — inflando estatísticas e burlando o limite.
    cond_cad = (
        Resolucao.caderno_id == req.caderno_id
        if req.caderno_id is not None
        else Resolucao.caderno_id.is_(None)
    )
    existente = (await db.execute(
        select(Resolucao)
        .where(
            Resolucao.usuario_uid == user.id,
            Resolucao.questao_id == questao_id,
            cond_cad,
        )
        .order_by(Resolucao.created_at.asc())
        .limit(1)
    )).scalars().first()
    if existente is not None:
        total = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id))).scalar_one()
        acertos = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
        return {
            "acertou": existente.acertou,
            "gabarito": q.gabarito,
            "stats": {"resolvidas": total, "acertos": acertos, "erros": total - acertos},
            "limite": await resumo_limite(db, user),
            "meta_diaria": await meta_diaria_status(db, user, era_nova=False),
            "ja_resolvida": True,
        }

    # Plano grátis: bloqueia a partir da 11ª questão NOVA do dia (402). Admin e
    # assinante ativo passam direto. Repetir questão já contada hoje é livre.
    await garantir_pode_resolver(db, user, questao_id)

    # Normaliza pra comparar.
    # Em CERTO_ERRADO o gabarito é a *palavra* ("CERTO"/"ERRADO") mas a resposta
    # enviada é a *letra* (A/B) — então comparar letra==gabarito daria sempre erro.
    # Regra robusta: usa a flag `correta` quando existe; senão cai pro gabarito
    # (letra em múltipla escolha, ou texto da alternativa em certo/errado).
    resp = req.resposta.strip().upper()
    gab = (q.gabarito or "").strip().upper()
    corretas = {(a.letra or "").strip().upper() for a in q.alternativas if a.correta is True}
    if "ANULADA" in gab:
        acertou = True  # questão anulada — todo mundo acerta (convenção TC)
    elif corretas:
        acertou = resp in corretas
    else:
        alt_sel = next((a for a in q.alternativas if (a.letra or "").strip().upper() == resp), None)
        texto_sel = (alt_sel.texto_md or "").strip().upper() if alt_sel else ""
        acertou = (resp == gab) or (texto_sel == gab)

    res = Resolucao(
        questao_id=questao_id,
        caderno_id=req.caderno_id,
        usuario_uid=user.id,
        resposta=resp,
        acertou=acertou,
        tempo_segundos=req.tempo_segundos,
    )
    db.add(res)
    await db.commit()

    # Retorna stats atualizadas (só do usuário atual)
    total = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    erros = total - acertos
    return {
        "acertou": acertou,
        "gabarito": q.gabarito,
        "stats": {"resolvidas": total, "acertos": acertos, "erros": erros},
        "limite": await resumo_limite(db, user),
        "meta_diaria": await meta_diaria_status(db, user, era_nova=True),
    }


@router.get("/{questao_id}/estatisticas")
async def estatisticas(
    questao_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    total = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    return {"resolvidas": total, "acertos": acertos, "erros": total - acertos}


@router.get("/cadernos/{caderno_id}/estatisticas")
async def estatisticas_caderno(
    caderno_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_acessivel(db, caderno_id, user)
    total = (await db.execute(select(func.count()).where(Resolucao.caderno_id == caderno_id, Resolucao.usuario_uid == user.id))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(Resolucao.caderno_id == caderno_id, Resolucao.usuario_uid == user.id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    return {
        "caderno_id": caderno_id,
        "questoes_total": cad.total,
        "resolvidas": total,
        "acertos": acertos,
        "erros": total - acertos,
    }


class ImportarGabaritoReq(BaseModel):
    # ID do caderno no TEC. Opcional: se o caderno studIA já tem `tc_caderno_id`,
    # usa esse. Aceita o número puro (a UI extrai de uma URL antes de enviar).
    tc_caderno_id: int | None = None


_ALT_LETRAS = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}


def _alt_para_resposta(alternativa: Any, tipo: str | None) -> str | None:
    """Converte a alternativa marcada do TEC (1-5) na resposta studIA.

    Em CERTO_ERRADO o TEC usa 1=Certo, 2=Errado → grava a *palavra* (igual ao
    formato de `Questao.gabarito`). Em múltipla escolha, 1-5 → A-E.
    """
    if alternativa is None:
        return None
    if (tipo or "").upper() == "CERTO_ERRADO":
        return "CERTO" if alternativa == 1 else "ERRADO"
    return _ALT_LETRAS.get(alternativa)


def _parse_data_tc(valor: Any) -> datetime | None:
    """Parseia datas do TEC em datetime UTC-aware.

    Formatos suportados:
    - "DD/MM/AAAA HH:MM:SS" — fórum de alunos (ex.: "02/12/2023 20:09:16")
    - "DD/MM/AAAA" — gabarito
    - "AAAA-MM-DD" — comentário do professor (ex.: "2024-04-28")
    """
    if not valor or not isinstance(valor, str):
        return None
    s = valor.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


@router.post("/cadernos/{caderno_id}/importar-gabarito")
async def importar_gabarito_tec(
    caderno_id: int,
    req: ImportarGabaritoReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Importa o desempenho do usuário no TEC (aba Gabarito) para este caderno.

    Mapeia cada `idQuestao` do TEC → `Questao.id_externo` → grava `Resolucao`
    (resposta/acertou/data). Dedup por (usuário, caderno, questão): não duplica
    nem sobrescreve respostas já existentes — re-import é incremental.
    """
    cad = await _caderno_acessivel(db, caderno_id, user)

    tc_cid = cad.tc_caderno_id or req.tc_caderno_id
    if not tc_cid:
        raise HTTPException(
            422,
            "Caderno sem vínculo com o TEC. Informe o ID (ou URL) do caderno no TecConcursos.",
        )
    # Vincula o caderno ao TEC se ainda não tinha (só o dono pode gravar).
    if cad.tc_caderno_id is None and cad.owner_uid == user.id:
        cad.tc_caderno_id = tc_cid

    # Busca o gabarito no scraper (sessão TC + proxy residencial vivem lá).
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=180, write=10, pool=185)
        ) as c:
            r = await c.get(f"{SCRAPER_URL}/caderno/{tc_cid}/gabarito")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:300]}")
    payload = r.json()
    itens: list[dict[str, Any]] = payload.get("itens") or []

    # idQuestao (TEC) → Questao.id (studIA), via id_externo.
    ids_externos = [it["idQuestao"] for it in itens if it.get("idQuestao") is not None]
    mapa: dict[int, int] = {}
    if ids_externos:
        mapa = dict(
            (
                await db.execute(
                    select(Questao.id_externo, Questao.id).where(
                        Questao.id_externo.in_(ids_externos)
                    )
                )
            ).all()
        )

    # Questões que o usuário já tem resolução NESTE caderno (qualquer origem):
    # não duplicar nem sobrescrever resposta manual.
    ja_resolvidas: set[int] = set(
        (
            await db.execute(
                select(Resolucao.questao_id).where(
                    Resolucao.caderno_id == caderno_id,
                    Resolucao.usuario_uid == user.id,
                )
            )
        )
        .scalars()
        .all()
    )

    importadas = acertos = erros = ja_tinha = nao_resolvidas = nao_mapeadas = 0
    for it in itens:
        if it.get("acertou") is None:  # não resolvida no TEC
            nao_resolvidas += 1
            continue
        qid = mapa.get(it.get("idQuestao"))
        if qid is None:  # questão não existe no studIA (caderno não coletado por completo)
            nao_mapeadas += 1
            continue
        if qid in ja_resolvidas:
            ja_tinha += 1
            continue

        acertou = bool(it.get("acertou"))
        kwargs: dict[str, Any] = dict(
            questao_id=qid,
            caderno_id=caderno_id,
            usuario_uid=user.id,
            resposta=_alt_para_resposta(it.get("alternativa"), it.get("tipoQuestao")),
            acertou=acertou,
            tempo_segundos=None,
        )
        data = _parse_data_tc(it.get("data"))
        if data is not None:
            kwargs["created_at"] = data
        db.add(Resolucao(**kwargs))
        ja_resolvidas.add(qid)
        importadas += 1
        if acertou:
            acertos += 1
        else:
            erros += 1

    await db.commit()
    return {
        "caderno_id": caderno_id,
        "tc_caderno_id": tc_cid,
        "total_no_tec": payload.get("total", len(itens)),
        "importadas": importadas,
        "acertos": acertos,
        "erros": erros,
        "ja_tinha": ja_tinha,
        "nao_resolvidas_no_tec": nao_resolvidas,
        "nao_mapeadas": nao_mapeadas,
    }


@router.get("/cadernos/{caderno_id}/stats-detalhe")
async def stats_detalhe(
    caderno_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Estatísticas analíticas DO usuário: por matéria/assunto/banca + tempo + histórico."""
    from models import questao_assunto

    cad = await _caderno_acessivel(db, caderno_id, user)
    # Toda Resolucao é filtrada por (caderno, usuário atual): nunca soma de outros.
    _meu = (Resolucao.caderno_id == caderno_id, Resolucao.usuario_uid == user.id)

    # ─── Resumo ───
    total = (await db.execute(select(func.count()).where(*_meu))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(*_meu, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    tempo_total = (await db.execute(select(func.coalesce(func.sum(Resolucao.tempo_segundos), 0)).where(*_meu))).scalar_one()
    tempo_medio = (await db.execute(select(func.coalesce(func.avg(Resolucao.tempo_segundos), 0)).where(*_meu))).scalar_one()

    # ─── Por matéria ───
    por_materia = (await db.execute(
        select(
            Materia.nome.label("nome"),
            func.count(Resolucao.id).label("resolvidas"),
            func.sum(func.cast(Resolucao.acertou, Integer)).label("acertos"),
        )
        .select_from(Resolucao)
        .join(Questao, Questao.id == Resolucao.questao_id)
        .join(Materia, Materia.id == Questao.materia_id)
        .where(*_meu)
        .group_by(Materia.nome)
        .order_by(func.count(Resolucao.id).desc())
        .limit(20)
    )).all()

    # ─── Por assunto ───
    from models import Assunto
    por_assunto = (await db.execute(
        select(
            Assunto.nome.label("nome"),
            func.count(Resolucao.id).label("resolvidas"),
            func.sum(func.cast(Resolucao.acertou, Integer)).label("acertos"),
        )
        .select_from(Resolucao)
        .join(Questao, Questao.id == Resolucao.questao_id)
        .join(questao_assunto, questao_assunto.c.questao_id == Questao.id)
        .join(Assunto, Assunto.id == questao_assunto.c.assunto_id)
        .where(*_meu)
        .group_by(Assunto.nome)
        .order_by(func.count(Resolucao.id).desc())
        .limit(30)
    )).all()

    # ─── Por banca ───
    por_banca = (await db.execute(
        select(
            Banca.sigla.label("nome"),
            func.count(Resolucao.id).label("resolvidas"),
            func.sum(func.cast(Resolucao.acertou, Integer)).label("acertos"),
        )
        .select_from(Resolucao)
        .join(Questao, Questao.id == Resolucao.questao_id)
        .join(Banca, Banca.id == Questao.banca_id)
        .where(*_meu)
        .group_by(Banca.sigla)
        .order_by(func.count(Resolucao.id).desc())
        .limit(10)
    )).all()

    # ─── Últimas 20 resoluções ───
    from sqlalchemy import desc
    ultimas = (await db.execute(
        select(
            Resolucao.id,
            Resolucao.questao_id,
            Questao.id_externo,
            Resolucao.resposta,
            Resolucao.acertou,
            Resolucao.tempo_segundos,
            Resolucao.created_at,
        )
        .select_from(Resolucao)
        .join(Questao, Questao.id == Resolucao.questao_id)
        .where(*_meu)
        .order_by(desc(Resolucao.created_at))
        .limit(20)
    )).all()

    def _format_grupo(rows: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "nome": r.nome,
                "resolvidas": int(r.resolvidas or 0),
                "acertos": int(r.acertos or 0),
                "taxa": round((float(r.acertos or 0) / r.resolvidas) * 100, 1) if r.resolvidas else 0,
            }
            for r in rows
        ]

    return {
        "caderno_id": caderno_id,
        "questoes_total": cad.total,
        "resolvidas": total,
        "acertos": acertos,
        "erros": total - acertos,
        "taxa": round((acertos / total) * 100, 1) if total else 0,
        "tempo_total_segundos": int(tempo_total or 0),
        "tempo_medio_segundos": round(float(tempo_medio or 0), 1),
        "por_materia": _format_grupo(por_materia),
        "por_assunto": _format_grupo(por_assunto),
        "por_banca": _format_grupo(por_banca),
        "ultimas_resolucoes": [
            {
                "id": r.id,
                "questao_id": r.questao_id,
                "id_externo": r.id_externo,
                "resposta": r.resposta,
                "acertou": r.acertou,
                "tempo_segundos": r.tempo_segundos,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in ultimas
        ],
    }


@router.get("/cadernos/{caderno_id}/gabarito")
async def gabarito_caderno(
    caderno_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Tabela: idx → questao_id → idExterno → gabarito (modo Gabarito do TC)."""
    cad = await _caderno_acessivel(db, caderno_id, user)
    ids = cad.question_ids or []
    if not ids:
        return {"caderno_id": caderno_id, "items": []}

    rows = (await db.execute(
        select(Questao.id, Questao.id_externo, Questao.gabarito, Questao.status)
        .where(Questao.id.in_(ids))
    )).all()
    by_id = {r.id: r for r in rows}

    items = [
        {
            "n": i + 1,
            "questao_id": qid,
            "id_externo": by_id[qid].id_externo if qid in by_id else None,
            "gabarito": by_id[qid].gabarito if qid in by_id else None,
            "status": by_id[qid].status if qid in by_id else None,
        }
        for i, qid in enumerate(ids)
    ]
    return {"caderno_id": caderno_id, "total": len(items), "items": items}


@router.get("/cadernos/{caderno_id}/indice")
async def indice_caderno(
    caderno_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Índice navegável — lista compacta de todas as questões do caderno."""
    from models import Assunto

    cad = await _caderno_acessivel(db, caderno_id, user)
    ids = cad.question_ids or []
    if not ids:
        return {"caderno_id": caderno_id, "items": []}

    rows = (await db.execute(
        select(
            Questao.id,
            Questao.id_externo,
            Banca.sigla.label("banca"),
            Materia.nome.label("materia"),
            Questao.gabarito,
            Questao.tipo,
            func.substring(Questao.enunciado_md, 1, 140).label("preview"),
        )
        .select_from(Questao)
        .outerjoin(Banca, Banca.id == Questao.banca_id)
        .outerjoin(Materia, Materia.id == Questao.materia_id)
        .where(Questao.id.in_(ids))
    )).all()
    by_id = {r.id: r for r in rows}

    items = []
    for i, qid in enumerate(ids):
        r = by_id.get(qid)
        if not r:
            continue
        items.append({
            "n": i + 1,
            "questao_id": qid,
            "id_externo": r.id_externo,
            "banca": r.banca,
            "materia": r.materia,
            "gabarito": r.gabarito,
            "tipo": r.tipo,
            "preview": (r.preview or "").strip()[:140],
        })
    return {"caderno_id": caderno_id, "total": len(items), "items": items}


@router.get("/cadernos/{caderno_id}/minhas-resolucoes")
async def minhas_resolucoes_caderno(
    caderno_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Resoluções DO usuário neste caderno: questao_id → {resposta, acertou}.
    Usado pelo front pra travar questões já respondidas e pular as resolvidas
    na navegação (Aleatória/Próxima não resolvida)."""
    await _caderno_acessivel(db, caderno_id, user)
    rows = (await db.execute(
        select(Resolucao.questao_id, Resolucao.resposta, Resolucao.acertou)
        .where(Resolucao.usuario_uid == user.id, Resolucao.caderno_id == caderno_id)
        .order_by(Resolucao.created_at.desc())
    )).all()
    out: dict[str, Any] = {}
    for r in rows:
        key = str(r.questao_id)
        if key not in out:  # ordenado desc → mantém a resolução mais recente
            out[key] = {"resposta": r.resposta, "acertou": r.acertou}
    return {"caderno_id": caderno_id, "resolucoes": out}


@router.get("/cadernos/{caderno_id}/questoes/{questao_id}/annotations")
async def get_annotations(
    caderno_id: int,
    questao_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_acessivel(db, caderno_id, user)
    if questao_id not in (cad.question_ids or []):
        raise HTTPException(404, "questao não pertence ao caderno")

    row = (await db.execute(_annotation_scope(caderno_id, questao_id, user.id))).scalar_one_or_none()
    return _annotation_response(row, caderno_id, questao_id)


@router.put("/cadernos/{caderno_id}/questoes/{questao_id}/annotations")
async def put_annotations(
    caderno_id: int,
    questao_id: int,
    req: AnnotationReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_acessivel(db, caderno_id, user)
    if questao_id not in (cad.question_ids or []):
        raise HTTPException(404, "questao não pertence ao caderno")

    row = (await db.execute(_annotation_scope(caderno_id, questao_id, user.id))).scalar_one_or_none()
    if row:
        row.canvas_json = req.canvas_json
        row.strikes_json = req.strikes_json
        await db.commit()
    else:
        row = QuestaoAnotacao(
            usuario_uid=user.id,
            caderno_id=caderno_id,
            questao_id=questao_id,
            canvas_json=req.canvas_json,
            strikes_json=req.strikes_json,
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            row = (await db.execute(_annotation_scope(caderno_id, questao_id, user.id))).scalar_one_or_none()
            if not row:
                raise HTTPException(409, "conflito ao salvar anotacao")
            row.canvas_json = req.canvas_json
            row.strikes_json = req.strikes_json
            await db.commit()

    await db.refresh(row)
    return _annotation_response(row, caderno_id, questao_id)


@router.get("/calculator/history")
async def list_calculator_history(
    caderno_id: int | None = None,
    questao_id: int | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from sqlalchemy import desc

    stmt = select(CalculadoraHistorico).where(CalculadoraHistorico.usuario_uid == user.id)
    if caderno_id is not None:
        stmt = stmt.where(CalculadoraHistorico.caderno_id == caderno_id)
    if questao_id is not None:
        stmt = stmt.where(CalculadoraHistorico.questao_id == questao_id)
    rows = (
        await db.execute(
            stmt.order_by(
                desc(CalculadoraHistorico.created_at),
                desc(CalculadoraHistorico.id),
            ).limit(50)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "usuario_uid": row.usuario_uid,
                "caderno_id": row.caderno_id,
                "questao_id": row.questao_id,
                "expression": row.expression,
                "result": row.result,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.post("/calculator/history")
async def create_calculator_history(
    req: CalculatorHistoryReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    expression = req.expression.strip()
    result = req.result.strip()
    if not expression or not result:
        raise HTTPException(422, "expression e result são obrigatórios")

    row = CalculadoraHistorico(
        usuario_uid=user.id,
        caderno_id=req.caderno_id,
        questao_id=req.questao_id,
        expression=expression,
        result=result,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "usuario_uid": row.usuario_uid,
        "caderno_id": row.caderno_id,
        "questao_id": row.questao_id,
        "expression": row.expression,
        "result": row.result,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/calculator/history/{item_id}")
async def delete_calculator_history(
    item_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    row = (await db.execute(
        select(CalculadoraHistorico).where(
            CalculadoraHistorico.id == item_id,
            CalculadoraHistorico.usuario_uid == user.id,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "historico não encontrado")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/favoritas")
async def listar_favoritas(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """IDs das questões favoritadas DO usuário (registrar ANTES de GET /{questao_id})."""
    ids = (
        await db.execute(
            select(QuestaoFavorita.questao_id)
            .where(QuestaoFavorita.owner_uid == user.id)
            .order_by(QuestaoFavorita.questao_id)
        )
    ).scalars().all()
    return {"ids": list(ids), "total": len(ids)}


@router.post("/{questao_id}/favoritar")
async def favoritar(
    questao_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Toggle estrela do usuário: favorita se não era, desfavorita se já era."""
    existente = (
        await db.execute(
            select(QuestaoFavorita).where(
                QuestaoFavorita.questao_id == questao_id,
                QuestaoFavorita.owner_uid == user.id,
            )
        )
    ).scalar_one_or_none()
    if existente:
        await db.delete(existente)
        await db.commit()
        return {"questao_id": questao_id, "favorita": False}
    existe_questao = (
        await db.execute(select(Questao.id).where(Questao.id == questao_id))
    ).scalar_one_or_none()
    if not existe_questao:
        raise HTTPException(404, f"questao {questao_id} not found")
    db.add(QuestaoFavorita(questao_id=questao_id, owner_uid=user.id))
    await db.commit()
    return {"questao_id": questao_id, "favorita": True}


@router.get("/dashboard")
async def dashboard(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dashboard pessoal — TUDO filtrado por Resolucao.usuario_uid == user.id.

    Estado vazio (usuário novo, zero resoluções) retorna zeros/arrays vazios.
    """
    meu = (Resolucao.usuario_uid == user.id,)

    total = (await db.execute(select(func.count()).where(*meu))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(*meu, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    erros = total - acertos
    tempo_total = (
        await db.execute(select(func.coalesce(func.sum(Resolucao.tempo_segundos), 0)).where(*meu))
    ).scalar_one()

    # ─── Por disciplina (Resolucao → Questao → Materia) ───
    por_disc_rows = (await db.execute(
        select(
            Materia.nome.label("nome"),
            func.count(Resolucao.id).label("total"),
            func.sum(func.cast(Resolucao.acertou, Integer)).label("acertos"),
            func.coalesce(func.sum(Resolucao.tempo_segundos), 0).label("tempo"),
        )
        .select_from(Resolucao)
        .join(Questao, Questao.id == Resolucao.questao_id)
        .join(Materia, Materia.id == Questao.materia_id)
        .where(*meu)
        .group_by(Materia.nome)
        .order_by(func.count(Resolucao.id).desc())
        .limit(20)
    )).all()
    por_disciplina = []
    for r in por_disc_rows:
        t = int(r.total or 0)
        ac = int(r.acertos or 0)
        por_disciplina.append({
            "nome": r.nome,
            "tempo_segundos": int(r.tempo or 0),
            "acertos": ac,
            "erros": t - ac,
            "total": t,
            "pct": round((ac / t) * 100, 1) if t else 0,
        })

    # ─── Atividade recente (group by dia, últimos 30) ───
    dia = func.date(Resolucao.created_at)
    atividade_rows = (await db.execute(
        select(
            dia.label("dia"),
            func.count(Resolucao.id).label("resolvidas"),
            func.sum(func.cast(Resolucao.acertou, Integer)).label("acertos"),
        )
        .where(*meu)
        .group_by(dia)
        .order_by(dia.desc())
        .limit(30)
    )).all()
    atividade_recente = [
        {
            "data": _as_date(r.dia).isoformat(),
            "resolvidas": int(r.resolvidas or 0),
            "acertos": int(r.acertos or 0),
        }
        for r in reversed(atividade_rows)
    ]

    # ─── Streak (dias consecutivos com atividade) ───
    dias_ativos = (
        await db.execute(select(func.distinct(func.date(Resolucao.created_at))).where(*meu))
    ).scalars().all()
    streak = _compute_streak({_as_date(d) for d in dias_ativos}, date.today())

    # ─── Últimas pastas acessadas (pela Resolucao mais recente do usuário) ───
    ultimas_rows = (await db.execute(
        select(
            CadernoQuestoes.pasta.label("pasta"),
            func.max(Resolucao.created_at).label("ultimo"),
            func.count(func.distinct(Resolucao.caderno_id)).label("cadernos"),
        )
        .select_from(Resolucao)
        .join(CadernoQuestoes, CadernoQuestoes.id == Resolucao.caderno_id)
        .where(*meu)
        .group_by(CadernoQuestoes.pasta)
        .order_by(func.max(Resolucao.created_at).desc())
        .limit(6)
    )).all()
    ultimas_pastas = [
        {
            "pasta": r.pasta,
            "cadernos": int(r.cadernos or 0),
            "ultimo_acesso": r.ultimo.isoformat() if r.ultimo else None,
        }
        for r in ultimas_rows
    ]

    return {
        "total_horas_segundos": int(tempo_total or 0),
        "resolvidas": total,
        "acertos": acertos,
        "erros": erros,
        "taxa": round((acertos / total) * 100, 1) if total else 0,
        "por_disciplina": por_disciplina,
        "atividade_recente": atividade_recente,
        "streak_dias": streak,
        "ultimas_pastas": ultimas_pastas,
    }


# ─── Fórum de discussão por questão ───────────────────────────────────────
MAX_COMENTARIO_CHARS = 20_000


class CriarComentarioReq(BaseModel):
    texto_md: str = Field(..., min_length=1, max_length=MAX_COMENTARIO_CHARS)
    parent_id: int | None = None
    quadro: Literal["alunos", "professores"] = "alunos"


def _display_name(c: QuestaoComentario) -> str:
    """Persona (admin no quadro professores) > pseudônimo TC > nome real do studIA."""
    if c.persona_nome:
        return c.persona_nome
    if c.origem == "tc":
        return pseudonimo(c.autor_nome or str(c.tc_comentario_id or c.id))
    return c.autor_nome or "Anônimo"


def _serializar_comentario(
    c: QuestaoComentario, *, meu_voto: int, user: CurrentUser, respostas: list[dict[str, Any]]
) -> dict[str, Any]:
    removido = c.deleted_at is not None
    nome = _display_name(c)
    dono = c.origem == "studia" and c.owner_uid == user.id
    return {
        "id": c.id,
        "parent_id": c.parent_id,
        "origem": c.origem,
        "display_name": nome,
        "autor_inicial": (nome.strip()[:1] or "?").upper(),
        "texto_md": None if removido else c.texto_md,
        "score": c.score or 0,
        "meu_voto": meu_voto,
        "criado_em": (c.publicado_em or c.created_at).isoformat() if (c.publicado_em or c.created_at) else None,
        "editado": c.edited_at is not None,
        "removido": removido,
        "eh_professor": c.forum_tipo == "professores",
        "posso_editar": dono and not removido,
        "posso_excluir": (dono or user.is_admin) and not removido,
        "respostas": respostas,
    }


_EXT_POR_CT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


async def _rehost_imagens_tc(
    md: str | None, imagens: list[str], client: httpx.AsyncClient
) -> str | None:
    """Baixa cada imagem do TC (via proxy do scraper) → MinIO → reescreve o md."""
    if not md or not imagens:
        return md
    for url in dict.fromkeys(imagens):  # dedup preservando ordem
        if url not in md:
            continue
        try:
            r = await client.get(f"{SCRAPER_URL}/tc/imagem", params={"u": url})
            if r.status_code != 200:
                continue
            ct = r.headers.get("content-type", "image/png").split(";")[0].strip()
            ext = _EXT_POR_CT.get(ct, "png")
            key = f"forum/{_uuid.uuid4()}.{ext}"
            upload_bytes(key, r.content, ct)
            md = md.replace(url, f"/api/q/forum/imagem/{key}")
        except Exception:
            continue
    return md


@router.get("/questoes/{questao_id}/forum")
async def listar_forum(
    questao_id: int,
    ordenar: str = "recentes",
    quadro: Literal["alunos", "professores"] = "alunos",
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    todos = (
        await db.execute(
            select(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == quadro,
            )
        )
    ).scalars().all()

    # Votos do usuário atual nesta questão (para `meu_voto`).
    ids = [c.id for c in todos]
    meus: dict[int, int] = {}
    if ids:
        rows = (
            await db.execute(
                select(ComentarioVoto.comentario_id, ComentarioVoto.valor).where(
                    ComentarioVoto.comentario_id.in_(ids),
                    ComentarioVoto.usuario_uid == user.id,
                )
            )
        ).all()
        meus = {cid: val for cid, val in rows}

    # Índice de respostas por pai (1 nível). Respostas deletadas são folhas → descartadas.
    respostas_por_pai: dict[int, list[QuestaoComentario]] = {}
    raizes: list[QuestaoComentario] = []
    for c in todos:
        if c.parent_id is None:
            raizes.append(c)
        elif c.deleted_at is None:
            respostas_por_pai.setdefault(c.parent_id, []).append(c)

    def _serial(c: QuestaoComentario, respostas: list[dict[str, Any]]) -> dict[str, Any]:
        return _serializar_comentario(c, meu_voto=meus.get(c.id, 0), user=user, respostas=respostas)

    out: list[dict[str, Any]] = []
    total = 0
    for raiz in raizes:
        filhos = sorted(respostas_por_pai.get(raiz.id, []), key=lambda x: x.created_at or x.id)
        # Raiz deletada sem filhos vivos → some do feed.
        if raiz.deleted_at is not None and not filhos:
            continue
        respostas = [_serial(f, []) for f in filhos]
        out.append(_serial(raiz, respostas))
        total += (0 if raiz.deleted_at is not None else 1) + len(filhos)

    if ordenar == "pontos":
        out.sort(key=lambda d: (d["score"], d["criado_em"] or ""), reverse=True)
    else:  # recentes
        out.sort(key=lambda d: d["criado_em"] or "", reverse=True)

    tc_importado = (await db.execute(
        select(QuestaoTcImport.id).where(
            QuestaoTcImport.questao_id == questao_id,
            QuestaoTcImport.quadro == quadro,
        )
    )).first() is not None

    return {"total": total, "comentarios": out, "tc_importado": tc_importado}


@router.post("/questoes/{questao_id}/importar-comentarios-tc")
async def importar_comentarios_tc(
    questao_id: int,
    quadro: Literal["alunos", "professores"] = "alunos",
    user: CurrentUser | None = Depends(require_user_or_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Importa (sob demanda) os comentários do TC para (questão, quadro).

    Idempotente: o marcador `QuestaoTcImport` impede re-scrape; o upsert por
    `tc_comentario_id` impede duplicar. Origem nunca exposta ao usuário.
    """
    row = (await db.execute(
        select(Questao.id, Questao.id_externo).where(Questao.id == questao_id)
    )).one_or_none()
    if row is None:
        raise HTTPException(404, "questão não encontrada")
    if row.id_externo is None:  # sem id_externo → não veio do TC (ex.: guia manual)
        return {"importados": 0, "count": 0, "ja_importado": False}
    id_externo = row.id_externo

    ja = (await db.execute(
        select(QuestaoTcImport).where(
            QuestaoTcImport.questao_id == questao_id,
            QuestaoTcImport.quadro == quadro,
        )
    )).scalar_one_or_none()
    if ja is not None:
        return {"importados": 0, "count": ja.count, "ja_importado": True}

    # Busca no scraper (sessão TC + proxy vivem lá).
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=120, write=10, pool=125)
        ) as c:
            r = await c.get(
                f"{SCRAPER_URL}/questao/{id_externo}/comentarios", params={"quadro": quadro}
            )
            if r.status_code != 200:
                raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:200]}")
            coments = (r.json() or {}).get("comentarios") or []

            # tc_comentario_id já presentes (dedup global por unique).
            tc_ids = [x["tc_comentario_id"] for x in coments if x.get("tc_comentario_id")]
            existentes: set[int] = set()
            if tc_ids:
                existentes = set((await db.execute(
                    select(QuestaoComentario.tc_comentario_id).where(
                        QuestaoComentario.tc_comentario_id.in_(tc_ids))
                )).scalars().all())

            # 1ª passada: raízes; 2ª: respostas (mapeia tc_parent → id local).
            # Nota: tc_parent_id é resolvido APENAS contra raízes importadas nesta
            # execução. O fórum do TC observado é flat (tc_parent_id sempre None),
            # portanto reimport incremental de threads aninhadas está fora do escopo
            # da Fase 1.
            tc_para_local: dict[int, int] = {}
            importados = 0
            for passada in ("raiz", "resposta"):
                for x in coments:
                    tcid = x.get("tc_comentario_id")
                    if not tcid or tcid in existentes:
                        continue
                    eh_raiz = x.get("tc_parent_id") is None
                    if (passada == "raiz") != eh_raiz:
                        continue
                    md = await _rehost_imagens_tc(x.get("md"), x.get("imagens") or [], c)
                    parent_local = (None if eh_raiz
                                    else tc_para_local.get(x["tc_parent_id"]))
                    com = QuestaoComentario(
                        questao_id=questao_id, origem="tc", forum_tipo=quadro,
                        tc_comentario_id=tcid, tc_parent_id=x.get("tc_parent_id"),
                        parent_id=parent_local,
                        autor_nome=x.get("autor_nome"), autor_tipo=x.get("autor_tipo"),
                        curtidas=int(x.get("curtidas") or 0),
                        score=int(x.get("curtidas") or 0), texto_md=md,
                        publicado_em=_parse_data_tc(x.get("publicado_em")),
                    )
                    db.add(com)
                    await db.flush()
                    tc_para_local[tcid] = com.id
                    existentes.add(tcid)
                    importados += 1
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fonte indisponível: {exc}") from exc
    except IntegrityError:
        # Corrida concorrente: outra requisição venceu no commit (UNIQUE collision).
        await db.rollback()
        return {"importados": 0, "count": 0, "ja_importado": True}

    try:
        total = (await db.execute(
            select(func.count()).select_from(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == quadro,
                QuestaoComentario.origem == "tc",
            )
        )).scalar_one()
        db.add(QuestaoTcImport(questao_id=questao_id, quadro=quadro, count=int(total)))
        await db.commit()
    except IntegrityError:
        # Outra requisição já gravou o marcador QuestaoTcImport entre o flush e o commit.
        await db.rollback()
        total = 0
        return {"importados": 0, "count": 0, "ja_importado": True}
    return {"importados": importados, "count": int(total), "ja_importado": False}


class EditarComentarioReq(BaseModel):
    texto_md: str = Field(..., min_length=1, max_length=MAX_COMENTARIO_CHARS)


async def _carregar_comentario(comentario_id: int, db: AsyncSession) -> QuestaoComentario:
    c = (await db.execute(
        select(QuestaoComentario).where(QuestaoComentario.id == comentario_id)
    )).scalar_one_or_none()
    if c is None or c.deleted_at is not None:
        raise HTTPException(404, "comentário não encontrado")
    return c


@router.patch("/forum/{comentario_id}")
async def editar_comentario(
    comentario_id: int,
    req: EditarComentarioReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _carregar_comentario(comentario_id, db)
    if c.origem != "studia" or c.owner_uid != user.id:
        raise HTTPException(403, "você só pode editar os seus próprios comentários")
    texto = req.texto_md.strip()
    if not texto:
        raise HTTPException(422, "comentário vazio")
    c.texto_md = texto
    c.edited_at = func.now()
    await db.commit()
    await db.refresh(c)
    meu = (await db.execute(
        select(ComentarioVoto.valor).where(
            ComentarioVoto.comentario_id == c.id, ComentarioVoto.usuario_uid == user.id
        )
    )).scalar_one_or_none() or 0
    return _serializar_comentario(c, meu_voto=meu, user=user, respostas=[])


@router.delete("/forum/{comentario_id}")
async def excluir_comentario(
    comentario_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _carregar_comentario(comentario_id, db)
    dono = c.origem == "studia" and c.owner_uid == user.id
    if not (dono or user.is_admin):
        raise HTTPException(403, "sem permissão para excluir")
    c.deleted_at = func.now()
    await db.commit()
    return {"id": comentario_id, "removido": True}


@router.post("/questoes/{questao_id}/forum", status_code=status.HTTP_201_CREATED)
async def criar_comentario(
    questao_id: int,
    req: CriarComentarioReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Gate de escrita: só professor/admin escrevem no quadro dos professores.
    if req.quadro == "professores" and not user.is_professor:
        raise HTTPException(403, "apenas professores podem escrever no fórum dos professores")

    texto = req.texto_md.strip()
    if not texto:
        raise HTTPException(422, "comentário vazio")

    existe_q = (await db.execute(select(Questao.id).where(Questao.id == questao_id))).scalar_one_or_none()
    if not existe_q:
        raise HTTPException(404, "questao não encontrada")

    if req.parent_id is not None:
        pai = (await db.execute(
            select(QuestaoComentario).where(QuestaoComentario.id == req.parent_id)
        )).scalar_one_or_none()
        if pai is None or pai.questao_id != questao_id or pai.forum_tipo != req.quadro:
            raise HTTPException(400, "comentário pai inválido")
        if pai.deleted_at is not None:
            raise HTTPException(400, "não é possível responder a um comentário removido")
        if pai.parent_id is not None:
            raise HTTPException(400, "respostas só podem ser feitas a um comentário raiz")

    # Persona: só o admin no quadro professores ganha nome de cientista.
    persona = None
    if req.quadro == "professores" and user.is_admin:
        # Identidade coerente: reusa a persona que este admin já tem NESTA questão.
        minha = (await db.execute(
            select(QuestaoComentario.persona_nome).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == "professores",
                QuestaoComentario.owner_uid == user.id,
                QuestaoComentario.persona_nome.is_not(None),
            ).limit(1)
        )).scalar_one_or_none()
        if minha:
            persona = minha
        else:
            # Primeiro post deste admin na questão: sorteia evitando personas já usadas
            # por QUALQUER post (raiz ou resposta) no quadro professores desta questão.
            usadas = set((await db.execute(
                select(QuestaoComentario.persona_nome).where(
                    QuestaoComentario.questao_id == questao_id,
                    QuestaoComentario.forum_tipo == "professores",
                    QuestaoComentario.persona_nome.is_not(None),
                )
            )).scalars().all())
            persona = sortear_persona(usadas)

    c = QuestaoComentario(
        questao_id=questao_id,
        origem="studia",
        owner_uid=user.id,
        autor_nome=user.name,
        autor_tipo="professor" if req.quadro == "professores" else None,
        forum_tipo=req.quadro,
        persona_nome=persona,
        parent_id=req.parent_id,
        texto_md=texto,
        score=0,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _serializar_comentario(c, meu_voto=0, user=user, respostas=[])


class VotarReq(BaseModel):
    valor: int = Field(..., ge=-1, le=1)  # -1 | 0 | 1 (0 remove)


@router.post("/forum/{comentario_id}/voto")
async def votar_comentario(
    comentario_id: int,
    req: VotarReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = (await db.execute(
        select(QuestaoComentario).where(QuestaoComentario.id == comentario_id).with_for_update()
    )).scalar_one_or_none()
    if c is None or c.deleted_at is not None:
        raise HTTPException(404, "comentário não encontrado")
    if c.origem == "studia" and c.owner_uid == user.id:
        raise HTTPException(400, "você não pode votar no próprio comentário")

    voto = (await db.execute(
        select(ComentarioVoto).where(
            ComentarioVoto.comentario_id == comentario_id,
            ComentarioVoto.usuario_uid == user.id,
        )
    )).scalar_one_or_none()

    if req.valor == 0:
        if voto is not None:
            await db.delete(voto)
    elif voto is None:
        db.add(ComentarioVoto(comentario_id=comentario_id, usuario_uid=user.id, valor=req.valor))
    else:
        voto.valor = req.valor
    await db.flush()

    soma = (await db.execute(
        select(func.coalesce(func.sum(ComentarioVoto.valor), 0)).where(
            ComentarioVoto.comentario_id == comentario_id
        )
    )).scalar_one()
    c.score = int(c.curtidas or 0) + int(soma)
    await db.commit()
    return {"score": c.score, "meu_voto": req.valor}


_FORUM_IMG_TIPOS = {
    "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif",
}
_FORUM_IMG_MAX = 5 * 1024 * 1024  # 5 MB
_FORUM_KEY_RE = _re.compile(r"^forum/[0-9a-f-]{36}\.(png|jpg|webp|gif)$")


@router.post("/forum/upload")
async def upload_imagem_forum(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
) -> dict[str, Any]:
    ext = _FORUM_IMG_TIPOS.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(400, "tipo de imagem não suportado (use png, jpg, webp ou gif)")
    data = await file.read()
    if len(data) > _FORUM_IMG_MAX:
        raise HTTPException(400, "imagem acima de 5 MB")
    key = f"forum/{_uuid.uuid4()}.{ext}"
    upload_bytes(key, data, file.content_type)
    return {"url": f"/api/q/forum/imagem/{key}"}


@router.get("/forum/imagem/{key:path}")
async def imagem_forum(key: str) -> RedirectResponse:
    if not _FORUM_KEY_RE.match(key):
        raise HTTPException(404, "imagem não encontrada")
    return RedirectResponse(get_presigned_url(key), status_code=302)


# ─── Admin: gestão de roles de usuários ───────────────────────────────────
class PatchRoleReq(BaseModel):
    role: Literal["user", "professor", "admin"]


@router.get("/admin/usuarios")
async def admin_listar_usuarios(
    q: str = "",
    page: int = 1,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    page = max(1, page)
    por_pagina = 30
    termo = f"%{q.strip()}%"
    rows = (await db.execute(
        text(
            'SELECT id, email, name, COALESCE(role, \'user\') AS role, '
            'COALESCE(banned, false) AS banned, "createdAt" '
            'FROM "user" '
            "WHERE (:q = '' OR email ILIKE :termo OR name ILIKE :termo) "
            'ORDER BY "createdAt" DESC '
            "LIMIT :lim OFFSET :off"
        ),
        {"q": q.strip(), "termo": termo, "lim": por_pagina + 1, "off": (page - 1) * por_pagina},
    )).mappings().all()
    tem_mais = len(rows) > por_pagina
    usuarios = [
        {
            "id": r["id"], "email": r["email"], "name": r["name"],
            "role": r["role"], "banned": bool(r["banned"]),
            "created_at": r["createdAt"].isoformat() if r["createdAt"] else None,
        }
        for r in rows[:por_pagina]
    ]
    return {"usuarios": usuarios, "page": page, "tem_mais": tem_mais}


@router.patch("/admin/usuarios/{uid}/role")
async def admin_trocar_role(
    uid: str,
    req: PatchRoleReq,
    admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if uid == admin.id:
        raise HTTPException(400, "você não pode alterar o seu próprio papel")
    existe = (await db.execute(
        text('SELECT 1 FROM "user" WHERE id = :id'), {"id": uid}
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(404, "usuário não encontrado")
    await db.execute(
        text('UPDATE "user" SET role = :role, "updatedAt" = now() WHERE id = :id'),
        {"role": req.role, "id": uid},
    )
    await db.commit()
    return {"id": uid, "role": req.role, "aviso": "O novo papel só terá efeito após o próximo login do usuário."}


@router.get("/{questao_id}")
async def detalhe(questao_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    stmt = (
        select(Questao)
        .options(selectinload(Questao.alternativas), selectinload(Questao.assuntos))
        .where(Questao.id == questao_id)
    )
    q = (await db.execute(stmt)).scalar_one_or_none()
    if not q:
        raise HTTPException(404, f"questao {questao_id} not found")

    # Resolve taxonomia (poderia ser selectinload mas com sigla é fácil)
    banca = (await db.execute(select(Banca).where(Banca.id == q.banca_id))).scalar_one_or_none() if q.banca_id else None
    orgao = (await db.execute(select(Orgao).where(Orgao.id == q.orgao_id))).scalar_one_or_none() if q.orgao_id else None
    cargo = (await db.execute(select(Cargo).where(Cargo.id == q.cargo_id))).scalar_one_or_none() if q.cargo_id else None
    materia = (await db.execute(select(Materia).where(Materia.id == q.materia_id))).scalar_one_or_none() if q.materia_id else None

    return {
        "id": q.id,
        "id_externo": q.id_externo,
        "enunciado_md": q.enunciado_md,
        "enunciado_html": q.enunciado_html,
        "tipo": q.tipo,
        "gabarito": q.gabarito,
        "status": q.status,
        "banca": {"id": banca.id, "sigla": banca.sigla, "nome": banca.nome} if banca else None,
        "orgao": {"id": orgao.id, "sigla": orgao.sigla, "nome": orgao.nome} if orgao else None,
        "cargo": {"id": cargo.id, "nome": cargo.nome, "ano": cargo.ano} if cargo else None,
        "materia": {"id": materia.id, "nome": materia.nome} if materia else None,
        "assuntos": [{"id": a.id, "nome": a.nome} for a in q.assuntos],
        "alternativas": [
            {"id": alt.id, "letra": alt.letra, "texto_md": alt.texto_md, "texto_html": alt.texto_html, "correta": alt.correta, "ordem": alt.ordem}
            for alt in sorted(q.alternativas, key=lambda x: x.ordem or 0)
        ],
        "forum_count": (await db.execute(
            select(func.count()).select_from(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == "alunos",
                QuestaoComentario.deleted_at.is_(None),
            )
        )).scalar_one(),
        "forum_count_professores": (await db.execute(
            select(func.count()).select_from(QuestaoComentario).where(
                QuestaoComentario.questao_id == questao_id,
                QuestaoComentario.forum_tipo == "professores",
                QuestaoComentario.deleted_at.is_(None),
            )
        )).scalar_one(),
    }
