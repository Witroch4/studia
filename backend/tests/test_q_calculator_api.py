import pytest

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
