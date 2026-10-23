from urllib.parse import urlsplit

from app.core.config import Settings


def test_sensitive_configuration_has_no_embedded_defaults(monkeypatch):
    for name in ("SECRET_KEY", "DATABASE_URL", "NEO4J_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    config = Settings(_env_file=None)

    assert config.SECRET_KEY == ""
    assert config.NEO4J_PASSWORD == ""
    database_url = urlsplit(config.DATABASE_URL)
    assert database_url.username is None
    assert database_url.password is None
