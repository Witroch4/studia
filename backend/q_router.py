"""Endpoints `/api/q/*` para witdev-tec-master.

Proxy fino sobre Meilisearch + Postgres. Replicam o padrão arquitetural do TC:
- `/api/q/count` → contagem leve + facetas (cacheável)
- `/api/q/search` → lista paginada
- `/api/q/{id}` → detalhe de questão
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Integer, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import (
    Alternativa,
    Banca,
    CalculadoraHistorico,
    CadernoQuestoes,
    Cargo,
    Materia,
    Orgao,
    Questao,
    QuestaoAnotacao,
    Resolucao,
)

import re as _re

router = APIRouter(prefix="/api/q", tags=["questoes"])

MEILI_URL = os.getenv("MEILI_URL", "http://localhost:7700")
MEILI_KEY = os.getenv("MEILI_KEY", "dev_master_key_studia_2026")
SCRAPER_URL = os.getenv("SCRAPER_URL", "http://scraper:8090")

DEFAULT_FACETS = ["banca", "orgao", "cargo", "ano", "materia", "assuntos", "tipo", "status"]


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


class SearchReq(CountReq):
    page: int = 1
    page_size: int = 20
    sort: list[str] | None = None


def _to_meili_filter(filtros: dict[str, list]) -> str | None:
    parts: list[str] = []
    for k, vals in filtros.items():
        if not vals:
            continue
        quoted = [f'"{v}"' if isinstance(v, str) else str(v) for v in vals]
        parts.append("(" + " OR ".join(f"{k} = {v}" for v in quoted) + ")")
    return " AND ".join(parts) if parts else None


async def _meili_search(payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(
            f"{MEILI_URL}/indexes/questoes/search",
            headers={"Authorization": f"Bearer {MEILI_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()


# ─── Endpoints ───────────────────────────────────────────


@router.post("/count")
async def count(req: CountReq) -> dict[str, Any]:
    """Padrão TC: contagem leve + facetas para painel UI."""
    payload = {
        "q": req.q,
        "limit": 0,  # NÃO traz hits
        "facets": DEFAULT_FACETS,
    }
    f = _to_meili_filter(req.filtros)
    if f:
        payload["filter"] = f
    data = await _meili_search(payload)
    return {
        "total": data.get("estimatedTotalHits", 0),
        "facets": data.get("facetDistribution", {}),
        "ms": data.get("processingTimeMs", 0),
    }


@router.post("/search")
async def search(req: SearchReq) -> dict[str, Any]:
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


@router.post("/coletar")
async def coletar(req: ColetarReq, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Coleta o caderno via endpoint OURO + dedup automática + reindexa Meili.

    Idempotente: a coluna `id_externo` em `questoes` é UNIQUE, então repetir
    o mesmo caderno faz UPSERT sem duplicar. Adicionalmente, o `ScrapeState`
    do scraper marca por idQuestao e pula reprocessamento.
    """
    caderno_id = extrair_caderno_id(req.url)

    # Snapshot pré-coleta (para reportar dedup)
    pre_total = (await db.execute(select(func.count(Questao.id)))).scalar_one()

    # Chama scraper via HTTP (long-running ok porque /imprimir é rápido)
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=600, write=10, pool=30)) as c:
        r = await c.post(
            f"{SCRAPER_URL}/run/caderno-imprimir",
            json={"caderno_id": caderno_id, "relogin": req.relogin},
        )
        if r.status_code != 200:
            raise HTTPException(502, f"scraper falhou: {r.status_code} {r.text[:300]}")
        resultado = r.json()

    # Snapshot pós-coleta
    pos_total = (await db.execute(select(func.count(Questao.id)))).scalar_one()
    novas = pos_total - pre_total
    atualizadas = max(0, resultado.get("ok", 0) - novas)

    # Reindexa no Meilisearch (apenas as do caderno, em batch)
    novas_questoes = await _meili_reindex_recentes(db, limit=resultado.get("ok", 0))

    return {
        "caderno_id": caderno_id,
        "scraper": resultado,
        "pre_total": pre_total,
        "pos_total": pos_total,
        "novas": novas,
        "atualizadas": atualizadas,
        "meili_reindexadas": novas_questoes,
    }


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
    limite: int = Field(default=500, ge=1, le=30000)
    ordem: str = Field(default="aleatoria", description="aleatoria | id | ano")


@router.post("/cadernos")
async def gerar_caderno(req: GerarCadernoReq, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Cria um caderno materializando os IDs das questões que matcham os filtros.

    Replica o padrão TC: armazena IDs concretos (não apenas a query) — assim o
    histórico do caderno fica estável mesmo se novas questões forem adicionadas.
    """
    # 1. Busca IDs via Meili
    payload = {
        "q": req.q,
        "limit": req.limite,
        "offset": 0,
        "attributesToRetrieve": ["id"],
    }
    f = _to_meili_filter(req.filtros)
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

    # 2. Persiste o caderno
    caderno = CadernoQuestoes(
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


@router.get("/cadernos/{caderno_id}")
async def detalhe_caderno(caderno_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "Caderno não encontrado")
    return {
        "id": cad.id,
        "nome": cad.nome,
        "pasta": cad.pasta,
        "filtros": cad.filtros,
        "total": cad.total,
        "question_ids": cad.question_ids or [],
        "created_at": cad.created_at.isoformat() if cad.created_at else None,
    }


@router.get("/cadernos")
async def listar_cadernos(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    from sqlalchemy import desc
    rows = (await db.execute(select(CadernoQuestoes).order_by(desc(CadernoQuestoes.created_at)).limit(50))).scalars().all()
    return [
        {"id": c.id, "nome": c.nome, "total": c.total, "pasta": c.pasta,
         "created_at": c.created_at.isoformat() if c.created_at else None}
        for c in rows
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
        "usuario_id": row.usuario_id if row else None,
        "caderno_id": caderno_id,
        "questao_id": questao_id,
        "canvas_json": row.canvas_json if row else _empty_canvas(),
        "strikes_json": row.strikes_json if row else _empty_strikes(),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def _annotation_scope(caderno_id: int, questao_id: int):
    return select(QuestaoAnotacao).where(
        QuestaoAnotacao.usuario_id.is_(None),
        QuestaoAnotacao.caderno_id == caderno_id,
        QuestaoAnotacao.questao_id == questao_id,
    )


@router.post("/{questao_id}/responder")
async def responder(questao_id: int, req: ResponderReq, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    q = (await db.execute(
        select(Questao).options(selectinload(Questao.alternativas)).where(Questao.id == questao_id)
    )).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "questao não encontrada")

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
        resposta=resp,
        acertou=acertou,
        tempo_segundos=req.tempo_segundos,
    )
    db.add(res)
    await db.commit()

    # Retorna stats atualizadas
    total = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    erros = total - acertos
    return {
        "acertou": acertou,
        "gabarito": q.gabarito,
        "stats": {"resolvidas": total, "acertos": acertos, "erros": erros},
    }


@router.get("/{questao_id}/estatisticas")
async def estatisticas(questao_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    total = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(Resolucao.questao_id == questao_id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    return {"resolvidas": total, "acertos": acertos, "erros": total - acertos}


@router.get("/cadernos/{caderno_id}/estatisticas")
async def estatisticas_caderno(caderno_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    total = (await db.execute(select(func.count()).where(Resolucao.caderno_id == caderno_id))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(Resolucao.caderno_id == caderno_id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    return {
        "caderno_id": caderno_id,
        "questoes_total": cad.total,
        "resolvidas": total,
        "acertos": acertos,
        "erros": total - acertos,
    }


@router.get("/cadernos/{caderno_id}/stats-detalhe")
async def stats_detalhe(caderno_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Estatísticas analíticas: por matéria/assunto/banca + tempo + histórico."""
    from models import questao_assunto

    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")

    # ─── Resumo ───
    total = (await db.execute(select(func.count()).where(Resolucao.caderno_id == caderno_id))).scalar_one()
    acertos = (await db.execute(select(func.count()).where(Resolucao.caderno_id == caderno_id, Resolucao.acertou == True))).scalar_one()  # noqa: E712
    tempo_total = (await db.execute(select(func.coalesce(func.sum(Resolucao.tempo_segundos), 0)).where(Resolucao.caderno_id == caderno_id))).scalar_one()
    tempo_medio = (await db.execute(select(func.coalesce(func.avg(Resolucao.tempo_segundos), 0)).where(Resolucao.caderno_id == caderno_id))).scalar_one()

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
        .where(Resolucao.caderno_id == caderno_id)
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
        .where(Resolucao.caderno_id == caderno_id)
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
        .where(Resolucao.caderno_id == caderno_id)
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
        .where(Resolucao.caderno_id == caderno_id)
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
async def gabarito_caderno(caderno_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Tabela: idx → questao_id → idExterno → gabarito (modo Gabarito do TC)."""
    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
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
async def indice_caderno(caderno_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Índice navegável — lista compacta de todas as questões do caderno."""
    from models import Assunto

    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
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


@router.get("/cadernos/{caderno_id}/questoes/{questao_id}/annotations")
async def get_annotations(caderno_id: int, questao_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    q = (await db.execute(select(Questao.id).where(Questao.id == questao_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "questao não encontrada")
    if questao_id not in (cad.question_ids or []):
        raise HTTPException(404, "questao não pertence ao caderno")

    row = (await db.execute(_annotation_scope(caderno_id, questao_id))).scalar_one_or_none()
    return _annotation_response(row, caderno_id, questao_id)


@router.put("/cadernos/{caderno_id}/questoes/{questao_id}/annotations")
async def put_annotations(
    caderno_id: int,
    questao_id: int,
    req: AnnotationReq,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = (await db.execute(select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id))).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    q = (await db.execute(select(Questao.id).where(Questao.id == questao_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "questao não encontrada")
    if questao_id not in (cad.question_ids or []):
        raise HTTPException(404, "questao não pertence ao caderno")

    row = (await db.execute(_annotation_scope(caderno_id, questao_id))).scalar_one_or_none()
    if row:
        row.canvas_json = req.canvas_json
        row.strikes_json = req.strikes_json
        await db.commit()
    else:
        row = QuestaoAnotacao(
            usuario_id=None,
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
            row = (await db.execute(_annotation_scope(caderno_id, questao_id))).scalar_one_or_none()
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from sqlalchemy import desc

    stmt = select(CalculadoraHistorico).where(CalculadoraHistorico.usuario_id.is_(None))
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
                "usuario_id": row.usuario_id,
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
async def create_calculator_history(req: CalculatorHistoryReq, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    expression = req.expression.strip()
    result = req.result.strip()
    if not expression or not result:
        raise HTTPException(422, "expression e result são obrigatórios")

    row = CalculadoraHistorico(
        usuario_id=None,
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
        "usuario_id": row.usuario_id,
        "caderno_id": row.caderno_id,
        "questao_id": row.questao_id,
        "expression": row.expression,
        "result": row.result,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/calculator/history/{item_id}")
async def delete_calculator_history(item_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    row = (await db.execute(
        select(CalculadoraHistorico).where(
            CalculadoraHistorico.id == item_id,
            CalculadoraHistorico.usuario_id.is_(None),
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "historico não encontrado")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


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
            {"id": alt.id, "letra": alt.letra, "texto_md": alt.texto_md, "correta": alt.correta, "ordem": alt.ordem}
            for alt in sorted(q.alternativas, key=lambda x: x.ordem or 0)
        ],
    }
