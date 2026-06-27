from app.main import api


def test_rota_registrada():
    paths = [r.path for r in api.routes]
    assert "/enqueue/comentarios" in paths
