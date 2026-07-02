"""POST /api/q/calculadora/reconhecer: gate PRO, limites e mapeamento de erros."""

import base64

import pytest

import vision_calc
from tests.conftest import USER_A
from vision_calc import IaIndisponivel, ReconhecimentoIlegivel, _clean_expression

PNG_B64 = base64.b64encode(b"fake-png-bytes").decode()


@pytest.fixture
def reconhecedor(monkeypatch):
    """Substitui a chamada de IA; devolve holder p/ configurar o resultado."""
    holder = {"result": "2+2", "raises": None, "alias": None}

    async def fake(image_b64, alias):
        holder["alias"] = alias
        if holder["raises"]:
            raise holder["raises"]
        return holder["result"]

    monkeypatch.setattr(vision_calc, "reconhecer_expressao", fake)
    return holder


@pytest.mark.asyncio
async def test_reconhecer_exige_login(client, auth_state, reconhecedor):
    auth_state["user"] = None
    resp = await client.post("/api/q/calculadora/reconhecer", json={"image_base64": PNG_B64})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reconhecer_free_recebe_pro_required(client, auth_state, reconhecedor):
    auth_state["user"] = USER_A  # sem assinatura/voucher
    resp = await client.post("/api/q/calculadora/reconhecer", json={"image_base64": PNG_B64})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "pro_required"


@pytest.mark.asyncio
async def test_reconhecer_admin_ok(client, reconhecedor):
    resp = await client.post("/api/q/calculadora/reconhecer", json={"image_base64": PNG_B64})
    assert resp.status_code == 200
    assert resp.json() == {"expression": "2+2"}
    # Alias default do painel quando nada foi configurado.
    assert reconhecedor["alias"] == "gemini-3-flash-preview"


@pytest.mark.asyncio
async def test_reconhecer_usa_alias_configurado(client, reconhecedor, db_session):
    from llm_registry import SETTING_CALC, set_setting

    await set_setting(db_session, SETTING_CALC, "witdev_copilot/claude-sonnet-5")
    resp = await client.post("/api/q/calculadora/reconhecer", json={"image_base64": PNG_B64})
    assert resp.status_code == 200
    assert reconhecedor["alias"] == "witdev_copilot/claude-sonnet-5"


@pytest.mark.asyncio
async def test_reconhecer_ilegivel_422(client, reconhecedor):
    reconhecedor["raises"] = ReconhecimentoIlegivel()
    resp = await client.post("/api/q/calculadora/reconhecer", json={"image_base64": PNG_B64})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "ilegivel"


@pytest.mark.asyncio
async def test_reconhecer_ia_indisponivel_503(client, reconhecedor):
    reconhecedor["raises"] = IaIndisponivel()
    resp = await client.post("/api/q/calculadora/reconhecer", json={"image_base64": PNG_B64})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ia_indisponivel"


@pytest.mark.asyncio
async def test_reconhecer_base64_invalido(client, reconhecedor):
    resp = await client.post(
        "/api/q/calculadora/reconhecer", json={"image_base64": "isso não é b64!!!"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reconhecer_imagem_grande_413(client, reconhecedor):
    grande = base64.b64encode(b"x" * (2 * 1024 * 1024 + 1)).decode()
    resp = await client.post("/api/q/calculadora/reconhecer", json={"image_base64": grande})
    assert resp.status_code == 413


# ─── vision_calc unidades ────────────────────────────────


def test_clean_expression_normal():
    assert _clean_expression("  2+2 \n") == "2+2"


def test_clean_expression_code_fence():
    assert _clean_expression("```\nsqrt(16)\n```") == "sqrt(16)"


def test_clean_expression_erro_e_vazio():
    with pytest.raises(ReconhecimentoIlegivel):
        _clean_expression("ERRO")
    with pytest.raises(ReconhecimentoIlegivel):
        _clean_expression("   ")


@pytest.mark.asyncio
async def test_fallback_alias_nao_gemini_vira_indisponivel(monkeypatch):
    import httpx

    async def proxy_caindo(image_b64, alias):
        raise httpx.ConnectError("proxy fora")

    monkeypatch.setattr(vision_calc, "_via_proxy", proxy_caindo)
    with pytest.raises(IaIndisponivel):
        await vision_calc.reconhecer_expressao(PNG_B64, "witdev_copilot/claude-sonnet-5")


@pytest.mark.asyncio
async def test_fallback_alias_gemini_tenta_direto(monkeypatch):
    import httpx

    async def proxy_caindo(image_b64, alias):
        raise httpx.ConnectError("proxy fora")

    chamadas = {}

    async def gemini_direto(image_b64, gemini_model):
        chamadas["model"] = gemini_model
        return "5!"

    monkeypatch.setattr(vision_calc, "_via_proxy", proxy_caindo)
    monkeypatch.setattr(vision_calc, "_via_gemini_direto", gemini_direto)

    result = await vision_calc.reconhecer_expressao(
        PNG_B64, "witdev_copilot/gemini-3-flash-preview"
    )
    assert result == "5!"
    assert chamadas["model"] == "gemini-3-flash-preview"
