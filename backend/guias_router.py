"""Endpoints `/api/q/guias/*` — importação de Guias do TecConcursos.

Orquestra a cascata guia → pasta → cadernos → questões reusando o pipeline de
coleta de caderno já existente (`/api/q/coletar` → scraper TaskIQ/NATS). O guia
apenas:

1. resolve a URL base (chama o scraper `/guia/resolver`);
2. faz upsert de `Guia` + `GuiaCaderno`;
3. dispara "salvar todos" no TC e enfileira a coleta de cada caderno;
4. materializa um `CadernoQuestoes` por caderno (mesmo nome, ordem real);
5. audita esperado vs coletado vs materializado.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import CadernoQuestoes, Guia, GuiaCaderno

router = APIRouter(prefix="/api/q/guias", tags=["guias"])

SCRAPER_URL = os.getenv("SCRAPER_URL", "http://scraper:8090")

# Timeouts: resolver baixa 2 HTMLs + 1 JSON do TC (pode demorar com human-mode).
_RESOLVE_TIMEOUT = httpx.Timeout(connect=5, read=90, write=10, pool=95)
_SAVE_TIMEOUT = httpx.Timeout(connect=5, read=120, write=10, pool=125)
# Publicar no NATS pode demorar quando o worker está ocupado em série.
_ENQUEUE_TIMEOUT = httpx.Timeout(connect=3, read=30, write=5, pool=35)


# ─── Schemas ─────────────────────────────────────────────


class ImportarGuiaReq(BaseModel):
    url: str = Field(..., description="URL base do guia TC (ex.: /guias/oab-2026)")
    relogin: bool = Field(False, description="Refazer login Playwright antes")
    page_size: int = Field(200, ge=1, le=200)
    iniciar_coleta: bool = Field(
        True, description="Enfileirar coleta dos cadernos logo após importar"
    )


class MaterializarReq(BaseModel):
    forcar: bool = Field(
        False, description="Materializar mesmo cadernos com coleta incompleta"
    )


# ─── Helpers ─────────────────────────────────────────────


async def _scraper_post(path: str, json: dict[str, Any], timeout: httpx.Timeout) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{SCRAPER_URL}{path}", json=json)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, f"scraper demorou para responder em {path}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(502, f"scraper falhou ({path}): {r.status_code} {r.text[:300]}")
    return r.json()


async def _enqueue_caderno(caderno_id: int, expected_total: int, page_size: int) -> dict[str, Any]:
    """Enfileira a coleta de um caderno. Tenta 2× antes de desistir; nunca derruba
    o import (mas o chamador registra a falha para retomada posterior)."""
    payload = {
        "caderno_id": caderno_id,
        "expected_total": expected_total or None,
        "page_size": page_size,
        "enqueue_limit": 1,
        "discover_total": False,
        "relogin": False,
    }
    for _ in range(2):
        try:
            async with httpx.AsyncClient(timeout=_ENQUEUE_TIMEOUT) as c:
                r = await c.post(f"{SCRAPER_URL}/enqueue/caderno", json=payload)
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            continue
    return {}


def _guia_dict(g: Guia) -> dict[str, Any]:
    return {
        "id": g.id,
        "tc_guia_id": g.tc_guia_id,
        "slug": g.slug,
        "url": g.url,
        "nome": g.nome,
        "banca": g.banca,
        "tc_pasta_id": g.tc_pasta_id,
        "status": g.status,
        "total_cadernos": g.total_cadernos,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


# ─── Endpoints ───────────────────────────────────────────


@router.post("/importar", status_code=status.HTTP_202_ACCEPTED)
async def importar_guia(req: ImportarGuiaReq, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Resolve o guia, persiste cadernos, salva no TC e enfileira a coleta."""
    resolved = await _scraper_post(
        "/guia/resolver", {"url": req.url, "relogin": req.relogin}, _RESOLVE_TIMEOUT
    )

    tc_guia_id = int(resolved["tc_guia_id"])
    # `cadernos_in` enriquece capítulos/ordem; a fonte autoritativa dos ids vem
    # dos itens da pasta após "salvar todos" (ver `_merge_cadernos`).
    cadernos_in = resolved.get("cadernos", [])

    # Upsert Guia
    guia = (
        await db.execute(select(Guia).where(Guia.tc_guia_id == tc_guia_id))
    ).scalar_one_or_none()
    if guia is None:
        guia = Guia(tc_guia_id=tc_guia_id)
        db.add(guia)
    guia.slug = resolved.get("slug")
    guia.url = resolved.get("url") or req.url
    guia.nome = resolved.get("nome") or f"Guia {tc_guia_id}"
    guia.banca = resolved.get("banca")
    guia.status = "saving"
    await db.flush()

    # Salvar todos os cadernos no TC (cria/reaproveita a pasta). Os itens da
    # pasta são a fonte AUTORITATIVA dos ids/nomes dos cadernos de questões —
    # `listar-pelo-guia` só traz o id quando o usuário já tinha salvo o guia.
    saved = await _scraper_post(
        "/guia/salvar-cadernos", {"tc_guia_id": tc_guia_id}, _SAVE_TIMEOUT
    )
    pasta_id = saved.get("pasta_id")
    if pasta_id:
        guia.tc_pasta_id = int(pasta_id)

    cadernos = _merge_cadernos(saved.get("itens") or [], cadernos_in)
    if not cadernos:
        raise HTTPException(502, "Não foi possível obter os cadernos do guia (pasta vazia).")
    guia.total_cadernos = len(cadernos)

    # Upsert GuiaCaderno
    existing = {
        gc.tc_caderno_id: gc
        for gc in (
            await db.execute(select(GuiaCaderno).where(GuiaCaderno.guia_id == guia.id))
        ).scalars().all()
    }
    for c in cadernos:
        tc_caderno_id = int(c["tc_caderno_id"])
        gc = existing.get(tc_caderno_id)
        if gc is None:
            gc = GuiaCaderno(guia_id=guia.id, tc_caderno_id=tc_caderno_id)
            db.add(gc)
        gc.tc_caderno_base = c.get("caderno_base_id")
        gc.nome = c["nome"]
        gc.disciplina = c["nome"]
        gc.total_questoes = int(c.get("total_questoes") or 0)
        gc.total_capitulos = int(c.get("total_capitulos") or 0)
        gc.ordem = c.get("ordem")
        if gc.status not in {"materialized"}:
            gc.status = "pending"
    await db.commit()
    await db.refresh(guia)

    # Enfileira a coleta de cada caderno (serial no worker; aqui só publica)
    enqueued = 0
    falhas: list[int] = []
    if req.iniciar_coleta:
        for c in cadernos:
            res = await _enqueue_caderno(
                int(c["tc_caderno_id"]), int(c.get("total_questoes") or 0), req.page_size
            )
            if res.get("enqueued_units", 0) > 0 or res.get("job_id"):
                enqueued += 1
            else:
                falhas.append(int(c["tc_caderno_id"]))
        guia.status = "collecting"
        await db.commit()
        await db.refresh(guia)

    message = (
        "Guia importado. Cadernos salvos e coleta enfileirada; o worker processa em série."
        if req.iniciar_coleta
        else "Guia importado. Cadernos salvos; inicie a coleta quando quiser."
    )
    if falhas:
        message += f" {len(falhas)} caderno(s) não enfileirados — use 'Retomar coleta' no guia."

    return {
        **_guia_dict(guia),
        "cadernos": len(cadernos),
        "enqueued": enqueued,
        "falhas": falhas,
        "message": message,
    }


def _merge_cadernos(itens_pasta: list[dict], cadernos_guia: list[dict]) -> list[dict]:
    """Combina itens da pasta (id/nome/quantidade autoritativos) com metadados
    de `listar-pelo-guia` (capítulos, base, ordem) casando por nome.

    Se a pasta veio vazia (guia já salvo, ou TC não retornou), cai para a lista
    do guia (que terá ids quando o usuário já possuía o guia salvo).
    """
    by_nome = {c["nome"]: c for c in cadernos_guia}
    if itens_pasta:
        out = []
        for it in itens_pasta:
            nome = it.get("nome") or ""
            extra = by_nome.get(nome, {})
            out.append(
                {
                    "tc_caderno_id": int(it["id"]),
                    "nome": nome or extra.get("nome") or f"Caderno {it['id']}",
                    "total_questoes": int(it.get("quantidadeItens") or extra.get("total_questoes") or 0),
                    "total_capitulos": int(extra.get("total_capitulos") or 0),
                    "caderno_base_id": extra.get("caderno_base_id"),
                    "ordem": extra.get("ordem"),
                }
            )
        return out
    return [
        {
            "tc_caderno_id": int(c["tc_caderno_id"]),
            "nome": c["nome"],
            "total_questoes": int(c.get("total_questoes") or 0),
            "total_capitulos": int(c.get("total_capitulos") or 0),
            "caderno_base_id": c.get("caderno_base_id"),
            "ordem": c.get("ordem"),
        }
        for c in cadernos_guia
        if c.get("tc_caderno_id")
    ]


@router.get("/buscar-tc")
async def buscar_guias_tc(termo: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Busca guias no TC por palavra-chave e marca quais já foram importados."""
    try:
        async with httpx.AsyncClient(timeout=_SAVE_TIMEOUT) as c:
            r = await c.get(f"{SCRAPER_URL}/guia/buscar", params={"termo": termo})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"scraper indisponível: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(502, f"scraper falhou na busca: {r.status_code}")
    encontrados = r.json().get("guias", [])

    # Casa o slug do edital (ex.: "oab-2026") com o slug salvo, que inclui o
    # cargo (ex.: "oab-2026/nacional-unificado-oab"). Match por prefixo.
    salvos = (
        await db.execute(select(Guia.id, Guia.slug, Guia.url))
    ).all()
    for g in encontrados:
        edital = g["slug"]
        g["guia_id"] = next(
            (
                gid
                for gid, slug, url in salvos
                if (slug and (slug == edital or slug.startswith(f"{edital}/")))
                or (url and f"/guias/{edital}/" in url)
                or (url and url.rstrip("/").endswith(f"/guias/{edital}"))
            ),
            None,
        )
    return {"termo": termo, "guias": encontrados}


@router.get("")
async def listar_guias(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Lista guias importados com progresso agregado (cards estilo TC)."""
    from sqlalchemy import desc

    guias = (
        await db.execute(select(Guia).order_by(desc(Guia.created_at)))
    ).scalars().all()
    if not guias:
        return {"guias": []}

    guia_ids = [g.id for g in guias]
    rows = (
        await db.execute(
            select(GuiaCaderno).where(GuiaCaderno.guia_id.in_(guia_ids))
        )
    ).scalars().all()
    cadernos_by_guia: dict[int, list[GuiaCaderno]] = {}
    for gc in rows:
        cadernos_by_guia.setdefault(gc.guia_id, []).append(gc)

    # Contagem coletada por caderno (membership)
    coletado = await _coletado_por_caderno(db, [gc.tc_caderno_id for gc in rows])

    out = []
    for g in guias:
        cads = cadernos_by_guia.get(g.id, [])
        esperado = sum(c.total_questoes for c in cads)
        col = sum(coletado.get(c.tc_caderno_id, 0) for c in cads)
        materializados = sum(1 for c in cads if c.caderno_id)
        out.append(
            {
                **_guia_dict(g),
                "cadernos_total": len(cads),
                "questoes_esperadas": esperado,
                "questoes_coletadas": col,
                "cadernos_materializados": materializados,
                "pct": round((col / esperado) * 100, 1) if esperado else 0.0,
            }
        )
    return {"guias": out}


@router.get("/{guia_id}")
async def detalhe_guia(guia_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Detalhe do guia: cadernos + progresso de coleta + materialização."""
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")

    cads = (
        await db.execute(
            select(GuiaCaderno)
            .where(GuiaCaderno.guia_id == guia_id)
            .order_by(GuiaCaderno.ordem.is_(None), GuiaCaderno.ordem, GuiaCaderno.nome)
        )
    ).scalars().all()
    tc_ids = [c.tc_caderno_id for c in cads]
    coletado = await _coletado_por_caderno(db, tc_ids)
    jobs = await _jobs_por_caderno(db, tc_ids)

    cadernos_out = []
    for c in cads:
        col = coletado.get(c.tc_caderno_id, 0)
        job = jobs.get(c.tc_caderno_id, {})
        cadernos_out.append(
            {
                "id": c.id,
                "tc_caderno_id": c.tc_caderno_id,
                "nome": c.nome,
                "total_questoes": c.total_questoes,
                "total_capitulos": c.total_capitulos,
                "ordem": c.ordem,
                "questoes_coletadas": col,
                "pct": round((col / c.total_questoes) * 100, 1) if c.total_questoes else 0.0,
                "caderno_id": c.caderno_id,
                "status": _caderno_status(c, col, job),
                "job_status": job.get("status"),
                "done_units": job.get("done_units"),
                "total_units": job.get("total_units"),
                "blocked_units": job.get("blocked_units"),
            }
        )

    esperado = sum(c.total_questoes for c in cads)
    col_total = sum(coletado.get(c.tc_caderno_id, 0) for c in cads)
    return {
        **_guia_dict(guia),
        "questoes_esperadas": esperado,
        "questoes_coletadas": col_total,
        "pct": round((col_total / esperado) * 100, 1) if esperado else 0.0,
        "cadernos": cadernos_out,
    }


@router.post("/{guia_id}/coletar")
async def coletar_guia(guia_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """(Re)enfileira a coleta dos cadernos do guia que ainda não estão completos.

    Idempotente: cadernos já `done` no ledger são ignorados pelo scraper.
    """
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")

    cads = (
        await db.execute(select(GuiaCaderno).where(GuiaCaderno.guia_id == guia_id))
    ).scalars().all()
    jobs = await _jobs_por_caderno(db, [c.tc_caderno_id for c in cads])

    enqueued = 0
    falhas: list[int] = []
    for c in cads:
        if jobs.get(c.tc_caderno_id, {}).get("status") == "done":
            continue
        res = await _enqueue_caderno(c.tc_caderno_id, c.total_questoes, 200)
        if res.get("enqueued_units", 0) > 0 or res.get("job_id"):
            enqueued += 1
        else:
            falhas.append(c.tc_caderno_id)
    if enqueued:
        guia.status = "collecting"
        await db.commit()
    return {"guia_id": guia_id, "enqueued": enqueued, "falhas": falhas}


@router.post("/{guia_id}/materializar")
async def materializar_guia(
    guia_id: int, req: MaterializarReq | None = None, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Cria/atualiza um CadernoQuestoes por caderno com coleta concluída.

    Por padrão só materializa cadernos completos (job `done` ou coletado ≥
    esperado). Use `forcar=true` para incluir cadernos parciais.
    Idempotente por `CadernoQuestoes.tc_caderno_id`. Usa a ordem real (membership).
    """
    forcar = bool(req and req.forcar)
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")

    cads = (
        await db.execute(select(GuiaCaderno).where(GuiaCaderno.guia_id == guia_id))
    ).scalars().all()
    jobs = await _jobs_por_caderno(db, [c.tc_caderno_id for c in cads])

    materializados = []
    pulados = 0
    for c in cads:
        ids = await _question_ids_ordenados(db, c.tc_caderno_id)
        if not ids:
            continue
        job = jobs.get(c.tc_caderno_id, {})
        completo = (
            job.get("status") == "done"
            or (c.total_questoes > 0 and len(ids) >= c.total_questoes)
        )
        if not completo and not forcar:
            pulados += 1
            continue
        caderno = (
            await db.execute(
                select(CadernoQuestoes).where(CadernoQuestoes.tc_caderno_id == c.tc_caderno_id)
            )
        ).scalar_one_or_none()
        if caderno is None:
            caderno = CadernoQuestoes(
                nome=c.nome,
                pasta=guia.nome,
                tc_caderno_id=c.tc_caderno_id,
            )
            db.add(caderno)
        caderno.nome = c.nome
        caderno.pasta = guia.nome
        caderno.question_ids = ids
        caderno.total = len(ids)
        await db.flush()
        c.caderno_id = caderno.id
        c.status = "materialized"
        materializados.append(
            {"tc_caderno_id": c.tc_caderno_id, "caderno_id": caderno.id, "total": len(ids)}
        )

    if cads and all(c.status == "materialized" for c in cads):
        guia.status = "done"
    await db.commit()
    return {
        "guia_id": guia_id,
        "materializados": materializados,
        "total": len(materializados),
        "pulados_incompletos": pulados,
    }


@router.get("/{guia_id}/auditoria")
async def auditoria_guia(guia_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Relatório ponta a ponta: esperado vs coletado vs materializado por caderno."""
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")

    cads = (
        await db.execute(select(GuiaCaderno).where(GuiaCaderno.guia_id == guia_id))
    ).scalars().all()
    tc_ids = [c.tc_caderno_id for c in cads]
    coletado = await _coletado_por_caderno(db, tc_ids)
    jobs = await _jobs_por_caderno(db, tc_ids)

    materializado_total = {}
    if tc_ids:
        rows = (
            await db.execute(
                select(CadernoQuestoes.tc_caderno_id, CadernoQuestoes.total).where(
                    CadernoQuestoes.tc_caderno_id.in_(tc_ids)
                )
            )
        ).all()
        materializado_total = {r[0]: r[1] for r in rows}

    itens = []
    for c in cads:
        col = coletado.get(c.tc_caderno_id, 0)
        job = jobs.get(c.tc_caderno_id, {})
        mat = materializado_total.get(c.tc_caderno_id)
        completo = c.total_questoes > 0 and col >= c.total_questoes
        itens.append(
            {
                "tc_caderno_id": c.tc_caderno_id,
                "nome": c.nome,
                "esperado": c.total_questoes,
                "coletado": col,
                "materializado": mat,
                "faltam": max(0, c.total_questoes - col),
                "job_status": job.get("status"),
                "blocked_units": job.get("blocked_units"),
                "completo": completo,
                "divergencia": (not completo) or (mat is not None and mat != col),
            }
        )

    return {
        "guia_id": guia_id,
        "nome": guia.nome,
        "esperado_total": sum(c.total_questoes for c in cads),
        "coletado_total": sum(coletado.get(c.tc_caderno_id, 0) for c in cads),
        "cadernos_completos": sum(1 for i in itens if i["completo"]),
        "cadernos_total": len(cads),
        "itens": itens,
    }


# ─── Consultas auxiliares (ledger + membership) ──────────


async def _table_exists(db: AsyncSession, qualified_name: str) -> bool:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        name = qualified_name.split(".")[-1]
        row = (
            await db.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                {"n": name},
            )
        ).first()
        return row is not None
    reg = (
        await db.execute(text("SELECT to_regclass(:n)"), {"n": qualified_name})
    ).scalar()
    return reg is not None


async def _coletado_por_caderno(db: AsyncSession, tc_ids: list[int]) -> dict[int, int]:
    if not tc_ids or not await _table_exists(db, "public.tc_caderno_questoes"):
        return {}
    rows = (
        await db.execute(
            text(
                """
                SELECT caderno_id, COUNT(*) AS n
                FROM tc_caderno_questoes
                WHERE caderno_id IN :ids
                GROUP BY caderno_id
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": tc_ids},
        )
    ).all()
    return {int(r[0]): int(r[1]) for r in rows}


async def _jobs_por_caderno(db: AsyncSession, tc_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not tc_ids or not await _table_exists(db, "public.tc_jobs"):
        return {}
    rows = (
        await db.execute(
            text(
                """
                SELECT CAST(external_id AS BIGINT) AS caderno_id, status,
                       total_units, done_units, blocked_units, failed_units
                FROM tc_jobs
                WHERE kind = 'caderno' AND CAST(external_id AS BIGINT) IN :ids
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": tc_ids},
        )
    ).mappings().all()
    return {int(r["caderno_id"]): dict(r) for r in rows}


async def _question_ids_ordenados(db: AsyncSession, tc_caderno_id: int) -> list[int]:
    if not await _table_exists(db, "public.tc_caderno_questoes"):
        return []
    rows = (
        await db.execute(
            text(
                """
                SELECT questao_id
                FROM tc_caderno_questoes
                WHERE caderno_id = :cid
                ORDER BY posicao
                """
            ),
            {"cid": tc_caderno_id},
        )
    ).all()
    return [int(r[0]) for r in rows]


def _caderno_status(c: GuiaCaderno, coletado: int, job: dict[str, Any]) -> str:
    if c.caderno_id:
        return "materialized"
    if c.total_questoes and coletado >= c.total_questoes:
        return "collected"
    job_status = job.get("status")
    if job_status == "blocked":
        return "blocked"
    if job_status in {"running", "pending"} or coletado > 0:
        return "collecting"
    return "pending"
