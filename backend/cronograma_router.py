"""Endpoints do cronograma de estudo por caderno (`/api/q/cadernos/{id}/cronograma`)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, delete as sa_delete, func
from sqlalchemy.ext.asyncio import AsyncSession

import io as io_module

from fastapi.responses import StreamingResponse

from auth import CurrentUser, require_user
from database import get_db
from models import (
    CadernoQuestoes, GuiaCaderno, Resolucao,
    Cronograma, CronogramaDiscursiva, CronogramaSimulado,
)
import cronograma_core as core
import logging
from gemini_service import gerar_temas_discursivas
from cronograma_xlsx import montar_workbook

_log = logging.getLogger("cronograma")

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



async def _materias_do_caderno(db: AsyncSession, cad: CadernoQuestoes) -> list[str]:
    from models import Questao, Materia
    ids = cad.question_ids or []
    if not ids:
        return []
    rows = (await db.execute(
        select(Materia.nome, func.count())
        .join(Questao, Questao.materia_id == Materia.id)
        .where(Questao.id.in_(ids))
        .group_by(Materia.nome).order_by(func.count().desc())
    )).all()
    return [nome for nome, _ in rows]


async def _popular_discursivas(db: AsyncSession, cad: CadernoQuestoes, c: Cronograma) -> None:
    """Gera temas via IA e agenda em terças/quintas. Falha de IA não propaga."""
    from datetime import timedelta
    try:
        materias = await _materias_do_caderno(db, cad)
        temas = gerar_temas_discursivas(materias, n=18)
    except Exception as e:  # noqa: BLE001
        _log.warning("IA de discursivas indisponível: %s", e)
        return
    fim_1volta = c.data_prova - timedelta(days=c.buffer_dias)
    agenda = core.agendar_discursivas(temas, c.data_inicio, fim_1volta, c.discursivas_por_semana)
    for data_, tema in agenda:
        db.add(CronogramaDiscursiva(cronograma_id=c.id, data=data_, tema=tema,
                                    tipo="Treino 20 linhas", qtd=1, status="Pendente",
                                    reescrita=False))

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
    if payload.incluir_discursivas:
        await _popular_discursivas(db, cad, c)
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


@router.post("/cadernos/{caderno_id}/cronograma/recalcular")
async def recalcular_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Re-ancora o plano em hoje: a curva de meta passa a partir de hoje com o
    restante das questões. Mantém datas de prova/folgas/buffer."""
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    c.rebaseline_em = date.today()
    await db.commit()
    await db.refresh(c)
    return await _montar_resposta(db, cad, c)


class SimuladoPatch(BaseModel):
    resultado_objetiva: Optional[int] = None
    resultado_discursiva: Optional[float] = None
    observacoes: Optional[str] = None


@router.patch("/cadernos/{caderno_id}/cronograma/simulados/{sim_id}")
async def patch_simulado(
    caderno_id: int, sim_id: int, payload: SimuladoPatch,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    sim = (await db.execute(
        select(CronogramaSimulado).where(
            CronogramaSimulado.id == sim_id, CronogramaSimulado.cronograma_id == c.id
        )
    )).scalar_one_or_none()
    if not sim:
        raise HTTPException(404, "simulado não encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sim, k, v)
    await db.commit()
    return {"ok": True}




class DiscursivaPatch(BaseModel):
    status: Optional[str] = None
    nota: Optional[float] = None
    reescrita: Optional[bool] = None
    observacoes: Optional[str] = None


@router.patch("/cadernos/{caderno_id}/cronograma/discursivas/{disc_id}")
async def patch_discursiva(
    caderno_id: int, disc_id: int, payload: DiscursivaPatch,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    d = (await db.execute(
        select(CronogramaDiscursiva).where(
            CronogramaDiscursiva.id == disc_id, CronogramaDiscursiva.cronograma_id == c.id
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "discursiva não encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    await db.commit()
    return {"ok": True}


@router.post("/cadernos/{caderno_id}/cronograma/discursivas/regenerar")
async def regenerar_discursivas(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    await db.execute(
        sa_delete(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == c.id)
    )
    await _popular_discursivas(db, cad, c)
    await db.commit()
    return await _montar_resposta(db, cad, c)

@router.get("/cadernos/{caderno_id}/cronograma/export.xlsx")
async def exportar_cronograma(
    caderno_id: int,
    user: CurrentUser = Depends(require_user), db: AsyncSession = Depends(get_db),
):
    cad = await _caderno_do_usuario(db, caderno_id, user)
    c = await _get_cron(db, caderno_id, user.id)
    if not c:
        raise HTTPException(404, "sem cronograma")
    inicio_efetivo = c.rebaseline_em or c.data_inicio
    plano = core.gerar_plano(inicio_efetivo, c.data_prova, cad.total or 0,
                             c.dias_folga or [], c.buffer_dias)
    discs = (await db.execute(
        select(CronogramaDiscursiva).where(CronogramaDiscursiva.cronograma_id == c.id)
        .order_by(CronogramaDiscursiva.data)
    )).scalars().all()
    sims = (await db.execute(
        select(CronogramaSimulado).where(CronogramaSimulado.cronograma_id == c.id)
        .order_by(CronogramaSimulado.data)
    )).scalars().all()
    blob = montar_workbook({
        "nome_caderno": cad.nome, "total": cad.total or 0,
        "data_inicio": c.data_inicio, "data_prova": c.data_prova, "plano": plano,
        "discursivas": [{"data": x.data, "tema": x.tema, "tipo": x.tipo, "qtd": x.qtd,
                         "status": x.status, "nota": x.nota, "observacoes": x.observacoes}
                        for x in discs],
        "simulados": [{"data": s.data, "tipo": s.tipo,
                       "objetivas_planejadas": s.objetivas_planejadas,
                       "meta_objetiva": s.meta_objetiva,
                       "resultado_objetiva": s.resultado_objetiva,
                       "discursiva_planejada": s.discursiva_planejada,
                       "resultado_discursiva": s.resultado_discursiva} for s in sims],
    })
    nome = f"cronograma_caderno_{caderno_id}.xlsx"
    return StreamingResponse(
        io_module.BytesIO(blob),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


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
