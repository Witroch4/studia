"""Painel admin "Modelos de IA": catálogo central + settings recurso→modelo.

- GET /api/admin/llm/models   → proxy do catálogo da autoridade (platform-api),
  com fallback local marcado quando a central está fora/vazia.
- GET /api/admin/llm/settings → mapa recurso→modelo efetivo (defaults aplicados).
- PUT /api/admin/llm/settings → grava; valida cada valor contra a lista
  atualmente servida (central ou fallback — nunca aceita valor fora dela).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db
from llm_registry import (
    SETTING_CALC,
    SETTING_CHAT,
    SETTING_DEFAULTS,
    SETTING_MAPA,
    SETTING_PDF,
    fetch_catalog,
    gemini_options_from_catalog,
    get_setting,
    set_setting,
)

router = APIRouter(prefix="/api/admin/llm", tags=["admin-llm"], dependencies=[Depends(require_admin)])

# Campo da API ↔ chave em app_settings
_FIELD_TO_KEY = {
    "calculadora_reconhecimento": SETTING_CALC,
    "processamento_pdf": SETTING_PDF,
    "chat_aula": SETTING_CHAT,
    "mapa_edital": SETTING_MAPA,
}


class LlmSettingsPut(BaseModel):
    calculadora_reconhecimento: Optional[str] = None
    processamento_pdf: Optional[str] = None
    chat_aula: Optional[str] = None
    mapa_edital: Optional[str] = None


@router.get("/models")
async def list_llm_models() -> dict[str, Any]:
    return await fetch_catalog()


@router.get("/settings")
async def get_llm_settings(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field, key in _FIELD_TO_KEY.items():
        out[field] = await get_setting(db, key, SETTING_DEFAULTS[key])
    return out


@router.put("/settings")
async def put_llm_settings(
    body: LlmSettingsPut,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    catalog = await fetch_catalog()
    # Calculadora persiste o alias canônico completo; PDF/chat persistem o id
    # Gemini upstream (exceção Batch) — cada um valida contra a sua lista.
    alias_values = {m["value"] for m in catalog["models"]}
    gemini_values = {m["value"] for m in gemini_options_from_catalog(catalog)}

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(422, "nenhuma configuração enviada")

    for field, value in updates.items():
        allowed = alias_values if field == "calculadora_reconhecimento" else gemini_values
        if value not in allowed:
            raise HTTPException(422, f"modelo '{value}' não está no catálogo atual")

    for field, value in updates.items():
        await set_setting(db, _FIELD_TO_KEY[field], value)

    return await get_llm_settings(db)
