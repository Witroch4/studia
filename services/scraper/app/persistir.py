"""Upsert de questões/taxonomia no Postgres do studIA.

Mapeia o schema REAL da API TecConcursos (campos flat: bancaSigla,
orgaoSigla, etc) para as tabelas relacionais do studIA.

Acoplamento temporário: o scraper escreve direto na mesma instância
Postgres que o studIA. Quando este serviço migrar para
`witdev-platform-core/services/scraper/`, trocar este módulo por chamadas
HTTP a `platform-api` (`POST /api/q/upsert`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from slugify import slugify
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.observability import get_logger
from app.schemas import QuestaoApi, letra_from_numero

log = get_logger(__name__)


# ─── Bootstrap: importa models do studIA ─────────────────────────


def _ensure_backend_on_path() -> None:
    here = Path(__file__).resolve()
    candidates = [Path("/backend"), Path("/app/_backend")]
    if len(here.parents) >= 4:
        candidates.append(here.parents[3] / "backend")
    for c in candidates:
        if c.exists() and str(c) not in sys.path:
            sys.path.insert(0, str(c))
            return


_ensure_backend_on_path()

from models import (  # noqa: E402
    Alternativa,
    Assunto,
    Banca,
    Cargo,
    Materia,
    Orgao,
    Questao,
    questao_assunto,
)

# ─── Sessão dedicada ─────────────────────────────────────────────


_engine = None
_Session: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _Session
    if _Session is None:
        _engine = create_async_engine(get_settings().database_url, echo=False)
        _Session = async_sessionmaker(_engine, expire_on_commit=False)
    return _Session


# ─── Helpers ─────────────────────────────────────────────────────


def _html_to_md(html: str | None) -> str | None:
    if not html:
        return None
    try:
        from markdownify import markdownify
        return markdownify(html, heading_style="ATX").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("md.fallback", err=str(e))
        return html


async def _upsert_taxonomia(session: AsyncSession, q: QuestaoApi) -> dict[str, int | None]:
    ids: dict[str, Any] = {
        "banca_id": None,
        "orgao_id": None,
        "cargo_id": None,
        "materia_id": None,
        "assunto_id": None,
    }

    # ─── Banca ───
    if q.bancaSigla:
        slug = slugify(q.bancaUrl or q.bancaSigla) or "banca"
        stmt = (
            pg_insert(Banca)
            .values(nome=q.bancaSigla, slug=slug, sigla=q.bancaSigla)
            .on_conflict_do_update(
                index_elements=["nome"],
                set_={"sigla": q.bancaSigla, "slug": slug},
            )
            .returning(Banca.id)
        )
        ids["banca_id"] = (await session.execute(stmt)).scalar_one()

    # ─── Órgão ───
    if q.orgaoSigla or q.orgaoNome:
        nome = q.orgaoNome or q.orgaoSigla
        slug = slugify(q.orgaoUrl or nome) or "orgao"
        stmt = (
            pg_insert(Orgao)
            .values(nome=nome, slug=slug, sigla=q.orgaoSigla)
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={"nome": nome, "sigla": q.orgaoSigla},
            )
            .returning(Orgao.id)
        )
        ids["orgao_id"] = (await session.execute(stmt)).scalar_one()

    # ─── Cargo ───
    if q.cargoSigla:
        # cargos não têm id_externo confiável; chave composta nome+ano
        from sqlalchemy import select
        existing = (
            await session.execute(
                select(Cargo.id).where(
                    Cargo.nome == q.cargoSigla,
                    Cargo.ano == q.concursoAno,
                    Cargo.orgao_id == ids["orgao_id"],
                )
            )
        ).scalar_one_or_none()
        if existing:
            ids["cargo_id"] = existing
        else:
            cargo = Cargo(
                orgao_id=ids["orgao_id"],
                nome=q.cargoSigla,
                ano=q.concursoAno,
                area=q.concursoArea,
            )
            session.add(cargo)
            await session.flush()
            ids["cargo_id"] = cargo.id

    # ─── Matéria ───
    if q.nomeMateria:
        stmt = (
            pg_insert(Materia)
            .values(id_externo=q.idMateria, nome=q.nomeMateria)
            .on_conflict_do_update(
                index_elements=["nome"],
                set_={"id_externo": q.idMateria},
            )
            .returning(Materia.id)
        )
        ids["materia_id"] = (await session.execute(stmt)).scalar_one()

    # ─── Assunto ───
    if q.nomeAssunto and ids["materia_id"]:
        stmt = (
            pg_insert(Assunto)
            .values(
                id_externo=q.idAssunto,
                materia_id=ids["materia_id"],
                nome=q.nomeAssunto,
            )
            .on_conflict_do_update(
                index_elements=["materia_id", "nome"],
                set_={"id_externo": q.idAssunto},
            )
            .returning(Assunto.id)
        )
        ids["assunto_id"] = (await session.execute(stmt)).scalar_one()

    return ids


async def upsert_questao(q: QuestaoApi, raw: dict[str, Any] | None = None) -> int:
    """Idempotente: insere/atualiza questão + alternativas + vínculo assunto."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        async with session.begin():
            ids = await _upsert_taxonomia(session, q)

            # Prefere o campo `gabarito` direto (letra A-E ou "Certo"/"Errado")
            # quando disponível (vem em /ajaxCarregarQuestoesImpressao). Fallback
            # pra derivar da posição numérica (vem em /api/cadernos/{c}/questoes/{N}).
            gabarito = q.gabarito or letra_from_numero(q.numeroAlternativaCorreta)
            status_txt = "ANULADA" if q.anulada else ("DESATUALIZADA" if q.desatualizada else "ATIVA")

            stmt = (
                pg_insert(Questao)
                .values(
                    id_externo=q.idQuestao,
                    banca_id=ids["banca_id"],
                    orgao_id=ids["orgao_id"],
                    cargo_id=ids["cargo_id"],
                    materia_id=ids["materia_id"],
                    tipo=q.tipoQuestao,
                    enunciado_md=_html_to_md(q.enunciado),
                    enunciado_html=q.enunciado,
                    gabarito=gabarito,
                    status=status_txt,
                    raw_json=raw,
                )
                .on_conflict_do_update(
                    index_elements=["id_externo"],
                    set_={
                        "banca_id": ids["banca_id"],
                        "orgao_id": ids["orgao_id"],
                        "cargo_id": ids["cargo_id"],
                        "materia_id": ids["materia_id"],
                        "tipo": q.tipoQuestao,
                        "enunciado_md": _html_to_md(q.enunciado),
                        "enunciado_html": q.enunciado,
                        "gabarito": gabarito,
                        "status": status_txt,
                        "raw_json": raw,
                    },
                )
                .returning(Questao.id)
            )
            questao_pk = (await session.execute(stmt)).scalar_one()

            # Substitui alternativas
            await session.execute(
                Alternativa.__table__.delete().where(
                    Alternativa.questao_id == questao_pk
                )
            )
            for idx, alt_html in enumerate(q.alternativas):
                letra = chr(ord("A") + idx)
                correta = (q.numeroAlternativaCorreta == idx + 1) if q.numeroAlternativaCorreta else None
                await session.execute(
                    pg_insert(Alternativa).values(
                        questao_id=questao_pk,
                        letra=letra,
                        texto_md=_html_to_md(alt_html),
                        texto_html=alt_html,
                        correta=correta,
                        ordem=idx + 1,
                    )
                )

            # Vínculo questão↔assunto
            await session.execute(
                questao_assunto.delete().where(
                    questao_assunto.c.questao_id == questao_pk
                )
            )
            if ids["assunto_id"]:
                await session.execute(
                    pg_insert(questao_assunto)
                    .values(questao_id=questao_pk, assunto_id=ids["assunto_id"])
                    .on_conflict_do_nothing()
                )

    log.info(
        "questao.upsert",
        id_externo=q.idQuestao,
        pk=questao_pk,
        gabarito=gabarito,
        banca=q.bancaSigla,
    )
    return questao_pk
