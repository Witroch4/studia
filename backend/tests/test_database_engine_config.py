import database


def test_runtime_engine_uses_health_checked_pool(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "11")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "7")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "4.5")
    monkeypatch.setenv("DB_POOL_RECYCLE", "120")
    monkeypatch.setenv("DB_APPLICATION_NAME", "studia-test")

    kwargs = database._engine_kwargs_from_env()

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_size"] == 11
    assert kwargs["max_overflow"] == 7
    assert kwargs["pool_timeout"] == 4.5
    assert kwargs["pool_recycle"] == 120
    assert kwargs["connect_args"]["server_settings"]["application_name"] == "studia-test"
