from datetime import datetime

import pytest
from sqlalchemy import update

from models import CalculadoraHistorico

pytestmark = pytest.mark.asyncio


async def test_calculator_history_post_and_list(client):
    payload = {
        "expression": "sin(30)",
        "result": "0.5",
        "caderno_id": 10,
        "questao_id": 99,
    }

    post_response = await client.post("/api/q/calculator/history", json=payload)
    list_response = await client.get("/api/q/calculator/history?caderno_id=10&questao_id=99")

    assert post_response.status_code == 200
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["expression"] == "sin(30)"
    assert items[0]["result"] == "0.5"


async def test_calculator_history_rejects_whitespace_only_payload(client):
    response = await client.post(
        "/api/q/calculator/history",
        json={
            "expression": " \n\t ",
            "result": "   ",
            "caderno_id": None,
            "questao_id": None,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "expression e result são obrigatórios"


async def test_calculator_history_delete(client):
    response = await client.post(
        "/api/q/calculator/history",
        json={"expression": "2+2", "result": "4", "caderno_id": None, "questao_id": None},
    )
    item_id = response.json()["id"]

    delete_response = await client.delete(f"/api/q/calculator/history/{item_id}")
    list_response = await client.get("/api/q/calculator/history")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}
    assert list_response.json()["items"] == []


async def test_calculator_history_delete_missing_row_returns_404(client):
    response = await client.delete("/api/q/calculator/history/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "historico não encontrado"


async def test_calculator_history_orders_newest_with_stable_tie_break(client, db_session):
    first_response = await client.post(
        "/api/q/calculator/history",
        json={
            "expression": "1+1",
            "result": "2",
            "caderno_id": None,
            "questao_id": None,
        },
    )
    second_response = await client.post(
        "/api/q/calculator/history",
        json={
            "expression": "2+2",
            "result": "4",
            "caderno_id": None,
            "questao_id": None,
        },
    )
    same_created_at = datetime(2026, 1, 1, 12, 0, 0)
    await db_session.execute(update(CalculadoraHistorico).values(created_at=same_created_at))
    await db_session.commit()

    list_response = await client.get("/api/q/calculator/history")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert [item["id"] for item in items] == [
        second_response.json()["id"],
        first_response.json()["id"],
    ]
