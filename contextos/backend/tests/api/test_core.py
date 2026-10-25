import pytest
from httpx import AsyncClient
from pathlib import Path
from git import Repo
from app.core.config import settings


@pytest.mark.asyncio
async def test_graph_disabled_does_not_block_application_startup(monkeypatch):
    from app import main

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GRAPH_SYNC_ENABLED", False)
    calls = []

    async def record_db_start():
        calls.append("db_start")

    async def record_db_stop():
        calls.append("db_stop")

    async def unexpected_graph_call():
        raise AssertionError("Graph lifecycle must be skipped when graph sync is disabled.")

    monkeypatch.setattr(main, "init_db", record_db_start)
    monkeypatch.setattr(main, "close_db", record_db_stop)
    monkeypatch.setattr(main, "init_graph", unexpected_graph_call)
    monkeypatch.setattr(main, "close_graph", unexpected_graph_call)

    app = main.create_app()
    async with main.lifespan(app):
        assert calls == ["db_start"]

    assert calls == ["db_start", "db_stop"]


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


@pytest.mark.asyncio
async def test_graph_cleanup_only_runs_for_repository_delete(client: AsyncClient, monkeypatch):
    from app.api import repositories as repository_api

    created = await client.post(
        "/repositories", json={"name": "delete-check", "local_path": "/tmp/delete-check"}
    )
    repo_id = created.json()["id"]
    calls = []

    async def unavailable(repository_id):
        calls.append(repository_id)
        return "unavailable"

    monkeypatch.setattr(repository_api, "delete_repository_graph", unavailable)
    fetched = await client.get(f"/repositories/{repo_id}")
    assert fetched.status_code == 200, fetched.text
    assert calls == []

    deleted = await client.delete(f"/repositories/{repo_id}")
    assert deleted.status_code == 503
    assert calls == [repo_id]
    still_present = await client.get(f"/repositories/{repo_id}")
    assert still_present.status_code == 200


@pytest.mark.asyncio
async def test_session_handoff_captures_git_metadata_without_diff_content(
    client: AsyncClient, tmp_path, monkeypatch
):
    repo_path = tmp_path / "worktree"
    repo_path.mkdir()
    git_repo = Repo.init(repo_path)
    with git_repo.config_writer() as config:
        config.set_value("user", "name", "ContextOS Test")
        config.set_value("user", "email", "test@example.invalid")
    source = repo_path / "module.py"
    source.write_text("def stable(): return 1\n", encoding="utf-8")
    git_repo.index.add(["module.py"])
    git_repo.index.commit("Start snapshot")
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))

    created = await client.post(
        "/repositories", json={"name": "snapshot-demo", "local_path": str(repo_path)}
    )
    repo_id = created.json()["id"]
    started = await client.post(
        f"/repositories/{repo_id}/sessions",
        json={"llm_provider": "test", "llm_model": "agent", "objective": "Edit module"},
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["id"]
    start_sha = started.json()["starting_commit_sha"]
    assert start_sha == git_repo.head.commit.hexsha
    assert started.json()["git_snapshot_status"] == "captured"

    source.write_text("def stable(): return 2\n", encoding="utf-8")
    (repo_path / "new.py").write_text("def added(): pass\n", encoding="utf-8")
    finished = await client.patch(
        f"/repositories/{repo_id}/sessions/{session_id}",
        json={"status": "completed", "summary": "Updated module behavior"},
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["handoff_commit_sha"] == start_sha
    assert set(finished.json()["handoff_changed_files"]) == {"module.py", "new.py"}
    assert finished.json()["handoff_working_tree_dirty"] is True
