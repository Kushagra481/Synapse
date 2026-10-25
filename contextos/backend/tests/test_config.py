from urllib.parse import urlsplit

from app.core.config import Settings, is_test_runtime, settings


def test_sensitive_configuration_has_no_embedded_defaults(monkeypatch):
    for name in ("SECRET_KEY", "DATABASE_URL", "NEO4J_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    config = Settings(_env_file=None)

    assert config.SECRET_KEY == ""
    assert config.NEO4J_PASSWORD == ""
    database_url = urlsplit(config.DATABASE_URL)
    assert database_url.username is None
    assert database_url.password is None


def test_test_mode_bypass_requires_active_pytest(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert is_test_runtime() is False

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_config.py::test_case")
    assert is_test_runtime() is True
