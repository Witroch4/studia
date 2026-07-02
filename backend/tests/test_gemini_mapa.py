"""extrair_edital_estruturado / mapear_materias com client Gemini mockado."""
import json
from unittest.mock import MagicMock

import pytest

import gemini_service


def _mock_client(monkeypatch, text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=text)
    monkeypatch.setattr(gemini_service, "_get_client", lambda: client)
    return client


def test_extrair_edital_envia_pdf_e_parseia(monkeypatch):
    client = _mock_client(monkeypatch, json.dumps({"cargos": [{"nome": "Engenheiro Civil"}]}))
    out = gemini_service.extrair_edital_estruturado(b"%PDF-fake", "gemini-3-flash-preview")
    assert out["cargos"][0]["nome"] == "Engenheiro Civil"
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3-flash-preview"
    assert kwargs["config"].response_mime_type == "application/json"


def test_extrair_edital_recusa_pdf_gigante(monkeypatch):
    _mock_client(monkeypatch, "{}")
    with pytest.raises(ValueError, match="20MB"):
        gemini_service.extrair_edital_estruturado(b"x" * (21 * 1024 * 1024), "m")


def test_mapear_materias_filtra_fora_do_banco(monkeypatch):
    _mock_client(monkeypatch, json.dumps({"mapeamento": {
        "Língua Portuguesa": "Português",
        "Raciocínio Lógico": "Matemágica Inventada",
    }}))
    out = gemini_service.mapear_materias(
        ["Língua Portuguesa", "Raciocínio Lógico"], ["Português", "Matemática"], "m"
    )
    assert out == {"Língua Portuguesa": "Português", "Raciocínio Lógico": None}


def test_mapear_materias_listas_vazias_sem_ia(monkeypatch):
    client = _mock_client(monkeypatch, "{}")
    assert gemini_service.mapear_materias(["A"], [], "m") == {"A": None}
    client.models.generate_content.assert_not_called()
