"""Reconhecimento de desenho da calculadora → expressão matemática.

Caminho principal: POST /v1/chat/completions do LiteLLM (alias canônico do
painel admin; o proxy resolve o provider). Degradação: se o proxy estiver
fora E o alias for Gemini, tenta Gemini direto via GEMINI_API_KEY (mesma
contingência do gemini_service).
"""

from __future__ import annotations

import base64
import os

import httpx

LITELLM_BASE_URL_DEFAULT = "http://platform-litellm:4000"
RECOGNIZE_TIMEOUT_S = 20.0

SYSTEM_PROMPT = (
    "Você é um transcritor estrito de expressões matemáticas desenhadas à mão. "
    "Devolva SOMENTE a expressão matemática na sintaxe da calculadora: dígitos, "
    "operadores + - * / ^ % ! ( ) e ponto decimal, funções sin cos tan asin acos "
    "atan log ln exp sqrt, constantes pi e e. Converta ÷ para /, × para *, "
    "√x para sqrt(x), frações verticais para (a)/(b), potências para ^. "
    "Sem explicação, sem markdown, sem espaços desnecessários. "
    "Se o desenho for ilegível ou não for matemática, devolva exatamente ERRO."
)


class ReconhecimentoIlegivel(Exception):
    """O modelo leu a imagem mas não achou expressão (devolveu ERRO/vazio)."""


class IaIndisponivel(Exception):
    """Proxy fora e sem fallback aplicável — recurso indisponível agora."""


def _clean_expression(raw: str) -> str:
    text = (raw or "").strip()
    # Modelos às vezes embrulham em code fence mesmo instruídos a não fazer.
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("text") or text.lower().startswith("math"):
            text = text.split("\n", 1)[-1].strip()
    if not text or text.upper() == "ERRO":
        raise ReconhecimentoIlegivel()
    return text


async def _via_proxy(image_b64: str, alias: str) -> str:
    base = os.getenv("LITELLM_BASE_URL", LITELLM_BASE_URL_DEFAULT).rstrip("/")
    key = os.getenv("LITELLM_API_KEY", "")
    async with httpx.AsyncClient(timeout=RECOGNIZE_TIMEOUT_S) as client:
        resp = await client.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": alias,
                "temperature": 0,
                "max_tokens": 120,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                            }
                        ],
                    },
                ],
            },
        )
    if resp.status_code >= 500:
        raise httpx.HTTPStatusError("proxy 5xx", request=resp.request, response=resp)
    resp.raise_for_status()
    data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return _clean_expression(content)


async def _via_gemini_direto(image_b64: str, gemini_model: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise IaIndisponivel()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model=gemini_model,
        contents=[
            types.Part.from_bytes(data=base64.b64decode(image_b64), mime_type="image/png"),
            SYSTEM_PROMPT,
        ],
        config=types.GenerateContentConfig(temperature=0, max_output_tokens=120),
    )
    return _clean_expression(response.text or "")


async def reconhecer_expressao(image_b64: str, alias: str) -> str:
    """Transcreve o desenho para expressão. Levanta ReconhecimentoIlegivel /
    IaIndisponivel para o endpoint mapear em 422/503."""
    try:
        return await _via_proxy(image_b64, alias)
    except ReconhecimentoIlegivel:
        raise
    except (httpx.HTTPError, ValueError, KeyError):
        # Proxy fora / resposta 5xx ou inválida → fallback só quando o alias é Gemini.
        gemini_id = alias.rsplit("/", 1)[-1]
        if "gemini" not in gemini_id.lower():
            raise IaIndisponivel()
        try:
            return await _via_gemini_direto(image_b64, gemini_id)
        except ReconhecimentoIlegivel:
            raise
        except Exception:
            raise IaIndisponivel()
