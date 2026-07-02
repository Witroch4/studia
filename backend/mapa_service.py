"""Serviço do Mapa da Aprovação: extração do edital (chamado pelo worker).

Separado do router para ser testável sem NATS: o worker é um wrapper fino.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gemini_service import extrair_edital_estruturado
from mapa_schemas import EditalExtraido
from minio_client import download_bytes
from models import EditalExtracao, TcConcursoArquivo


async def executar_extracao(db: AsyncSession, concurso_id: int, modelo: str) -> dict:
    """Roda a extração IA do edital de um concurso. Idempotente por status.

    pendente/erro → processando → concluido|erro. Falha NUNCA propaga (o
    worker não deve reentregar um job de IA caro): fica registrada em erro_msg.
    """
    ext = (
        await db.execute(
            select(EditalExtracao).where(EditalExtracao.concurso_id == concurso_id)
        )
    ).scalar_one_or_none()
    if ext is None:
        return {"error": f"extração do concurso {concurso_id} não registrada"}
    if ext.status in ("concluido", "processando"):
        return {"status": "skip", "motivo": ext.status}

    ext.status = "processando"
    ext.modelo_usado = modelo
    ext.erro_msg = None
    await db.commit()

    try:
        arq = (
            await db.execute(
                select(TcConcursoArquivo)
                .where(
                    TcConcursoArquivo.concurso_id == concurso_id,
                    TcConcursoArquivo.tipo == "EDITAL",
                )
                .order_by(TcConcursoArquivo.arquivo_id_externo)
            )
        ).scalars().first()
        if arq is None:
            raise RuntimeError("concurso sem arquivo de edital")

        pdf_bytes = await asyncio.to_thread(download_bytes, arq.minio_object_key)
        bruto = await asyncio.to_thread(extrair_edital_estruturado, pdf_bytes, modelo)
        dados = EditalExtraido.model_validate(bruto)  # normaliza datas/tipos
        if not dados.cargos:
            raise RuntimeError("IA não encontrou nenhum cargo no edital")
        ext.dados = dados.model_dump(mode="json")
        ext.status = "concluido"
    except Exception as exc:  # noqa: BLE001 — falha vira status visível, nunca crash
        ext.status = "erro"
        ext.erro_msg = str(exc)[:2000]
    await db.commit()
    return {"status": ext.status}
