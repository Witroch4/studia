"""Endpoints `/api/q/mapas/*` — Mapa da Aprovação.

Extração do edital é compartilhada por concurso (1 linha em edital_extracoes,
qualquer logado dispara — o resultado serve a todos). Criar/gerir o Mapa em si
é feature PRO (Tasks seguintes).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import mapa_service
from auth import CurrentUser, require_admin, require_user
from database import get_db
from entitlements import acesso_pro_ativo
from llm_registry import SETTING_DEFAULTS, SETTING_MAPA, get_setting
from models import (
    CadernoQuestoes,
    EditalExtracao,
    MapaAprovacao,
    MapaItem,
    TcConcurso,
    TcConcursoArquivo,
)

router = APIRouter(prefix="/api/q/mapas", tags=["mapa-aprovacao"])

STATUS_ITEM = {"nao_visto", "estudando", "dominado"}

# `worker.py` importa taskiq_nats/nats (broker NATS) no topo do módulo — pesado
# e ausente em alguns ambientes (venv de teste local). Para não travar o import
# de `mapa_router` (e portanto de `main.app`, usado por `tests/conftest.py`),
# a task é resolvida em tempo de chamada: `_kiq_extrair` lê este nome global a
# cada requisição e, se ainda for None (produção — nada aqui o preenche), faz
# `from worker import ...` ali dentro. Esse import roda a CADA chamada; o que é
# cacheado é o módulo em `sys.modules` após a primeira vez, então o custo
# repetido é só um lookup de dicionário + atributo. Testes monkeypatcham este
# nome diretamente (`monkeypatch.setattr(mapa_router, "extrair_edital_task",
# FakeTask())`), então o import do worker real nunca roda neles.
extrair_edital_task: Any = None


class ExtrairReq(BaseModel):
    concurso_id: int


class CriarMapaReq(BaseModel):
    concurso_id: int
    cargo_nome: str


async def _concurso_ou_404(db: AsyncSession, concurso_id: int) -> TcConcurso:
    c = (
        await db.execute(select(TcConcurso).where(TcConcurso.id == concurso_id))
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Concurso não encontrado")
    return c


async def _kiq_extrair(concurso_id: int, modelo: str) -> None:
    """Enfileira a task de extração — import lazy do worker (ver nota acima)."""
    task = extrair_edital_task
    if task is None:
        from worker import extrair_edital_task as task  # import local, só em prod
    await task.kiq(concurso_id, modelo)


@router.post("/extrair", status_code=status.HTTP_202_ACCEPTED)
async def extrair_edital(
    req: ExtrairReq,
    _user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dispara (ou reaproveita) a extração IA do edital. Idempotente.

    concluido/processando → devolve o status sem reenfileirar; pendente/erro
    → (re)enfileira no worker.
    """
    concurso = await _concurso_ou_404(db, req.concurso_id)
    tem_edital = (
        await db.execute(
            select(TcConcursoArquivo.id).where(
                TcConcursoArquivo.concurso_id == concurso.id,
                TcConcursoArquivo.tipo == "EDITAL",
            )
        )
    ).first()
    if tem_edital is None:
        raise HTTPException(409, "Este concurso não tem edital coletado")

    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso.id)
        )
    ).scalar_one_or_none()
    if ext is not None and ext.status in ("concluido", "processando"):
        return {"status": ext.status}

    if ext is None:
        ext = EditalExtracao(concurso_id=concurso.id, status="pendente")
        db.add(ext)
    else:  # erro → nova tentativa
        ext.status = "pendente"
        ext.erro_msg = None
    await db.commit()

    modelo = await get_setting(db, SETTING_MAPA, SETTING_DEFAULTS[SETTING_MAPA])
    await _kiq_extrair(concurso.id, modelo)
    return {"status": "pendente"}


@router.get("/extracao/{concurso_id}")
async def status_extracao(
    concurso_id: int,
    _user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Polling do wizard: status + dados quando concluído."""
    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso_id)
        )
    ).scalar_one_or_none()
    if ext is None:
        return {"status": "nao_iniciada", "erro_msg": None}
    out: dict[str, Any] = {"status": ext.status, "erro_msg": ext.erro_msg}
    if ext.status == "concluido":
        out["dados"] = ext.dados
    return out


@router.post("/extracao/{concurso_id}/reextrair", status_code=status.HTTP_202_ACCEPTED)
async def reextrair_edital(
    concurso_id: int,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Força nova extração (edital retificado / prompt novo). Mapas existentes
    mantêm o snapshot em cargo_dados — não são reescritos."""
    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso_id)
        )
    ).scalar_one_or_none()
    if ext is None:
        raise HTTPException(404, "Extração não encontrada")
    ext.status = "pendente"
    ext.erro_msg = None
    ext.prompt_versao = (ext.prompt_versao or 1) + 1
    await db.commit()
    modelo = await get_setting(db, SETTING_MAPA, SETTING_DEFAULTS[SETTING_MAPA])
    await _kiq_extrair(concurso_id, modelo)
    return {"status": "pendente", "prompt_versao": ext.prompt_versao}


@router.post("")
async def criar_mapa(
    req: CriarMapaReq,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cria o Mapa da Aprovação (PRO): itens verticalizados + cadernos automáticos."""
    if not (user.is_admin or await acesso_pro_ativo(db, user.id)):
        raise HTTPException(403, "O Mapa da Aprovação é um recurso PRO")

    concurso = await _concurso_ou_404(db, req.concurso_id)
    ext = (
        await db.execute(
            select(EditalExtracao).where(
                EditalExtracao.concurso_id == concurso.id,
                EditalExtracao.status == "concluido",
            )
        )
    ).scalar_one_or_none()
    if ext is None or not ext.dados:
        raise HTTPException(409, "Edital ainda não extraído")

    cargo = next(
        (c for c in (ext.dados.get("cargos") or []) if c.get("nome") == req.cargo_nome),
        None,
    )
    if cargo is None:
        raise HTTPException(404, "Cargo não encontrado no edital")

    existente = (
        await db.execute(
            select(MapaAprovacao.id).where(
                MapaAprovacao.usuario_uid == user.id,
                MapaAprovacao.concurso_id == concurso.id,
                MapaAprovacao.cargo_nome == req.cargo_nome,
            )
        )
    ).scalar_one_or_none()
    if existente:
        # detail estruturado: o wizard do frontend usa o id p/ redirecionar ao Mapa.
        raise HTTPException(
            409, {"msg": "Você já tem um Mapa para este cargo", "id": existente}
        )

    modelo = await get_setting(db, SETTING_MAPA, SETTING_DEFAULTS[SETTING_MAPA])
    mapa, n_cadernos, n_questoes = await mapa_service.montar_mapa(
        db, user.id, concurso, ext, cargo, modelo
    )
    return {
        "id": mapa.id,
        "redirect": f"/q/mapa/{mapa.id}",
        "cadernos_criados": n_cadernos,
        "total_questoes": n_questoes,
    }


def _data_prova_do_mapa(dados: Optional[dict], concurso: TcConcurso) -> Optional[str]:
    """data_prova ISO: extração > evento tipo=prova > data_aplicacao do concurso."""
    if dados:
        dp = (dados.get("concurso") or {}).get("data_prova")
        if dp:
            return dp
        for ev in dados.get("eventos") or []:
            if ev.get("tipo") == "prova" and ev.get("data_inicio"):
                return ev["data_inicio"]
    if concurso.data_aplicacao:
        return concurso.data_aplicacao.date().isoformat()
    return None


async def _mapa_do_usuario(db: AsyncSession, mapa_id: int, user_uid: str) -> MapaAprovacao:
    mapa = (
        await db.execute(
            select(MapaAprovacao).where(
                MapaAprovacao.id == mapa_id, MapaAprovacao.usuario_uid == user_uid
            )
        )
    ).scalar_one_or_none()
    if mapa is None:
        raise HTTPException(404, "Mapa não encontrado")
    return mapa


@router.get("")
async def listar_mapas(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    mapas = (
        await db.execute(
            select(MapaAprovacao)
            .where(MapaAprovacao.usuario_uid == user.id)
            .order_by(MapaAprovacao.criado_em.desc())
        )
    ).scalars().all()
    out = []
    for m in mapas:
        concurso = (
            await db.execute(select(TcConcurso).where(TcConcurso.id == m.concurso_id))
        ).scalar_one()
        ext = (
            await db.execute(
                select(EditalExtracao).where(EditalExtracao.id == m.extracao_id)
            )
        ).scalar_one_or_none()
        itens = m.itens  # lazy="selectin"
        out.append({
            "id": m.id,
            "concurso_id": m.concurso_id,
            "concurso_nome": concurso.nome_completo,
            "orgao_sigla": concurso.orgao_sigla,
            "banca_nome": concurso.banca_nome,
            "cargo_nome": m.cargo_nome,
            "data_prova": _data_prova_do_mapa(ext.dados if ext else None, concurso),
            "total_itens": len(itens),
            "itens_dominados": sum(1 for i in itens if i.status == "dominado"),
            "caderno_ids": sorted({i.caderno_id for i in itens if i.caderno_id}),
            "criado_em": m.criado_em.isoformat() if m.criado_em else None,
        })
    return {"mapas": out}


@router.get("/{mapa_id}")
async def detalhar_mapa(
    mapa_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    mapa = await _mapa_do_usuario(db, mapa_id, user.id)
    concurso = (
        await db.execute(select(TcConcurso).where(TcConcurso.id == mapa.concurso_id))
    ).scalar_one()
    ext = (
        await db.execute(select(EditalExtracao).where(EditalExtracao.id == mapa.extracao_id))
    ).scalar_one_or_none()

    # Verticalização agrupada por matéria, na ordem dos itens
    grupos: dict[str, dict[str, Any]] = {}
    for i in mapa.itens:
        g = grupos.setdefault(i.materia_nome, {
            "materia_nome": i.materia_nome, "materia_id": i.materia_id,
            "caderno_id": i.caderno_id, "itens": [],
        })
        g["itens"].append({"id": i.id, "assunto_texto": i.assunto_texto, "status": i.status})

    cadernos_ids = sorted({i.caderno_id for i in mapa.itens if i.caderno_id})
    cadernos = []
    if cadernos_ids:
        rows = (
            await db.execute(
                select(CadernoQuestoes).where(CadernoQuestoes.id.in_(cadernos_ids))
            )
        ).scalars().all()
        cadernos = [{"id": c.id, "nome": c.nome, "total": c.total} for c in rows]

    return {
        "id": mapa.id,
        "concurso_id": mapa.concurso_id,
        "concurso_nome": concurso.nome_completo,
        "orgao_sigla": concurso.orgao_sigla,
        "banca_nome": concurso.banca_nome,
        "cargo_nome": mapa.cargo_nome,
        "cargo_dados": mapa.cargo_dados,
        "data_prova": _data_prova_do_mapa(ext.dados if ext else None, concurso),
        "eventos": (ext.dados.get("eventos") if ext and ext.dados else []) or [],
        "verticalizacao": list(grupos.values()),
        "cadernos": cadernos,
    }


class ItemPatch(BaseModel):
    status: str


@router.patch("/{mapa_id}/itens/{item_id}")
async def atualizar_item(
    mapa_id: int,
    item_id: int,
    req: ItemPatch,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if req.status not in STATUS_ITEM:
        raise HTTPException(400, f"status deve ser um de {sorted(STATUS_ITEM)}")
    await _mapa_do_usuario(db, mapa_id, user.id)
    item = (
        await db.execute(
            select(MapaItem).where(MapaItem.id == item_id, MapaItem.mapa_id == mapa_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    item.status = req.status
    await db.commit()
    return {"ok": True, "id": item.id, "status": item.status}


@router.delete("/{mapa_id}")
async def excluir_mapa(
    mapa_id: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove o mapa (cascade nos itens). Cadernos criados são do usuário — ficam."""
    mapa = await _mapa_do_usuario(db, mapa_id, user.id)
    await db.delete(mapa)
    await db.commit()
    return {"ok": True}
