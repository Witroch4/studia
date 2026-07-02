"""Avatar do perfil: upload (validação + Pillow 256x256 webp), remoção e serving."""

import io

import pytest
from PIL import Image
from sqlalchemy import select

from conftest import USER_A
from models import PerfilUsuario

pytestmark = pytest.mark.asyncio


@pytest.fixture
def minio_fake(monkeypatch):
    """Armazenamento em memória no lugar do MinIO."""
    store: dict[str, bytes] = {}

    def fake_upload(key, data, content_type):
        store[key] = data
        return f"studia-pdfs/{key}"

    def fake_download(key):
        return store[key]  # KeyError vira 404 no endpoint

    def fake_remove(key):
        store.pop(key, None)

    import perfil_router
    monkeypatch.setattr(perfil_router, "upload_bytes", fake_upload)
    monkeypatch.setattr(perfil_router, "download_bytes", fake_download)
    monkeypatch.setattr(perfil_router, "remove_object", fake_remove)
    return store


def _png(largura=800, altura=600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), "#06b6d4").save(buf, format="PNG")
    return buf.getvalue()


async def test_upload_processa_e_salva_webp_256(client, db_session, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("foto.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url.startswith("/api/q/perfil/avatar/avatars/") and url.endswith(".webp")
    key = url.removeprefix("/api/q/perfil/avatar/")
    img = Image.open(io.BytesIO(minio_fake[key]))
    assert img.format == "WEBP"
    assert img.size == (256, 256)  # crop central quadrado
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.avatar_key == key


async def test_reupload_remove_objeto_antigo(client, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r1 = await client.post("/api/q/perfil/avatar",
                           files={"file": ("a.png", _png(), "image/png")})
    key1 = r1.json()["avatar_url"].removeprefix("/api/q/perfil/avatar/")
    r2 = await client.post("/api/q/perfil/avatar",
                           files={"file": ("b.png", _png(), "image/png")})
    key2 = r2.json()["avatar_url"].removeprefix("/api/q/perfil/avatar/")
    assert key1 != key2  # chave nova = cache-busting
    assert key1 not in minio_fake and key2 in minio_fake


async def test_upload_valida_tipo_tamanho_e_conteudo(client, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("f.gif", b"GIF89a", "image/gif")})
    assert r.status_code == 415
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("f.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")})
    assert r.status_code == 413
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("f.png", b"nao-e-imagem", "image/png")})
    assert r.status_code == 422


async def test_delete_avatar(client, db_session, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("a.png", _png(), "image/png")})
    key = r.json()["avatar_url"].removeprefix("/api/q/perfil/avatar/")
    r = await client.delete("/api/q/perfil/avatar")
    assert r.status_code == 200
    assert key not in minio_fake
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.avatar_key is None


async def test_serve_avatar_publico_e_404s(client, auth_state, minio_fake):
    auth_state["user"] = USER_A
    r = await client.post("/api/q/perfil/avatar",
                          files={"file": ("a.png", _png(), "image/png")})
    url = r.json()["avatar_url"]
    auth_state["user"] = None  # endpoint de serving é público
    ok = await client.get(url)
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/webp"
    assert "immutable" in ok.headers["cache-control"]
    assert (await client.get("/api/q/perfil/avatar/avatars/../segredo.webp")).status_code == 404
    assert (await client.get(
        "/api/q/perfil/avatar/avatars/00000000-0000-0000-0000-000000000000.webp"
    )).status_code == 404
