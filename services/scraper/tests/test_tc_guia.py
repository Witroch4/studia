from __future__ import annotations

import pytest

from app.scrapers import tc_guia
from app.scrapers.tc_guia import resolver_guia


class _FakeResp:
    def __init__(self, *, text: str = "", json_data=None, status: int = 200):
        self.text = text
        self._json = json_data
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        return None


class _FakeHttpx:
    """Mapa path -> _FakeResp para GET; registra chamadas."""

    def __init__(self, routes: dict[str, _FakeResp]):
        self.routes = routes
        self.gets: list[str] = []

    async def get(self, path, **kwargs):
        self.gets.append(path)
        for key, resp in self.routes.items():
            if key in path:
                return resp
        raise AssertionError(f"GET inesperado: {path}")


class _FakeClient:
    def __init__(self, routes: dict[str, _FakeResp]):
        self._client = _FakeHttpx(routes)

    def _check(self, r):  # noqa: D401 - no-op (sessão sempre válida no teste)
        return None


BASE_HTML = """
<html><head><title>Guia OAB / 2026 para concurso Nacional Unificado</title></head>
<body>Banca FGV
<a href="https://www.tecconcursos.com.br/guias/oab-2026/nacional-unificado-oab/-/-">cargo</a>
</body></html>
"""

CARGO_HTML = """
<html><head><title>Guia OAB / 2026 para concurso Nacional Unificado</title></head>
<body>FGV
<script>var jsonGuiaId = "6818";</script>
</body></html>
"""

LISTAR_JSON = {
    "cadernosGuia": [
        {
            "id": 73889,
            "cadernoBaseId": 86980764,
            "disciplina": "Direito Administrativo - OAB 2026 - 46º Exame",
            "totalQuestoes": 1804,
            "totalCapitulos": 152,
            "usuarioPossuiCadernoSalvo": True,
            "cadernoQuestaoRecenteId": 96081460,
            "ordem": 1,
        },
        {
            # caderno-guia ainda não entregue: sem cadernoQuestaoRecenteId -> ignorado
            "id": 99999,
            "cadernoBaseId": None,
            "disciplina": "Caderno futuro",
            "totalQuestoes": 0,
            "totalCapitulos": 0,
            "usuarioPossuiCadernoSalvo": False,
            "cadernoQuestaoRecenteId": None,
            "ordem": None,
        },
    ]
}


@pytest.mark.asyncio
async def test_resolver_guia_segue_link_de_cargo_e_extrai_id():
    routes = {
        "/guias/oab-2026/nacional-unificado-oab/-/-": _FakeResp(text=CARGO_HTML),
        "/guias/oab-2026": _FakeResp(text=BASE_HTML),
        "/api/caderno-guia/listar-pelo-guia/6818": _FakeResp(json_data=LISTAR_JSON),
    }
    client = _FakeClient(routes)

    guia = await resolver_guia(client, "https://www.tecconcursos.com.br/guias/oab-2026")

    assert guia.tc_guia_id == 6818
    assert guia.banca == "FGV"
    assert "Nacional Unificado" in guia.nome
    # caderno sem cadernoQuestaoRecenteId é filtrado
    assert len(guia.cadernos) == 1
    assert guia.cadernos[0].tc_caderno_id == 96081460
    assert guia.cadernos[0].total_questoes == 1804


@pytest.mark.asyncio
async def test_resolver_guia_aceita_url_de_cargo_direta():
    routes = {
        "/guias/oab-2026/nacional-unificado-oab/-/-": _FakeResp(text=CARGO_HTML),
        "/api/caderno-guia/listar-pelo-guia/6818": _FakeResp(json_data=LISTAR_JSON),
    }
    client = _FakeClient(routes)

    guia = await resolver_guia(
        client,
        "https://www.tecconcursos.com.br/guias/oab-2026/nacional-unificado-oab/-/-",
    )
    assert guia.tc_guia_id == 6818
    assert guia.slug == "oab-2026/nacional-unificado-oab"
