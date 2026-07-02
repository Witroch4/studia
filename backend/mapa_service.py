"""Serviço do Mapa da Aprovação: extração do edital (chamado pelo worker).

Separado do router para ser testável sem NATS: o worker é um wrapper fino.
"""
from __future__ import annotations

import asyncio
import re as _re

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gemini_service import extrair_edital_estruturado, mapear_materias
from mapa_schemas import EditalExtraido
from minio_client import download_bytes
from models import (
    Banca,
    CadernoQuestoes,
    EditalExtracao,
    MapaAprovacao,
    MapaItem,
    Materia,
    Prova,
    Questao,
    TcConcursoArquivo,
)


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


def _sigla_da_banca(banca_nome: str | None) -> str | None:
    """Primeiro token "sigla-like" do nome vindo da fonte (ex.: "IDECAN — Inst..." → IDECAN)."""
    if not banca_nome:
        return None
    token = _re.split(r"[—\-–(/]", banca_nome, maxsplit=1)[0].strip()
    return token or None


async def resolver_banca_id(db: AsyncSession, banca_nome: str | None) -> int | None:
    """Casa a banca do concurso com a tabela `bancas` (sigla exata > nome ilike)."""
    sigla = _sigla_da_banca(banca_nome)
    if not sigla:
        return None
    row = (
        await db.execute(
            select(Banca.id).where(
                or_(
                    func.upper(Banca.sigla) == sigla.upper(),
                    Banca.nome.ilike(f"%{sigla}%"),
                )
            ).order_by(Banca.id)
        )
    ).scalars().first()
    return row


async def questao_ids_para(
    db: AsyncSession, banca_id: int, materia_id: int, cap: int = 500
) -> list[int]:
    """Questões da banca+matéria, não-anuladas, mais recentes primeiro (ano da prova)."""
    rows = (
        await db.execute(
            select(Questao.id)
            .outerjoin(Prova, Questao.prova_id == Prova.id)
            .where(
                Questao.banca_id == banca_id,
                Questao.materia_id == materia_id,
                or_(Questao.status.is_(None), Questao.status != "ANULADA"),
                ~func.upper(func.coalesce(Questao.gabarito, "")).like("ANULADA%"),
            )
            .order_by(Prova.ano.desc().nullslast(), Questao.id.desc())
            .limit(cap)
        )
    ).scalars().all()
    return [int(q) for q in rows]


async def montar_mapa(
    db: AsyncSession,
    user_uid: str,
    concurso,  # TcConcurso
    extracao: "EditalExtracao",
    cargo: dict,
    modelo: str,
) -> tuple[MapaAprovacao, int, int]:
    """Cria MapaAprovacao + itens + cadernos automáticos. Retorna (mapa, n_cadernos, n_questoes).

    Falha da IA de match NÃO propaga: mapa nasce sem cadernos (itens sem
    materia_id/caderno_id) — o usuário ainda ganha timeline + verticalização.
    """
    mapa = MapaAprovacao(
        usuario_uid=user_uid,
        concurso_id=concurso.id,
        extracao_id=extracao.id,
        cargo_nome=cargo.get("nome") or "Cargo",
        cargo_dados=cargo,
    )
    db.add(mapa)
    await db.flush()

    programatico = cargo.get("conteudo_programatico") or []
    materias_edital = [m.get("materia", "") for m in programatico if m.get("materia")]
    materias_banco = (
        (await db.execute(select(Materia.nome))).scalars().all() if materias_edital else []
    )

    mapeamento: dict[str, str | None] = {}
    try:
        if materias_edital and materias_banco:
            mapeamento = await asyncio.to_thread(
                mapear_materias, materias_edital, list(materias_banco), modelo
            )
    except Exception:  # noqa: BLE001 — match é bônus, nunca bloqueia o mapa
        mapeamento = {}

    materia_id_por_nome: dict[str, int] = {}
    if any(mapeamento.values()):
        rows = (
            await db.execute(
                select(Materia.id, Materia.nome).where(
                    Materia.nome.in_([v for v in mapeamento.values() if v])
                )
            )
        ).all()
        materia_id_por_nome = {nome: mid for mid, nome in rows}

    banca_id = await resolver_banca_id(db, concurso.banca_nome)
    pasta = f"🗺️ {concurso.orgao_sigla or concurso.nome_completo[:60]}"

    n_cadernos = 0
    n_questoes = 0
    ordem = 0
    for bloco in programatico:
        nome_edital = bloco.get("materia") or "Matéria"
        materia_banco = mapeamento.get(nome_edital)
        materia_id = materia_id_por_nome.get(materia_banco) if materia_banco else None

        caderno_id: int | None = None
        if materia_id and banca_id:
            ids = await questao_ids_para(db, banca_id, materia_id)
            if ids:
                caderno = CadernoQuestoes(
                    owner_uid=user_uid,
                    nome=f"🗺️ {nome_edital}",
                    pasta=pasta,
                    filtros={"origem": "mapa_aprovacao", "concurso_id": concurso.id,
                             "banca_id": banca_id, "materia_id": materia_id},
                    question_ids=ids,
                    total=len(ids),
                )
                db.add(caderno)
                await db.flush()
                caderno_id = caderno.id
                n_cadernos += 1
                n_questoes += len(ids)

        assuntos = bloco.get("assuntos") or []
        if not assuntos:
            assuntos = [nome_edital]  # matéria sem itens vira 1 item genérico
        for assunto in assuntos:
            db.add(MapaItem(
                mapa_id=mapa.id, materia_nome=nome_edital,
                assunto_texto=str(assunto), ordem=ordem,
                materia_id=materia_id, caderno_id=caderno_id,
            ))
            ordem += 1

    await db.commit()
    await db.refresh(mapa)
    return mapa, n_cadernos, n_questoes
