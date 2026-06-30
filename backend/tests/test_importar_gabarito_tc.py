from datetime import datetime

import httpx
import pytest
from sqlalchemy import func, select

import q_router
from models import CadernoQuestoes, Questao, Resolucao

pytestmark = pytest.mark.asyncio


def _mock_scraper(monkeypatch, payload: dict):
    def handler(req):
        return httpx.Response(200, json=payload)

    real = httpx.AsyncClient

    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)

    monkeypatch.setattr(q_router.httpx, "AsyncClient", fake_client)


async def _seed_caderno(db_session):
    db_session.add(
        CadernoQuestoes(
            id=501,
            nome="Estatistica",
            owner_uid="admin-1",
            tc_caderno_id=94947327,
            question_ids=[1001, 1002, 1003],
            total=3,
        )
    )
    db_session.add_all(
        [
            Questao(
                id=1001,
                id_externo=3643888,
                tipo="MULTIPLA_ESCOLHA",
                gabarito="A",
                status="ATIVA",
                enunciado_html="<p>q1</p>",
            ),
            Questao(
                id=1002,
                id_externo=2893013,
                tipo="MULTIPLA_ESCOLHA",
                gabarito="B",
                status="ATIVA",
                enunciado_html="<p>q2</p>",
            ),
            Questao(
                id=1003,
                id_externo=3027342,
                tipo="MULTIPLA_ESCOLHA",
                gabarito="C",
                status="ATIVA",
                enunciado_html="<p>q3</p>",
            ),
        ]
    )
    await db_session.commit()


async def test_importar_gabarito_atualiza_existente_e_grava_data_sem_timezone(
    client, db_session, monkeypatch
):
    await _seed_caderno(db_session)
    db_session.add(
        Resolucao(
            questao_id=1001,
            caderno_id=501,
            usuario_uid="admin-1",
            resposta="B",
            acertou=False,
            created_at=datetime(2026, 1, 1),
        )
    )
    await db_session.commit()
    _mock_scraper(
        monkeypatch,
        {
            "total": 3,
            "itens": [
                {
                    "idQuestao": 3643888,
                    "alternativa": 1,
                    "tipoQuestao": "MULTIPLA_ESCOLHA",
                    "acertou": True,
                    "data": "24/05/2026",
                },
                {
                    "idQuestao": 2893013,
                    "alternativa": 2,
                    "tipoQuestao": "MULTIPLA_ESCOLHA",
                    "acertou": False,
                    "data": "04/06/2026",
                },
                {
                    "idQuestao": 3027342,
                    "alternativa": None,
                    "tipoQuestao": "MULTIPLA_ESCOLHA",
                    "acertou": None,
                    "data": None,
                },
            ],
        },
    )

    r = await client.post(
        "/api/q/cadernos/501/importar-gabarito",
        json={"sobrescrever": True},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["importadas"] == 1
    assert body["atualizadas"] == 1
    assert body["ja_tinha"] == 1
    assert body["resolvidas"] == 2
    assert body["acertos"] == 1
    assert body["erros"] == 1

    rows = (
        await db_session.execute(
            select(Resolucao).where(Resolucao.caderno_id == 501).order_by(Resolucao.questao_id)
        )
    ).scalars().all()
    assert len(rows) == 2
    assert rows[0].questao_id == 1001
    assert rows[0].resposta == "A"
    assert rows[0].acertou is True
    assert rows[0].created_at == datetime(2026, 5, 24)
    assert rows[0].created_at.tzinfo is None
    assert rows[1].questao_id == 1002
    assert rows[1].resposta == "B"
    assert rows[1].acertou is False
    assert rows[1].created_at == datetime(2026, 6, 4)


async def test_importar_gabarito_aceita_texto_copiado_da_tabela(client, db_session, monkeypatch):
    await _seed_caderno(db_session)

    def scraper_nao_deve_ser_chamado(req):
        raise AssertionError("scraper nao deveria ser chamado quando texto_estatistica vem no body")

    real = httpx.AsyncClient

    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(scraper_nao_deve_ser_chamado)
        return real(*a, **k)

    monkeypatch.setattr(q_router.httpx, "AsyncClient", fake_client)

    texto = """
Nº\tAlternativa marcada\tStatus\tResolvida em\tCódigo
1
A
B
C
D
E
 Acertou\t24/05/2026\t#3643888
2
A
B
C
D
E
 Errou\t04/06/2026\t#2893013
3

A

B

C

D

E
Não resolvida\t\t#3027342
4\t\tAnulada\t\t
"""

    r = await client.post(
        "/api/q/cadernos/501/importar-gabarito",
        json={"texto_estatistica": texto, "sobrescrever": True},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fonte"] == "texto"
    assert body["total_no_tec"] == 4
    assert body["importadas"] == 2
    assert body["nao_resolvidas_no_tec"] == 1
    assert body["anuladas_no_tec"] == 1
    assert body["resolvidas"] == 2
    assert body["acertos"] == 1
    assert body["erros"] == 1

    total = (
        await db_session.execute(
            select(func.count()).select_from(Resolucao).where(Resolucao.caderno_id == 501)
        )
    ).scalar_one()
    assert total == 2
