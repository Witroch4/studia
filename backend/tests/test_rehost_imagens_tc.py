import pytest, httpx
import q_router

@pytest.mark.asyncio
async def test_rehost_reescreve_url(monkeypatch):
    subiu = {}
    monkeypatch.setattr(q_router, "upload_bytes",
                        lambda key, data, ct: subiu.update({key: (data, ct)}))

    def handler(req):
        return httpx.Response(200, content=b"\x89PNG...", headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as c:
        md = "![](https://www.tecconcursos.com.br/img/a.png) fim"
        out = await q_router._rehost_imagens_tc(
            md, ["https://www.tecconcursos.com.br/img/a.png"], c)
    assert "tecconcursos.com.br" not in out
    assert "/api/q/forum/imagem/forum/" in out
    assert len(subiu) == 1
