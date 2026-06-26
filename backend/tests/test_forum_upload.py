import pytest

import q_router

pytestmark = pytest.mark.asyncio

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f8f0000000049454e44ae426082"
)


async def test_upload_aceita_png(client, monkeypatch):
    monkeypatch.setattr(q_router, "upload_bytes", lambda *a, **k: "studia-pdfs/forum/x.png")
    r = await client.post(
        "/api/q/forum/upload",
        files={"file": ("foto.png", PNG_1x1, "image/png")},
    )
    assert r.status_code == 200
    assert "/api/q/forum/imagem/forum/" in r.json()["url"]


async def test_upload_rejeita_tipo_invalido(client):
    r = await client.post(
        "/api/q/forum/upload",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 400


async def test_upload_rejeita_arquivo_grande(client):
    grande = b"\x00" * (5 * 1024 * 1024 + 1)
    r = await client.post(
        "/api/q/forum/upload",
        files={"file": ("big.png", grande, "image/png")},
    )
    assert r.status_code == 400
