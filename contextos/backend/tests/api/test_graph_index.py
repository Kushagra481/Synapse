import pytest
from git import Repo
from httpx import AsyncClient

from app.core.config import settings
from app.services import graph_index


@pytest.mark.asyncio
async def test_graph_projection_contains_import_edges_not_source_bodies(
    client: AsyncClient, db_session, tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    root.mkdir()
    repo = Repo.init(root)
    with repo.config_writer() as config:
        config.set_value("user", "name", "ContextOS Graph Test")
        config.set_value("user", "email", "graph@example.invalid")
    (root / "main.py").write_text(
        "import helper\n\ndef run():\n    return 'must-not-enter-graph'\n", encoding="utf-8"
    )
    (root / "helper.py").write_text("def help_user(): return True\n", encoding="utf-8")
    repo.index.add(["main.py", "helper.py"])
    repo.index.commit("Graph fixture")
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))
    created = await client.post(
        "/repositories", json={"name": "graph-demo", "local_path": str(root)}
    )
    repository_id = created.json()["id"]
    indexed = await client.post(f"/repositories/{repository_id}/ingest")
    assert indexed.status_code == 200, indexed.text

    captured = []

    class FakeGraphSession:
        def __init__(self):
            pass

        async def run_transaction(self, statements):
            captured.extend(statements)

    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "GRAPH_SYNC_ENABLED", True)
    monkeypatch.setattr(graph_index, "GraphSession", FakeGraphSession)
    result = await graph_index.sync_repository_graph(
        db_session, repository_id, "graph-demo", indexed.json()["indexed_commit_sha"]
    )
    assert result == "synced"
    rendered = repr(captured)
    assert "IMPORTS" in rendered
    assert "DEFINES" in rendered
    assert "must-not-enter-graph" not in rendered
    assert any("target_file_path" in repr(params) for _, params in captured)
