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

from auth import CurrentUser, get_current_user_opt, require_admin, require_user
from database import get_db
from entitlements import acesso_pro_ativo
from models import CadernoQuestoes, CadernoSalvo, Guia, GuiaCaderno

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
    apenas_catalogar: bool = Field(
        False,
        description="Só resolver+salvar metadados agora (sem coletar). Padrão: "
        "False = adiciona à fila de coleta serial.",
    )


class ImportarLoteReq(BaseModel):
    urls: list[str] = Field(..., min_length=1, description="URLs de guias do TC")


class MaterializarReq(BaseModel):
    forcar: bool = Field(
        False, description="Materializar mesmo cadernos com coleta incompleta"
    )
    tc_caderno_id: int | None = Field(
        None, description="Se informado, materializa só esse caderno do guia"
    )


class SalvarReq(BaseModel):
    tc_caderno_id: int | None = Field(
        None,
        description="Se informado, salva só essa matéria; senão salva todas as "
        "matérias prontas do guia",
    )


class AtualizarGuiaReq(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=512, description="Novo nome")
    pro_only: bool | None = Field(None, description="Restringir o guia a contas PRO")


class RenomearGuiaCadernoReq(BaseModel):
    nome: str = Field(..., min_length=1, max_length=512, description="Novo nome do caderno")


class CriarGuiaManualReq(BaseModel):
    nome: str = Field(..., min_length=1, max_length=512)
    banca: str | None = Field(None, max_length=128)
    pro_only: bool = Field(False)
    caderno_ids: list[int] = Field(
        ..., min_length=1, description="IDs de CadernoQuestoes na ordem de estudo"
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
        "pro_only": bool(g.pro_only),
        "total_cadernos": g.total_cadernos,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


# ─── Endpoints ───────────────────────────────────────────


@router.post("/importar", status_code=status.HTTP_202_ACCEPTED)
async def importar_guia(
    req: ImportarGuiaReq,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Padrão: adiciona o guia à fila de coleta serial (resolve preguiçoso, na
    vez do guia). Com `apenas_catalogar=true`: resolve+salva metadados agora,
    sem coletar."""
    import guia_service

    if req.apenas_catalogar:
        try:
            guia, cadernos = await guia_service.resolver_e_salvar(
                db, url=req.url, relogin=req.relogin, page_size=req.page_size
            )
        except ValueError as exc:
            raise HTTPException(502, str(exc))
        guia.status = "pending"
        await db.commit()
        await db.refresh(guia)
        return {
            **_guia_dict(guia),
            "cadernos": len(cadernos),
            "enqueued": 0,
            "message": "Guia catalogado (sem coleta).",
        }

    novos = await guia_service.enfileirar_urls(db, [req.url], requested_by=_admin.id)
    await db.commit()
    if not novos:
        return {"status": "queued", "url": req.url, "message": "Guia já estava na fila."}
    e = novos[0]
    await db.refresh(e)
    return {
        "fila_id": e.id,
        "status": e.status,
        "url": e.url,
        "message": "Guia adicionado à fila de coleta.",
    }


@router.post("/importar-lote", status_code=status.HTTP_202_ACCEPTED)
async def importar_lote(
    req: ImportarLoteReq,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Enfileira N guias de uma vez (resolve preguiçoso, coleta 1 por vez)."""
    import guia_service

    novos = await guia_service.enfileirar_urls(db, req.urls, requested_by=_admin.id)
    await db.commit()
    return {
        "enfileirados": len(novos),
        "fila": [{"id": e.id, "url": e.url, "status": e.status} for e in novos],
        "message": f"{len(novos)} guia(s) na fila de coleta.",
    }


@router.get("/fila")
async def listar_fila(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fila de coleta + countdown do cooldown. Enriquece com o nome do guia."""
    import os
    from datetime import datetime

    import guia_service

    cooldown = int(os.getenv("GUIA_COOLDOWN_SECONDS", "900"))
    data = await guia_service.listar_fila(db, agora=datetime.utcnow(), cooldown_s=cooldown)
    guia_ids = [it["guia_id"] for it in data["fila"] if it["guia_id"]]
    nomes: dict[int, str] = {}
    if guia_ids:
        rows = (
            await db.execute(select(Guia.id, Guia.nome).where(Guia.id.in_(guia_ids)))
        ).all()
        nomes = {gid: nome for gid, nome in rows}
    for it in data["fila"]:
        it["guia_nome"] = nomes.get(it["guia_id"])
    return data


@router.delete("/fila/{fila_id}")
async def remover_fila(
    fila_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove uma entrada que ainda está só 'na fila'."""
    import guia_service

    ok = await guia_service.remover_da_fila(db, fila_id)
    await db.commit()
    return {"ok": ok}


@router.post("/fila/{fila_id}/pular")
async def pular_fila_endpoint(
    fila_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Pula a entrada ativa/queued (libera a fila; dispara o cooldown)."""
    from datetime import datetime

    import guia_service

    ok = await guia_service.pular_fila(db, fila_id, agora=datetime.utcnow())
    await db.commit()
    return {"ok": ok}


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
async def buscar_guias_tc(
    termo: str,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
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


@router.get("/usuarios-pastas")
async def usuarios_pastas(
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cadernos de todos os usuários agrupados por dono e por pasta — fonte do
    Guia Builder (admin). Inclui o catálogo de guias (owner NULL) como grupo
    'Catálogo'. Nomes/e-mails via tabela `"user"` (best-effort)."""
    cadernos = (
        await db.execute(
            select(
                CadernoQuestoes.id,
                CadernoQuestoes.nome,
                CadernoQuestoes.pasta,
                CadernoQuestoes.total,
                CadernoQuestoes.tc_caderno_id,
                CadernoQuestoes.owner_uid,
            ).order_by(CadernoQuestoes.nome)
        )
    ).all()

    # Quais cadernos já estão em algum guia (informativo; reuso é permitido).
    em_guia = set(
        (
            await db.execute(
                select(GuiaCaderno.caderno_id).where(GuiaCaderno.caderno_id.isnot(None))
            )
        ).scalars().all()
    )

    # Nomes dos donos (best-effort — a tabela do Better Auth pode não existir).
    owner_uids = {c.owner_uid for c in cadernos if c.owner_uid}
    perfis: dict[str, dict[str, str]] = {}
    if owner_uids and await _table_exists(db, "public.user"):
        rows = (
            await db.execute(
                text('SELECT id, name, email FROM "user" WHERE id IN :ids').bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": list(owner_uids)},
            )
        ).mappings().all()
        perfis = {r["id"]: {"nome": r["name"] or r["email"] or r["id"], "email": r["email"] or ""} for r in rows}

    grupos: dict[str | None, dict[str, Any]] = {}
    for c in cadernos:
        uid = c.owner_uid
        g = grupos.get(uid)
        if g is None:
            if uid is None:
                g = {"uid": None, "nome": "Catálogo (guias)", "email": "", "pastas": {}}
            else:
                perfil = perfis.get(uid, {})
                g = {
                    "uid": uid,
                    "nome": perfil.get("nome", uid),
                    "email": perfil.get("email", ""),
                    "pastas": {},
                }
            grupos[uid] = g
        pasta = c.pasta or "Sem pasta"
        g["pastas"].setdefault(pasta, []).append(
            {
                "id": c.id,
                "nome": c.nome,
                "total": c.total,
                "tc_caderno_id": c.tc_caderno_id,
                "em_guia": c.id in em_guia,
            }
        )

    # Catálogo primeiro, depois usuários por nome.
    def _ordem(g: dict[str, Any]) -> tuple[int, str]:
        return (0 if g["uid"] is None else 1, (g["nome"] or "").lower())

    usuarios = []
    for g in sorted(grupos.values(), key=_ordem):
        pastas = [
            {"nome": nome, "cadernos": cads}
            for nome, cads in sorted(g["pastas"].items(), key=lambda kv: kv[0].lower())
        ]
        total = sum(len(p["cadernos"]) for p in pastas)
        usuarios.append({**{k: g[k] for k in ("uid", "nome", "email")}, "total_cadernos": total, "pastas": pastas})

    return {"usuarios": usuarios}


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def criar_guia_manual(
    req: CriarGuiaManualReq,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cria um guia montado pelo admin a partir de CadernoQuestoes existentes,
    por referência (sem duplicar questões), na ordem informada. Cada caderno
    vira um GuiaCaderno já 'materialized'."""
    nome = req.nome.strip()
    if not nome:
        raise HTTPException(422, "Nome não pode ser vazio")
    # Preserva a ordem recebida, sem duplicatas.
    ordem_ids: list[int] = []
    for cid in req.caderno_ids:
        if cid not in ordem_ids:
            ordem_ids.append(cid)
    cadernos = {
        c.id: c
        for c in (
            await db.execute(
                select(CadernoQuestoes).where(CadernoQuestoes.id.in_(ordem_ids))
            )
        ).scalars().all()
    }
    faltando = [cid for cid in ordem_ids if cid not in cadernos]
    if faltando:
        raise HTTPException(404, f"Caderno(s) inexistente(s): {faltando}")

    guia = Guia(
        nome=nome,
        banca=(req.banca or "").strip() or None,
        pro_only=req.pro_only,
        status="done",
        total_cadernos=len(ordem_ids),
    )
    db.add(guia)
    await db.flush()

    for i, cid in enumerate(ordem_ids):
        c = cadernos[cid]
        db.add(
            GuiaCaderno(
                guia_id=guia.id,
                tc_caderno_id=c.tc_caderno_id,
                nome=c.nome,
                disciplina=c.nome,
                total_questoes=c.total or 0,
                total_capitulos=0,
                ordem=i,
                caderno_id=c.id,
                status="materialized",
            )
        )
    await db.commit()
    await db.refresh(guia)
    return {**_guia_dict(guia), "cadernos": len(ordem_ids)}


def _col_caderno(c: GuiaCaderno, coletado: dict[int, int]) -> int:
    """Questões 'coletadas' de um caderno do guia. Cadernos manuais (já
    materializados, sem membership de coleta TC) contam como o total — o guia
    manual nasce 100% pronto."""
    n = coletado.get(c.tc_caderno_id, 0) if c.tc_caderno_id else 0
    if c.caderno_id and n == 0:
        return c.total_questoes
    return n


async def _pode_ver_pro(db: AsyncSession, user: CurrentUser | None) -> bool:
    """Usuário pode acessar conteúdo PRO (admin ou assinatura/voucher vigente)."""
    if not user:
        return False
    if user.is_admin:
        return True
    return await acesso_pro_ativo(db, user.id)


async def _salvos_do_usuario(
    db: AsyncSession, uid: str | None, caderno_ids: list[int]
) -> set[int]:
    """Subconjunto de `caderno_ids` que o usuário salvou (vazio se anônimo)."""
    ids = [cid for cid in caderno_ids if cid]
    if not uid or not ids:
        return set()
    rows = await db.execute(
        select(CadernoSalvo.caderno_id).where(
            CadernoSalvo.usuario_uid == uid,
            CadernoSalvo.caderno_id.in_(ids),
        )
    )
    return set(rows.scalars().all())


@router.get("")
async def listar_guias(
    user: CurrentUser | None = Depends(get_current_user_opt),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
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

    # Contagem coletada + status de job por caderno (membership + jobs)
    tc_ids_all = [gc.tc_caderno_id for gc in rows]
    coletado = await _coletado_por_caderno(db, tc_ids_all)
    jobs_all = await _jobs_por_caderno(db, tc_ids_all)
    salvos = await _salvos_do_usuario(
        db, user.id if user else None, [gc.caderno_id for gc in rows if gc.caderno_id]
    )
    pode_pro = await _pode_ver_pro(db, user)

    out = []
    for g in guias:
        cads = cadernos_by_guia.get(g.id, [])
        esperado = sum(c.total_questoes for c in cads)
        col = sum(_col_caderno(c, coletado) for c in cads)
        materializados = sum(1 for c in cads if c.caderno_id)
        cadernos_salvos = sum(1 for c in cads if c.caderno_id in salvos)
        # Coleta completa: todo caderno com job 'done' ou já coletado o esperado.
        coleta_completa = bool(cads) and all(
            c.caderno_id
            or jobs_all.get(c.tc_caderno_id, {}).get("status") == "done"
            or (c.total_questoes > 0 and coletado.get(c.tc_caderno_id, 0) >= c.total_questoes)
            for c in cads
        )
        out.append(
            {
                **_guia_dict(g),
                "cadernos_total": len(cads),
                "questoes_esperadas": esperado,
                "questoes_coletadas": col,
                "cadernos_materializados": materializados,
                "cadernos_salvos": cadernos_salvos,
                "coleta_completa": coleta_completa,
                "bloqueado": bool(g.pro_only) and not pode_pro,
                "pct": round((col / esperado) * 100, 1) if esperado else 0.0,
            }
        )
    return {"guias": out}


@router.get("/{guia_id}")
async def detalhe_guia(
    guia_id: int,
    user: CurrentUser | None = Depends(get_current_user_opt),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
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
    salvos = await _salvos_do_usuario(
        db, user.id if user else None, [c.caderno_id for c in cads if c.caderno_id]
    )

    cadernos_out = []
    for c in cads:
        col = _col_caderno(c, coletado)
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
                "salvo": c.caderno_id in salvos,
                "status": _caderno_status(c, col, job),
                "job_status": job.get("status"),
                "done_units": job.get("done_units"),
                "total_units": job.get("total_units"),
                "blocked_units": job.get("blocked_units"),
            }
        )

    esperado = sum(c.total_questoes for c in cads)
    col_total = sum(_col_caderno(c, coletado) for c in cads)
    coleta_completa = bool(cads) and all(
        c.caderno_id
        or jobs.get(c.tc_caderno_id, {}).get("status") == "done"
        or (c.total_questoes > 0 and coletado.get(c.tc_caderno_id, 0) >= c.total_questoes)
        for c in cads
    )
    return {
        **_guia_dict(guia),
        "questoes_esperadas": esperado,
        "questoes_coletadas": col_total,
        "pct": round((col_total / esperado) * 100, 1) if esperado else 0.0,
        "coleta_completa": coleta_completa,
        "bloqueado": bool(guia.pro_only) and not await _pode_ver_pro(db, user),
        "cadernos": cadernos_out,
    }


@router.patch("/{guia_id}")
async def atualizar_guia(
    guia_id: int,
    req: AtualizarGuiaReq,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Atualiza o guia (admin): renomear e/ou marcar como PRO only. Renomear
    sincroniza o campo `pasta` dos cadernos já materializados, que herdam o nome
    do guia (ver `materializar_guia`)."""
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")

    if req.pro_only is not None:
        guia.pro_only = req.pro_only

    if req.nome is not None:
        novo = req.nome.strip()
        if not novo:
            raise HTTPException(422, "Nome não pode ser vazio")
        antigo = guia.nome
        guia.nome = novo
        # Cadernos materializados deste guia usam `guia.nome` como `pasta`.
        cad_ids = (
            await db.execute(
                select(GuiaCaderno.caderno_id).where(
                    GuiaCaderno.guia_id == guia_id, GuiaCaderno.caderno_id.isnot(None)
                )
            )
        ).scalars().all()
        if cad_ids:
            await db.execute(
                CadernoQuestoes.__table__.update()
                .where(
                    CadernoQuestoes.id.in_(cad_ids),
                    CadernoQuestoes.pasta == antigo,
                )
                .values(pasta=novo)
            )
    await db.commit()
    await db.refresh(guia)
    return _guia_dict(guia)


@router.patch("/{guia_id}/cadernos/{gc_id}")
async def renomear_caderno_guia(
    guia_id: int,
    gc_id: int,
    req: RenomearGuiaCadernoReq,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Renomeia um caderno do guia no catálogo (admin). Atualiza
    `GuiaCaderno.nome` e, se já materializado, o `CadernoQuestoes.nome` do
    caderno compartilhado — cadernos de guia têm `owner_uid` NULL (catálogo),
    então o novo nome vale para todos que usam o guia."""
    gc = (
        await db.execute(
            select(GuiaCaderno).where(
                GuiaCaderno.id == gc_id, GuiaCaderno.guia_id == guia_id
            )
        )
    ).scalar_one_or_none()
    if not gc:
        raise HTTPException(404, "Caderno do guia não encontrado")
    novo = req.nome.strip()
    if not novo:
        raise HTTPException(422, "Nome não pode ser vazio")
    gc.nome = novo
    if gc.caderno_id:
        cad = (
            await db.execute(
                select(CadernoQuestoes).where(CadernoQuestoes.id == gc.caderno_id)
            )
        ).scalar_one_or_none()
        if cad:
            cad.nome = novo
    await db.commit()
    return {"id": gc.id, "nome": gc.nome, "caderno_id": gc.caderno_id}


@router.post("/{guia_id}/coletar")
async def coletar_guia(
    guia_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adiciona o guia à fila de coleta serial (re-coleta). Idempotente: não
    duplica se já estiver na fila/coletando."""
    import guia_service

    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")
    e = await guia_service.enfileirar_guia(db, guia_id, requested_by=_admin.id)
    await db.commit()
    return {
        "guia_id": guia_id,
        "fila_id": e.id if e else None,
        "enfileirado": e is not None,
        "message": "Guia na fila de coleta." if e else "Guia já estava na fila/coletando.",
    }


@router.post("/{guia_id}/materializar")
async def materializar_guia(
    guia_id: int,
    req: MaterializarReq | None = None,
    _user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cria/atualiza um CadernoQuestoes por caderno com coleta concluída.

    Por padrão só materializa cadernos completos (job `done` ou coletado ≥
    esperado). Use `forcar=true` para incluir cadernos parciais. Se
    `tc_caderno_id` for informado, materializa só esse caderno (botão "Salvar"
    por matéria). Idempotente por `CadernoQuestoes.tc_caderno_id`. Usa a ordem
    real (membership). Disponível para qualquer aluno logado.
    """
    forcar = bool(req and req.forcar)
    so_caderno = req.tc_caderno_id if req else None
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")

    cads = (
        await db.execute(select(GuiaCaderno).where(GuiaCaderno.guia_id == guia_id))
    ).scalars().all()
    if so_caderno is not None:
        cads = [c for c in cads if c.tc_caderno_id == so_caderno]
        if not cads:
            raise HTTPException(404, "Caderno não pertence a este guia")
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

    # Releitura de TODOS os cadernos (cads pode estar filtrado a um só): o guia
    # vira 'done' apenas quando todos estiverem materializados.
    todos = (
        await db.execute(
            select(GuiaCaderno.status).where(GuiaCaderno.guia_id == guia_id)
        )
    ).scalars().all()
    if todos and all(s == "materialized" for s in todos):
        guia.status = "done"
    await db.commit()
    return {
        "guia_id": guia_id,
        "materializados": materializados,
        "total": len(materializados),
        "pulados_incompletos": pulados,
    }


async def _cadernos_salvaveis(
    db: AsyncSession, guia_id: int, so_caderno: int | None
) -> list[int]:
    """IDs de `CadernoQuestoes` materializados (prontos) do guia — opcionalmente
    só de uma matéria (`so_caderno` = tc_caderno_id). 404 se a matéria não
    pertence ao guia."""
    cads = (
        await db.execute(select(GuiaCaderno).where(GuiaCaderno.guia_id == guia_id))
    ).scalars().all()
    if so_caderno is not None:
        cads = [c for c in cads if c.tc_caderno_id == so_caderno]
        if not cads:
            raise HTTPException(404, "Matéria não pertence a este guia")
    return [c.caderno_id for c in cads if c.caderno_id]


@router.post("/{guia_id}/salvar")
async def salvar_guia(
    guia_id: int,
    req: SalvarReq | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Salva matérias do guia nas "Minhas Pastas" do usuário (por usuário, sem
    duplicar questões). Sem `tc_caderno_id` salva todas as matérias prontas;
    com, salva só aquela. Idempotente. Estudar não exige salvar — o catálogo
    fica aberto; salvar só adiciona o atalho às pastas do usuário."""
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")
    if guia.pro_only and not await _pode_ver_pro(db, user):
        raise HTTPException(403, "Guia exclusivo para assinantes PRO.")
    so_caderno = req.tc_caderno_id if req else None
    alvo = await _cadernos_salvaveis(db, guia_id, so_caderno)
    if not alvo:
        raise HTTPException(409, "Nenhuma matéria pronta para salvar ainda.")

    ja = await _salvos_do_usuario(db, user.id, alvo)
    novos = 0
    for cid in alvo:
        if cid not in ja:
            db.add(CadernoSalvo(usuario_uid=user.id, caderno_id=cid))
            novos += 1
    await db.commit()
    return {
        "guia_id": guia_id,
        "novos": novos,
        "salvos_agora": len(alvo),
        "total_salvos_guia": len(ja) + novos,
    }


@router.delete("/{guia_id}/salvar")
async def remover_salvo_guia(
    guia_id: int,
    tc_caderno_id: int | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove matérias do guia das "Minhas Pastas" do usuário (uma ou todas).

    Só desfaz o vínculo do usuário — o caderno do catálogo permanece intacto."""
    guia = (await db.execute(select(Guia).where(Guia.id == guia_id))).scalar_one_or_none()
    if not guia:
        raise HTTPException(404, "Guia não encontrado")
    alvo = await _cadernos_salvaveis(db, guia_id, tc_caderno_id)
    if not alvo:
        return {"guia_id": guia_id, "removidos": 0}
    res = await db.execute(
        CadernoSalvo.__table__.delete().where(
            CadernoSalvo.usuario_uid == user.id,
            CadernoSalvo.caderno_id.in_(alvo),
        )
    )
    await db.commit()
    return {"guia_id": guia_id, "removidos": res.rowcount or 0}


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
    job_status = job.get("status")
    # Job concluído = coleta terminou, mesmo que o total venha um pouco abaixo do
    # esperado pelo TC (anuladas/duplicadas que deduplicam). Pronto p/ salvar.
    if job_status == "done" or (c.total_questoes and coletado >= c.total_questoes):
        return "collected"
    if job_status == "blocked":
        return "blocked"
    if job_status in {"running", "pending"} or coletado > 0:
        return "collecting"
    return "pending"
