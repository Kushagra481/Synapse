from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core import auth
from app.core.config import settings
from app.main import app
from app.api.dependencies import require_repository_access


def test_scrypt_password_and_signed_token(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_USERNAME", "operator")
    monkeypatch.setattr(settings, "SECRET_KEY", "a-long-test-signing-secret-value-not-for-production")
    password_hash = auth.hash_password("test-password-with-enough-length")
    assert auth.verify_password("test-password-with-enough-length", password_hash)
    assert not auth.verify_password("wrong-password", password_hash)
    monkeypatch.setattr(settings, "AUTH_PASSWORD_HASH", password_hash)
    assert auth.auth_is_configured()
    token, _ = auth.issue_token("operator")
    assert auth.verify_token(token) == "operator"
    assert auth.verify_token(token + "x") is None
    monkeypatch.setattr(settings, "AUTH_USERNAME", "another-operator")
    assert auth.verify_token(token) is None


@pytest.mark.asyncio
async def test_repository_access_hides_another_owners_repository(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    request = SimpleNamespace(
        path_params={"repo_id": "repo-secret"},
        state=SimpleNamespace(principal="alice"),
    )

    class FakeDB:
        async def get(self, model, repository_id):
            assert repository_id == "repo-secret"
            return SimpleNamespace(owner_subject="bob")

    with pytest.raises(HTTPException) as error:
        await require_repository_access(request, FakeDB())
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_auth_status_and_protected_routes(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_USERNAME", "operator")
    password = "test-password-with-enough-length"
    monkeypatch.setattr(settings, "AUTH_PASSWORD_HASH", auth.hash_password(password))
    monkeypatch.setattr(settings, "SECRET_KEY", "a-long-test-signing-secret-value-not-for-production")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status_response = await client.get("/auth/status")
        assert status_response.json() == {"enabled": True, "configured": True}
        unauthorized = await client.get("/repositories")
        assert unauthorized.status_code == 401
        login = await client.post(
            "/auth/login", json={"username": "operator", "password": password}
        )
        assert login.status_code == 200
        me = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["username"] == "operator"
        health = await client.get("/api/health")
        assert health.status_code == 200
