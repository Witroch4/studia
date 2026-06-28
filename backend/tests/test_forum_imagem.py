"""Imagem do fórum é servida PELO backend (stream), nunca via redirect ao MinIO.

Regressão: o endpoint redirecionava 302 → http://minio:9000/... (host interno do
overlay), inalcançável pelo navegador → comentários só-imagem apareciam em branco.
"""
import pytest
import q_router

_KEY = "forum/5203a0d9-90bc-4fed-b224-fabbbbcd23c9.png"


@pytest.mark.asyncio
async def test_streama_bytes_com_content_type_e_cache(client, monkeypatch):
    fake = b"\x89PNG\r\n\x1a\nFAKEPNG"
    monkeypatch.setattr(q_router, "download_bytes", lambda key: fake)
    r = await client.get(f"/api/q/forum/imagem/{_KEY}")
    assert r.status_code == 200  # 200, não 302 (não redireciona pro minio interno)
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == fake
    assert "max-age" in r.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_jpg_vira_image_jpeg(client, monkeypatch):
    monkeypatch.setattr(q_router, "download_bytes", lambda key: b"jpgbytes")
    r = await client.get("/api/q/forum/imagem/forum/5203a0d9-90bc-4fed-b224-fabbbbcd23c9.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")


@pytest.mark.asyncio
async def test_key_invalida_404(client):
    r = await client.get("/api/q/forum/imagem/forum/not-a-uuid.png")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_objeto_ausente_404(client, monkeypatch):
    def boom(key):
        raise Exception("NoSuchKey")
    monkeypatch.setattr(q_router, "download_bytes", boom)
    r = await client.get(f"/api/q/forum/imagem/{_KEY}")
    assert r.status_code == 404
