"""Endpoints do cronograma de estudo por caderno (`/api/q/cadernos/{id}/cronograma`)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, delete as sa_delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, require_user
from database import get_db
from models import (
    CadernoQuestoes, GuiaCaderno, Resolucao,
    Cronograma, CronogramaDiscursiva, CronogramaSimulado,
)
import cronograma_core as core

router = APIRouter(prefix="/api/q", tags=["cronograma"])


class CronogramaIn(BaseModel):
    data_prova: date
    data_inicio: date = Field(default_factory=date.today)
    dias_folga: list[int] = Field(default_factory=lambda: [6])
    buffer_dias: int = Field(default=21, ge=0, le=120)
    incluir_revisao: bool = True
    incluir_discursivas: bool = False
    incluir_simulados: bool = True
    discursivas_por_semana: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def _valida_datas(self):
        if self.data_prova <= self.data_inicio:
            raise ValueError("data_prova deve ser depois de data_inicio")
        return self


async def _caderno_do_usuario(db: AsyncSession, caderno_id: int, user: CurrentUser) -> CadernoQuestoes:
    """Mesma regra de acesso de q_router._caderno_acessivel (dono ou catálogo)."""
    cad = (await db.execute(
        select(CadernoQuestoes).where(CadernoQuestoes.id == caderno_id)
    )).scalar_one_or_none()
    if not cad:
        raise HTTPException(404, "caderno não encontrado")
    if cad.owner_uid == user.id:
        return cad
    eh_catalogo = (await db.execute(
        select(GuiaCaderno.id).where(GuiaCaderno.caderno_id == caderno_id).limit(1)
    )).first()
    if eh_catalogo:
        return cad
    raise HTTPException(404, "caderno não encontrado")


async def _get_cron(db: AsyncSession, caderno_id: int, uid: str) -> Optional[Cronograma]:
    return (await db.execute(
        select(Cronograma).where(
            Cronograma.caderno_id == caderno_id, Cronograma.usuario_uid == uid
        )
    )).scalar_one_or_none()


async def _resolucoes_distinct(db: AsyncSession, caderno_id: int, uid: str):
    """(resolvidas_distinct, acertos_distinct, lista (qid, acertou, data) p/ revisões)."""
    rows = (await db.execute(
        select(Resolucao.questao_id, Resolucao.acertou, Resolucao.created_at)
        .where(Resolucao.caderno_id == caderno_id, Resolucao.usuario_uid == uid)
    )).all()
    resolucoes = []
    distintas: set[int] = set()
    acertadas: set[int] = set()
    for qid, acertou, criado in rows:
        d = criado.date() if isinstance(criado, datetime) else criado
        resolucoes.append((qid, bool(acertou), d))
        distintas.add(qid)
        if acertou:
            acertadas.add(qid)
    return len(distintas), len(acertadas), resolucoes


def _cron_config_dict(c: Cronograma) -> dict[str, Any]:
    return {
        "caderno_id": c.caderno_id, "data_inicio": c.data_inicio.isoformat(),
        "data_prova": c.data_prova.isoformat(),
        "rebaseline_em": c.rebaseline_em.isoformat() if c.rebaseline_em else None,
        "dias_folga": c.dias_folga or [], "buffer_dias": c.buffer_dias,
        "incluir_revisao": c.incluir_revisao, "incluir_discursivas": c.incluir_discursivas,
        "incluir_simulados": c.incluir_simulados,
        "discursivas_por_semana": c.discursivas_por_semana,
    }


async def _montar_resposta(db: AsyncSession, cad: CadernoQuestoes, c: Cronograma) -> dict[str, Any]:
    hoje = date.today()
    inicio_efetivo = c.rebaseline_em or c.data_inicio
    plano = core.gerar_plano(inicio_efetivo, c.data_prova, cad.total or 0,
                             c.dias_folga or [], c.buffer_dias)
    resolvidas, acertos, resolucoes = await _resolucoes_distinct(db, cad.id, c.usuario_uid)
    kpis = core.calcular_kpis(plano, cad.total or 0, resolvidas, acertos, hoje)
    revisoes = core.derivar_revisoes(resolucoes, hoje) if c.incluir_revisao else []
    discs = (await db.execute(
        select(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == c.id)
        .order_by(CronogramaDiscursiva.data)
    )).scalars().all()
    sims = (await db.execute(
        select(CronogramaSimulado).where(CronogramaSimulado.cronograma_id == c.id)
        .order_by(CronogramaSimulado.data)
    )).scalars().all()
    return {
        "config": _cron_config_dict(c),
        "plano": [
            {"data": d.data.isoformat(), "weekday": d.weekday, "fase": d.fase,
             "questoes_novas": d.questoes_novas, "meta_acumulada": d.meta_acumulada,
             "hoje": d.data == hoje}
            for d in plano
        ],
        "kpis": kpis.__dict__,
        "revisar_hoje": [
            {"questao_id": i.questao_id, "revisar_em": i.revisar_em.isoformat(),
             "intervalo": i.intervalo} for i in revisoes
        ],
        "discursivas": [
            {"id": x.id, "data": x.data.isoformat(), "tema": x.tema, "tipo": x.tipo,
             "qtd": x.qtd, "status": x.status, "nota": x.nota,
             "reescrita": x.reescrita, "observacoes": x.observacoes} for x in discs
        ],
        "simulados": [
            {"id": s.id, "data": s.data.isoformat(), "tipo": s.tipo,
             "objetivas_planejadas": s.objetivas_planejadas, "meta_objetiva": s.meta_objetiva,
             "resultado_objetiva": s.resultado_objetiva,
             "discursiva_planejada": s.discursiva_planejada,
             "resultado_discursiva": s.resultado_discursiva,
             "observacoes": s.observacoes} for s in sims
        ],
    }


@router.post("/cadernos/{caderno_id}/cronograma")
async def criar_cronograma(
    caderno_id: int, payload: CronogramaIn,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    if await _get_cron(db, caderno_id, user.id):
        raise HTTPException(409, "cronograma já existe para este caderno")
    try:
        core.gerar_plano(payload.data_inicio, payload.data_prova, cad.total or 0,
                         payload.dias_folga, payload.buffer_dias)
    except ValueError as e:
        raise HTTPException(422, str(e))
    c = Cronograma(usuario_uid=user.id, caderno_id=caderno_id, **payload.model_dump())
    db.add(c)
    await db.flush()
    if payload.incluir_simulados:
        for s in core.gerar_simulados(payload.data_inicio, payload.data_prova, payload.buffer_dias):
            db.add(CronogramaSimulado(cronograma_id=c.id, **s))
    await db.commit()
    await db.refresh(c)
    return await _montar_resposta(db, cad, c)


@router.get("/cadernos/{caderno_id}/cronograma")
async def obter_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    return await _montar_resposta(db, cad, c)


@router.put("/cadernos/{caderno_id}/cronograma")
async def atualizar_cronograma(
    caderno_id: int, payload: CronogramaIn,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    for k, v in payload.model_dump().items():
        setattr(c, k, v)
    # sincroniza marcos de simulado com o flag (sem apagar resultados já registrados)
    sims_existentes = (await db.execute(
        select(func.count()).select_from(CronogramaSimulado)
        .where(CronogramaSimulado.cronograma_id == c.id)
    )).scalar_one()
    if c.incluir_simulados and sims_existentes == 0:
        for s in core.gerar_simulados(c.data_inicio, c.data_prova, c.buffer_dias):
            db.add(CronogramaSimulado(cronograma_id=c.id, **s))
    elif not c.incluir_simulados and sims_existentes > 0:
        await db.execute(
            sa_delete(CronogramaSimulado).where(CronogramaSimulado.cronograma_id == c.id)
        )
    await db.commit()
    await db.refresh(c)
    return await _montar_resposta(db, cad, c)


@router.delete("/cadernos/{caderno_id}/cronograma")
async def deletar_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    await db.execute(sa_delete(Cronograma).where(Cronograma.id == c.id))
    await db.commit()
    return {"ok": True}
