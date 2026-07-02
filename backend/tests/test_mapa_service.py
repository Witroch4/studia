"""executar_extracao: transições de status, PDF via MinIO, IA mockada."""
import pytest
from sqlalchemy import select

import mapa_service
from models import EditalExtracao, TcConcurso, TcConcursoArquivo

pytestmark = pytest.mark.asyncio


async def _seed_concurso(db, com_edital=True) -> TcConcurso:
    c = TcConcurso(concurso_id_externo=111, nome_completo="Concurso X",
                   url_concurso="x", banca_nome="IDECAN — Instituto", ano=2026)
    db.add(c)
    await db.flush()
    if com_edital:
        db.add(TcConcursoArquivo(concurso_id=c.id, tipo="EDITAL",
                                 arquivo_id_externo=1, uuid="u1",
                                 nome_arquivo="edital.pdf",
                                 minio_object_key="concursos/u1.pdf"))
    db.add(EditalExtracao(concurso_id=c.id, status="pendente"))
    await db.commit()
    return c


async def test_extracao_feliz(db_session, monkeypatch):
    c = await _seed_concurso(db_session)
    monkeypatch.setattr(mapa_service, "download_bytes", lambda k: b"%PDF")
    monkeypatch.setattr(
        mapa_service, "extrair_edital_estruturado",
        lambda pdf, modelo: {"cargos": [{"nome": "Engenheiro Civil"}]},
    )
    await mapa_service.executar_extracao(db_session, c.id, "gemini-3-flash-preview")
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "concluido"
    assert ext.dados["cargos"][0]["nome"] == "Engenheiro Civil"
    assert ext.modelo_usado == "gemini-3-flash-preview"


async def test_extracao_ia_falha_marca_erro(db_session, monkeypatch):
    c = await _seed_concurso(db_session)
    monkeypatch.setattr(mapa_service, "download_bytes", lambda k: b"%PDF")

    def _boom(pdf, modelo):
        raise RuntimeError("proxy indisponível")

    monkeypatch.setattr(mapa_service, "extrair_edital_estruturado", _boom)
    await mapa_service.executar_extracao(db_session, c.id, "m")
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "erro"
    assert "proxy indisponível" in ext.erro_msg


async def test_extracao_sem_edital_marca_erro(db_session):
    c = await _seed_concurso(db_session, com_edital=False)
    await mapa_service.executar_extracao(db_session, c.id, "m")
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    assert ext.status == "erro"


async def test_extracao_concluida_e_skip(db_session, monkeypatch):
    c = await _seed_concurso(db_session)
    ext = (await db_session.execute(
        select(EditalExtracao).where(EditalExtracao.concurso_id == c.id)
    )).scalar_one()
    ext.status = "concluido"
    await db_session.commit()
    out = await mapa_service.executar_extracao(db_session, c.id, "m")
    assert out["status"] == "skip"
