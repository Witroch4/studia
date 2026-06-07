import pytest
from sqlalchemy import func, select

from models import CadernoQuestoes, Questao, QuestaoAnotacao

pytestmark = pytest.mark.asyncio


async def seed_question(db_session):
    db_session.add(CadernoQuestoes(id=10, nome="Caderno", question_ids=[99], total=1))
    db_session.add(
        Questao(
            id=99,
            id_externo=3966994,
            tipo="MULTIPLA_ESCOLHA",
            enunciado_html="<p>Enunciado</p>",
            gabarito="A",
            status="ATIVA",
        )
    )
    await db_session.commit()


async def test_get_missing_annotation_returns_empty_state(client, db_session):
    await seed_question(db_session)

    response = await client.get("/api/q/cadernos/10/questoes/99/annotations")

    assert response.status_code == 200
    data = response.json()
    assert data["caderno_id"] == 10
    assert data["questao_id"] == 99
    assert data["canvas_json"] == {"version": 1, "cardSize": None, "strokes": []}
    assert data["strikes_json"] == {"version": 1, "targets": []}


async def test_get_annotation_rejects_question_outside_caderno(client, db_session):
    await seed_question(db_session)
    db_session.add(
        Questao(
            id=100,
            id_externo=3966995,
            tipo="MULTIPLA_ESCOLHA",
            enunciado_html="<p>Outro enunciado</p>",
            gabarito="B",
            status="ATIVA",
        )
    )
    await db_session.commit()

    response = await client.get("/api/q/cadernos/10/questoes/100/annotations")

    assert response.status_code == 404
    assert response.json()["detail"] == "questao não pertence ao caderno"


async def test_put_annotation_persists_canvas_and_strikes(client, db_session):
    await seed_question(db_session)
    payload = {
        "canvas_json": {
            "version": 1,
            "cardSize": {"width": 900, "height": 600},
            "strokes": [
                {
                    "id": "stroke_1",
                    "tool": "pen",
                    "color": "#22c55e",
                    "width": 4,
                    "points": [{"x": 0.2, "y": 0.3, "p": 0.6}],
                }
            ],
        },
        "strikes_json": {
            "version": 1,
            "targets": [{"type": "alternative", "id": 321}],
        },
    }

    put_response = await client.put(
        "/api/q/cadernos/10/questoes/99/annotations",
        json=payload,
    )
    get_response = await client.get("/api/q/cadernos/10/questoes/99/annotations")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["canvas_json"] == payload["canvas_json"]
    assert get_response.json()["strikes_json"] == payload["strikes_json"]


async def test_put_annotation_updates_existing_row(client, db_session):
    await seed_question(db_session)

    await client.put(
        "/api/q/cadernos/10/questoes/99/annotations",
        json={
            "canvas_json": {"version": 1, "cardSize": None, "strokes": []},
            "strikes_json": {"version": 1, "targets": []},
        },
    )
    response = await client.put(
        "/api/q/cadernos/10/questoes/99/annotations",
        json={
            "canvas_json": {
                "version": 1,
                "cardSize": None,
                "strokes": [{"id": "stroke_2"}],
            },
            "strikes_json": {
                "version": 1,
                "targets": [{"type": "alternative", "id": 8}],
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["canvas_json"]["strokes"] == [{"id": "stroke_2"}]
    assert response.json()["strikes_json"]["targets"] == [
        {"type": "alternative", "id": 8}
    ]


async def test_put_annotation_keeps_single_row_for_scope(client, db_session):
    await seed_question(db_session)

    for stroke_id in ("stroke_1", "stroke_2"):
        response = await client.put(
            "/api/q/cadernos/10/questoes/99/annotations",
            json={
                "canvas_json": {
                    "version": 1,
                    "cardSize": None,
                    "strokes": [{"id": stroke_id}],
                },
                "strikes_json": {"version": 1, "targets": []},
            },
        )
        assert response.status_code == 200

    total = (
        await db_session.execute(
            select(func.count()).where(
                QuestaoAnotacao.usuario_id.is_(None),
                QuestaoAnotacao.caderno_id == 10,
                QuestaoAnotacao.questao_id == 99,
            )
        )
    ).scalar_one()

    assert total == 1
