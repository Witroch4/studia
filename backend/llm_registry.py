"""Registry de modelos LLM: settings por recurso + catálogo central.

Contrato canônico (witdev-platform-core/docs/agent-memory/llm-model-catalog-contract.md):
a autoridade de modelos é `platform-api /api/v1/llm/models` (que normaliza o
/model/info do LiteLLM). Apps NUNCA hardcodam catálogo — a lista local aqui é
apenas fallback de degradação, marcada `source: "local_fallback"` e nunca
mesclada com a central.

Settings (tabela app_settings):
- llm.calculadora_reconhecimento → alias canônico completo (ex.:
  witdev_copilot/gemini-3-flash-preview); a chamada vai por /v1 do proxy.
- llm.processamento_pdf / llm.chat_aula → id Gemini upstream (exceção
  deliberada: genai SDK via passthrough /gemini preserva o Batch 50% off).
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import AppSetting

# ─── Chaves e defaults ───────────────────────────────────

SETTING_CALC = "llm.calculadora_reconhecimento"
SETTING_PDF = "llm.processamento_pdf"
SETTING_CHAT = "llm.chat_aula"

# Alias canônico como servido pelo catálogo central (SEM prefixo de grupo:
# grupos "witdev_copilot/*" roteiam por credencial Copilot, que pode estar
# inativa — em prod o alias vigente é o id puro, ex. gemini-3-flash-preview).
DEFAULT_CALC_ALIAS = "gemini-3-flash-preview"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"

SETTING_DEFAULTS = {
    SETTING_CALC: DEFAULT_CALC_ALIAS,
    SETTING_PDF: DEFAULT_GEMINI_MODEL,
    SETTING_CHAT: DEFAULT_GEMINI_MODEL,
}

PLATFORM_LLM_CATALOG_URL = os.getenv(
    "PLATFORM_LLM_CATALOG_URL", "http://platform-api:8000/api/v1/llm/models"
)
CATALOG_CACHE_TTL_S = 60.0
CATALOG_TIMEOUT_S = 10.0

# ─── Lista Gemini local (fallback de degradação) ─────────

GEMINI_MODELS = [
    {
        "value": "gemini-3.1-pro-preview",
        "label": "Gemini 3.1 Pro Preview",
        "description": "SOTA reasoning com profundidade e multimodal avançado",
        "pricing": "≤200K: $2.00 / $12.00 · >200K: $4.00 / $18.00",
        "recommended": False,
    },
    {
        "value": "gemini-3-flash-preview",
        "label": "Gemini 3 Flash Preview",
        "description": "Inteligência frontier com velocidade, search e grounding",
        "pricing": "$0.50 / $3.00 por 1M tokens",
        "recommended": True,
    },
    {
        "value": "gemini-3-pro-preview",
        "label": "Gemini 3 Pro Preview",
        "description": "Raciocínio avançado, multimodal e vibe coding",
        "pricing": "≤200K: $2.00 / $12.00 · >200K: $4.00 / $18.00",
        "recommended": False,
    },
    {
        "value": "gemini-2.5-pro",
        "label": "Gemini 2.5 Pro",
        "description": "Geração anterior, excelente em código e raciocínio complexo",
        "pricing": "≤200K: $1.25 / $10.00 · >200K: $2.50 / $15.00",
        "recommended": False,
    },
    {
        "value": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash",
        "description": "Raciocínio híbrido, 1M context, thinking budgets",
        "pricing": "$0.30 / $2.50 por 1M tokens",
        "recommended": False,
    },
    {
        "value": "gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite",
        "description": "Menor e mais econômico, feito para uso em escala",
        "pricing": "$0.10 / $0.40 por 1M tokens",
        "recommended": False,
    },
    {
        "value": "gemini-flash-latest",
        "label": "Gemini Flash (latest)",
        "description": "Alias automático → gemini-2.5-flash-preview mais recente",
        "pricing": "$0.30 / $2.50 por 1M tokens",
        "recommended": False,
    },
    {
        "value": "gemini-flash-lite-latest",
        "label": "Gemini Flash Lite (latest)",
        "description": "Alias automático → Flash Lite mais recente",
        "pricing": "$0.10 / $0.40 por 1M tokens",
        "recommended": False,
    },
]

# ─── Settings (app_settings) ─────────────────────────────


async def get_setting(db: AsyncSession, key: str, default: Optional[str] = None) -> Optional[str]:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return row.value if row else default


async def set_setting(db: AsyncSession, key: str, value: str) -> None:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    await db.commit()


def gemini_id_from_alias(alias: str) -> str:
    """Deriva o id Gemini upstream do alias canônico (sufixo após o prefixo WitDev)."""
    return alias.rsplit("/", 1)[-1]


# ─── Catálogo central (com cache + fallback local) ───────

_catalog_cache: dict[str, Any] = {"at": 0.0, "payload": None}


def _normalize_central_models(payload: Any) -> list[dict[str, Any]]:
    """Normaliza o payload da platform-api ao shape consumido pelo studIA."""
    if not isinstance(payload, dict):
        return []

    models = []
    for raw in payload.get("models") or []:
        if not isinstance(raw, dict):
            continue
        value = raw.get("value") or raw.get("alias")
        if not value:
            continue
        models.append(
            {
                "value": value,
                "label": raw.get("label") or value,
                "provider": raw.get("provider") or "",
                "description": raw.get("description"),
                "pricing": raw.get("pricing"),
                "capabilities": {"vision": bool(raw.get("supportsVision"))},
            }
        )
    return models


def _local_fallback_payload() -> dict[str, Any]:
    return {
        "source": "local_fallback",
        "models": [
            {
                "value": m["value"],
                "label": m["label"],
                "provider": "gemini",
                "description": m.get("description"),
                "pricing": m.get("pricing"),
                # Toda a lista local é Gemini multimodal (aceita imagem).
                "capabilities": {"vision": True},
            }
            for m in GEMINI_MODELS
        ],
    }


def invalidate_catalog_cache() -> None:
    """Zera o cache (usado em testes)."""
    _catalog_cache["at"] = 0.0
    _catalog_cache["payload"] = None


async def fetch_catalog() -> dict[str, Any]:
    """Catálogo de modelos: central quando disponível, senão fallback local.

    Regras do contrato: central com ≥1 modelo → usa SÓ a central; central
    fora/vazia/inválida → fallback local marcado — nunca mescla as duas.
    """
    now = time.monotonic()
    if _catalog_cache["payload"] is not None and now - _catalog_cache["at"] < CATALOG_CACHE_TTL_S:
        return _catalog_cache["payload"]

    models: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=CATALOG_TIMEOUT_S) as client:
            resp = await client.get(PLATFORM_LLM_CATALOG_URL)
            if resp.status_code == 200:
                models = _normalize_central_models(resp.json())
    except (httpx.HTTPError, ValueError):
        models = []

    payload = {"source": "central", "models": models} if models else _local_fallback_payload()
    _catalog_cache["payload"] = payload
    _catalog_cache["at"] = now
    return payload


def gemini_options_from_catalog(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Filtra o catálogo a modelos Gemini e persiste o id upstream derivado.

    Usado pelos recursos que continuam na genai SDK (PDF Batch + chat de aula):
    o `value` vira o id Gemini (sufixo do alias) — é o que a SDK entende.
    """
    options = []
    seen: set[str] = set()
    for m in catalog["models"]:
        if (m.get("provider") or "").lower() != "gemini":
            continue
        gid = gemini_id_from_alias(m["value"])
        if gid in seen:
            continue
        seen.add(gid)
        options.append({**m, "value": gid})
    return options
