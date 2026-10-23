from types import SimpleNamespace
import json

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core import auth
from app.core.config import settings
from app.main import app
from app.api.dependencies import require_repository_access


def test_scrypt_password_and_signed_token(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_USERNAME", "operator")
    monkeypatch.setattr(settings, "AUTH_USERS_JSON", "")
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

        async def scalar(self, statement):
            return None

    with pytest.raises(HTTPException) as error:
        await require_repository_access(request, FakeDB())
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_auth_status_and_protected_routes(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_USERNAME", "operator")
    monkeypatch.setattr(settings, "AUTH_USERS_JSON", "")
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


@pytest.mark.asyncio
async def test_configured_multi_user_project_roles(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    async def ignore_audit(*args, **kwargs):
        return None
    monkeypatch.setattr("app.main._record_audit", ignore_audit)
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_USERNAME", "")
    monkeypatch.setattr(settings, "AUTH_PASSWORD_HASH", "")
    monkeypatch.setattr(
        settings, "SECRET_KEY", "a-long-test-signing-secret-value-not-for-production"
    )
    accounts = {
        name: auth.hash_password(f"{name}-test-password-is-long-enough")
        for name in ("alice", "bob", "carol", "dave")
    }
    monkeypatch.setattr(settings, "AUTH_USERS_JSON", json.dumps(accounts))

    async def login(username):
        response = await client.post(
            "/auth/login",
            json={"username": username, "password": f"{username}-test-password-is-long-enough"},
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    alice = await login("alice")
    bob = await login("bob")
    carol = await login("carol")
    dave = await login("dave")

    created = await client.post(
        "/repositories",
        headers=alice,
        json={"name": "shared-context-test", "local_path": str(tmp_path / "shared-context-test")},
    )
    assert created.status_code == 201
    repo_id = created.json()["id"]

    added_editor = await client.post(
        f"/repositories/{repo_id}/members",
        headers=alice,
        json={"username": "bob", "role": "editor"},
    )
    assert added_editor.status_code == 201
    added_viewer = await client.post(
        f"/repositories/{repo_id}/members",
        headers=alice,
        json={"username": "carol", "role": "viewer"},
    )
    assert added_viewer.status_code == 201

    editor_write = await client.post(
        f"/repositories/{repo_id}/tasks",
        headers=bob,
        json={"title": "editor can update project state"},
    )
    assert editor_write.status_code == 201

    viewer_list = await client.get(f"/repositories/{repo_id}/tasks", headers=carol)
    assert viewer_list.status_code == 200
    viewer_handoff = await client.post(
        f"/repositories/{repo_id}/context",
        headers=carol,
        json={"task": "resume work", "max_tokens": 512},
    )
    assert viewer_handoff.status_code == 200
    viewer_write = await client.post(
        f"/repositories/{repo_id}/tasks",
        headers=carol,
        json={"title": "viewer must not write"},
    )
    assert viewer_write.status_code == 403
    editor_manage_members = await client.post(
        f"/repositories/{repo_id}/members",
        headers=bob,
        json={"username": "dave", "role": "viewer"},
    )
    assert editor_manage_members.status_code == 403
    owner_grant_attempt = await client.post(
        f"/repositories/{repo_id}/members",
        headers=alice,
        json={"username": "dave", "role": "owner"},
    )
    assert owner_grant_attempt.status_code == 422
    editor_repo_update = await client.patch(
        f"/repositories/{repo_id}",
        headers=bob,
        json={"description": "edited by project editor"},
    )
    assert editor_repo_update.status_code == 200
    viewer_repo_update = await client.patch(
        f"/repositories/{repo_id}",
        headers=carol,
        json={"description": "viewer must not edit"},
    )
    assert viewer_repo_update.status_code == 403
    editor_repo_delete = await client.delete(f"/repositories/{repo_id}", headers=bob)
    assert editor_repo_delete.status_code == 403
    editor_audit_read = await client.get(
        f"/repositories/{repo_id}/audit-events", headers=bob
    )
    assert editor_audit_read.status_code == 403

    member_list = await client.get(f"/repositories/{repo_id}/members", headers=carol)
    assert member_list.status_code == 200
    assert member_list.json()["current_role"] == "viewer"
    assert {item["username"]: item["role"] for item in member_list.json()["items"]} == {
        "alice": "owner",
        "bob": "editor",
        "carol": "viewer",
    }

    outsider_repo = await client.get(f"/repositories/{repo_id}", headers=dave)
    assert outsider_repo.status_code == 404
    outsider_list = await client.get("/repositories", headers=dave)
    assert outsider_list.status_code == 200
    assert outsider_list.json()["total"] == 0

    removed = await client.delete(f"/repositories/{repo_id}/members/bob", headers=alice)
    assert removed.status_code == 204
    revoked_access = await client.get(f"/repositories/{repo_id}", headers=bob)
    assert revoked_access.status_code == 404
