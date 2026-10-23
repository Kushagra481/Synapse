import pytest
from httpx import AsyncClient

from app.core.config import settings
from conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_authenticated_repository_requests_create_minimal_audit_events(
    client: AsyncClient, monkeypatch
):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    monkeypatch.setattr("app.main.get_session_factory", lambda: TestingSessionLocal)

    created = await client.post(
        "/repositories", json={"name": "audit-demo", "local_path": "/tmp/contextos-audit"}
    )
    assert created.status_code == 201, created.text
    repo_id = created.json()["id"]

    fetched = await client.get(f"/repositories/{repo_id}")
    assert fetched.status_code == 200
    events = await client.get(f"/repositories/{repo_id}/audit-events")
    assert events.status_code == 200, events.text
    assert any(
        row["action"] == "GET /repositories/{repo_id}"
        and row["project_id"] == repo_id
        and row["actor"] == "local"
        and row["outcome"] == "success"
        and "request_body" not in row["details"]
        for row in events.json()
    )
