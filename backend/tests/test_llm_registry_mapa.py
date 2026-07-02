"""Setting llm.mapa_edital: registrada, com default, exposta no painel admin."""
from llm_registry import SETTING_DEFAULTS, SETTING_MAPA


def test_setting_mapa_registrada_com_default():
    assert SETTING_MAPA == "llm.mapa_edital"
    assert SETTING_DEFAULTS[SETTING_MAPA] == "gemini-3-flash-preview"


def test_painel_admin_expoe_campo_mapa():
    from admin_llm_router import _FIELD_TO_KEY, LlmSettingsPut

    assert _FIELD_TO_KEY["mapa_edital"] == SETTING_MAPA
    assert "mapa_edital" in LlmSettingsPut.model_fields
