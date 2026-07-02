"""Endpoints `/api/q/mapas/*` — Mapa da Aprovação.

Extração do edital é compartilhada por concurso (1 linha em edital_extracoes,
qualquer logado dispara — o resultado serve a todos). Criar/gerir o Mapa em si
é feature PRO (Tasks seguintes).
"""
from __future__ import annotations

from typing import Any

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
    EditalExtracao,
    MapaAprovacao,
    MapaItem,
    TcConcurso,
    TcConcursoArquivo,
)

router = APIRouter(prefix="/api/q/mapas", tags=["mapa-aprovacao"])

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
        raise HTTPException(409, f"Você já tem um Mapa para este cargo (id {existente})")

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
