import asyncio
import app.tasks.concursos as mod


PAYLOAD = {
    "concurso": {"concurso_id_externo": 86869, "nome_completo": "X", "url_concurso": "x"},
    "arquivos": [
        {"tipo": "EDITAL", "arquivo_id": 1, "uuid": "u-1", "nome_arquivo": "edital.pdf"},
        {"tipo": "GABARITO", "arquivo_id": 2, "uuid": "u-2", "nome_arquivo": "gab.zip"},
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
