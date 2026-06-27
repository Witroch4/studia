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


@pytest.mark.asyncio
async def test_rehost_falha_nao_levanta_e_preserva_url_original(monkeypatch):
    """Quando o download da imagem falha com qualquer Exception, a função
    não deve levantar e deve deixar a URL original no markdown inalterada.
    upload_bytes não deve ser chamado para a imagem com falha."""
    subiu = {}
    monkeypatch.setattr(q_router, "upload_bytes",
                        lambda key, data, ct: subiu.update({key: (data, ct)}))

    def handler_raise(req):
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler_raise)
    original_url = "https://www.tecconcursos.com.br/img/falha.png"
    md = f"![img]({original_url}) texto"

    async with httpx.AsyncClient(transport=transport) as c:
        out = await q_router._rehost_imagens_tc(md, [original_url], c)

    # Não deve levantar — chegamos aqui
    # URL original deve estar preservada
    assert original_url in out
    # upload_bytes não deve ter sido chamado
    assert len(subiu) == 0
