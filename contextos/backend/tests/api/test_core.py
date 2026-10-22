import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_repository_task_and_context_handoff(client: AsyncClient):
    created = await client.post("/repositories", json={"name": "handoff-demo", "url": "https://example.com/repo.git", "primary_language": "Python"})
    assert created.status_code == 201, created.text
    repo = created.json()
    repo_id = repo["id"]

    task = await client.post(f"/repositories/{repo_id}/tasks", json={"title": "Add search", "status": "active", "priority": "high"})
    assert task.status_code == 201, task.text
    assert task.json()["status"] == "active"

    memory = await client.patch(f"/repositories/{repo_id}/memory", json={"project_goal": "Search project docs", "architecture_summary": "FastAPI API with React UI"})
    assert memory.status_code == 200, memory.text

    pack = await client.post(f"/repositories/{repo_id}/context", json={"task": "Implement search for project docs", "max_tokens": 1000})
    assert pack.status_code == 200, pack.text
    body = pack.json()
    assert "handoff-demo" in body["text"]
    assert "Search project docs" in body["text"]
    assert "Add search" in body["text"]
    assert body["estimated_tokens"] <= 1000
    assert body["jev_used"] is False


@pytest.mark.asyncio
async def test_decisions_and_sessions_are_persisted(client: AsyncClient):
    repo_response = await client.post("/repositories", json={"name": "session-demo", "local_path": "/tmp/session-demo"})
    repo_id = repo_response.json()["id"]
    session_response = await client.post(f"/repositories/{repo_id}/sessions", json={"llm_provider": "manual", "llm_model": "agent", "objective": "Ship the settings page"})
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["id"]
    closed = await client.patch(f"/repositories/{repo_id}/sessions/{session_id}", json={"status": "completed", "summary": "Settings UI shipped", "next_steps": ["Add tests"]})
    assert closed.status_code == 200
    assert closed.json()["summary"] == "Settings UI shipped"
    decision = await client.post(f"/repositories/{repo_id}/decisions", json={"repository_id": repo_id, "title": "Use SQLite in tests", "decision": "Use SQLite for test isolation", "category": "database"})
    assert decision.status_code == 201, decision.text
    assert decision.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_repository_not_found_is_clear(client: AsyncClient):
    response = await client.get("/repositories/missing/context")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_context_pack_respects_minimum_budget(client: AsyncClient):
    created = await client.post("/repositories", json={"name": "budget-demo", "local_path": "/tmp/budget-demo"})
    repo_id = created.json()["id"]
    response = await client.post(
        f"/repositories/{repo_id}/context",
        json={"task": "x" * 6000, "max_tokens": 128},
    )
    assert response.status_code == 200, response.text
    assert response.json()["estimated_tokens"] <= 128
