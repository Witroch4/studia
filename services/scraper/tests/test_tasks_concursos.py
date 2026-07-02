import asyncio
import app.tasks.concursos as mod


PAYLOAD = {
    "concurso": {"concurso_id_externo": 86869, "nome_completo": "X", "url_concurso": "x"},
    "arquivos": [
        {"tipo": "EDITAL", "arquivo_id_externo": 1, "uuid": "u-1", "nome_arquivo": "edital.pdf"},
        {"tipo": "GABARITO", "arquivo_id_externo": 2, "uuid": "u-2", "nome_arquivo": "gab.zip"},
    ],
}


def test_object_key_por_uuid():
    assert mod._object_key("u-1", "application/pdf", "edital.pdf") == "concursos/u-1.pdf"
    assert mod._object_key("u-2", "application/x-zip-compressed", "g.zip") == "concursos/u-2.zip"
    assert mod._object_key("u-3", None, None) == "concursos/u-3"


def test_unit_baixa_faz_upload_e_posta(monkeypatch):
    calls = {"download": [], "put": [], "post": []}
    monkeypatch.setattr(mod, "_lease", lambda **k: {"unit_id": 1, "job_id": 9, "payload": PAYLOAD})
    monkeypatch.setattr(mod, "_is_paused", lambda **k: False)
    monkeypatch.setattr(mod, "_stat_minio", lambda key: None)  # nada existe ainda
    monkeypatch.setattr(mod, "_download", lambda url: calls["download"].append(url)
                        or (b"%PDF", "application/pdf", "arquivo.pdf"))
    monkeypatch.setattr(mod, "_put_minio", lambda key, data, ct: calls["put"].append(key))
    monkeypatch.setattr(mod, "_post_import", lambda payload: calls["post"].append(payload) or {"ok": True})
    done = {}
    monkeypatch.setattr(mod, "_mark_done", lambda **k: done.update(k))
    monkeypatch.setattr(mod, "_enqueue_next", lambda **k: None)

    r = asyncio.run(mod._processar_unit_concurso(9, 86869, sleep=lambda s: None))
    assert r["status"] == "done"
    assert len(calls["download"]) == 2 and len(calls["put"]) == 2
    assert done["arquivos_ok"] == 2
    arqs = calls["post"][0]["arquivos"]
    assert arqs[0]["minio_object_key"] == "concursos/u-1.pdf"


def test_unit_post_payload_casa_contrato_backend(monkeypatch):
    """Contrato com `backend/concursos_router.py` (ArquivoImportarReq/
    ConcursoImportarReq): o payload que `_post_import` recebe (construído por
    `_processar_unit_concurso` a partir do dict que `parse_busca_page` monta)
    precisa trazer exatamente os nomes de campo que o backend exige — um
    mismatch (ex: "arquivo_id" em vez de "arquivo_id_externo") faz TODO
    concurso com arquivos dar 422 e nada é persistido, silenciosamente."""
    calls = {"download": [], "put": [], "post": []}
    monkeypatch.setattr(mod, "_lease", lambda **k: {"unit_id": 1, "job_id": 9, "payload": PAYLOAD})
    monkeypatch.setattr(mod, "_is_paused", lambda **k: False)
    monkeypatch.setattr(mod, "_stat_minio", lambda key: None)
    monkeypatch.setattr(mod, "_download", lambda url: calls["download"].append(url)
                        or (b"%PDF", "application/pdf", "arquivo.pdf"))
    monkeypatch.setattr(mod, "_put_minio", lambda key, data, ct: calls["put"].append(key))
    monkeypatch.setattr(mod, "_post_import", lambda payload: calls["post"].append(payload) or {"ok": True})
    monkeypatch.setattr(mod, "_mark_done", lambda **k: None)
    monkeypatch.setattr(mod, "_enqueue_next", lambda **k: None)

    r = asyncio.run(mod._processar_unit_concurso(9, 86869, sleep=lambda s: None))
    assert r["status"] == "done"

    payload = calls["post"][0]
    arquivo_required = {
        "tipo", "arquivo_id_externo", "uuid", "nome_arquivo",
        "minio_object_key", "content_type", "tamanho_bytes",
    }
    concurso_required = {"concurso_id_externo", "nome_completo", "url_concurso"}
    for arq in payload["arquivos"]:
        assert arquivo_required <= set(arq.keys())
    assert concurso_required <= set(payload["concurso"].keys())


def test_unit_pula_download_se_objeto_existe(monkeypatch):
    monkeypatch.setattr(mod, "_lease", lambda **k: {"unit_id": 1, "job_id": 9, "payload": PAYLOAD})
    monkeypatch.setattr(mod, "_is_paused", lambda **k: False)
    monkeypatch.setattr(mod, "_stat_minio",
                        lambda key: {"content_type": "application/pdf", "size": 10, "key": key + ".pdf"})
    baixou = []
    monkeypatch.setattr(mod, "_download", lambda url: baixou.append(url))
    monkeypatch.setattr(mod, "_put_minio", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_post_import", lambda payload: {"ok": True})
    monkeypatch.setattr(mod, "_mark_done", lambda **k: None)
    monkeypatch.setattr(mod, "_enqueue_next", lambda **k: None)
    r = asyncio.run(mod._processar_unit_concurso(9, 86869, sleep=lambda s: None))
    assert r["status"] == "done" and baixou == []  # idempotente: não re-baixa


def test_unit_funciona_com_hooks_async(monkeypatch):
    """Trava o caminho async real: _download/_stat_minio/_put_minio/_post_import
    são corotinas em produção — _call precisa awaitá-las."""
    calls = {"download": [], "put": [], "post": []}

    async def alease(**k):
        return {"unit_id": 1, "job_id": 9, "payload": PAYLOAD}

    async def apaused(**k):
        return False

    async def astat(key):
        return None

    async def adownload(url):
        calls["download"].append(url)
        return (b"%PDF", "application/pdf", "arquivo.pdf")

    async def aput(key, data, ct):
        calls["put"].append(key)

    async def apost(payload):
        calls["post"].append(payload)
        return {"ok": True}

    done = {}

    async def adone(**k):
        done.update(k)

    async def anext(**k):
        return None

    async def asleep(s):
        return None

    monkeypatch.setattr(mod, "_lease", alease)
    monkeypatch.setattr(mod, "_is_paused", apaused)
    monkeypatch.setattr(mod, "_stat_minio", astat)
    monkeypatch.setattr(mod, "_download", adownload)
    monkeypatch.setattr(mod, "_put_minio", aput)
    monkeypatch.setattr(mod, "_post_import", apost)
    monkeypatch.setattr(mod, "_mark_done", adone)
    monkeypatch.setattr(mod, "_enqueue_next", anext)

    r = asyncio.run(mod._processar_unit_concurso(9, 86869, sleep=asleep))
    assert r["status"] == "done"
    assert len(calls["download"]) == 2 and len(calls["put"]) == 2
    assert done["arquivos_ok"] == 2
    assert calls["post"][0]["arquivos"][1]["minio_object_key"] == "concursos/u-2.pdf"


def test_finalizar_descoberta_fecha_job_sem_units(monkeypatch):
    """Job de 0 units: refresh_concursos_job_status nunca finaliza (a condição
    de done exige total_units > 0) — _finalizar_descoberta marca 'done'
    explicitamente."""
    marcado = []
    monkeypatch.setattr(mod, "_discovery_done", lambda **k: 0)
    monkeypatch.setattr(mod, "_marcar_job_done", lambda **k: marcado.append(k))

    total = asyncio.run(mod._finalizar_descoberta(7))
    assert total == 0
    assert marcado == [{"job_id": 7}]


def test_finalizar_descoberta_nao_forca_done_com_units(monkeypatch):
    marcado = []
    monkeypatch.setattr(mod, "_discovery_done", lambda **k: 12)
    monkeypatch.setattr(mod, "_marcar_job_done", lambda **k: marcado.append(k))

    total = asyncio.run(mod._finalizar_descoberta(7))
    assert total == 12
    assert marcado == []  # com units, quem finaliza é o refresh normal
