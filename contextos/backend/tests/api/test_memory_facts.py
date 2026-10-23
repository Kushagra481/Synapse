import pytest
from git import Repo
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_memory_fact_provenance_conflicts_superseding_and_soft_delete(
    client: AsyncClient, tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    root.mkdir()
    git_repo = Repo.init(root)
    with git_repo.config_writer() as config:
        config.set_value("user", "name", "ContextOS Memory Test")
        config.set_value("user", "email", "memory@example.invalid")
    source = root / "auth.py"
    source.write_text("def verify_user(): return True\n", encoding="utf-8")
    git_repo.index.add(["auth.py"])
    git_repo.index.commit("Add auth")
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))

    created = await client.post(
        "/repositories", json={"name": "facts-demo", "local_path": str(root)}
    )
    repo_id = created.json()["id"]
    indexed = await client.post(f"/repositories/{repo_id}/ingest")
    assert indexed.status_code == 200

    fact_one = await client.post(
        f"/repositories/{repo_id}/memory/facts",
        json={
            "title": "Authentication implementation",
            "content": "Authentication uses verify_user.",
            "topic_key": "auth-implementation",
            "fact_type": "architecture",
            "source_type": "repository_file",
            "source_file_path": "auth.py",
            "evidence_quote": "def verify_user(): return True",
            "confidence": 0.9,
            "verified": True,
        },
    )
    assert fact_one.status_code == 201, fact_one.text
    first = fact_one.json()["fact"]
    assert first["source_commit_sha"] == indexed.json()["indexed_commit_sha"]
    assert first["source_content_sha256"]
    assert first["conflict_status"] == "clear"

    jev_payload = []

    async def capture_context_candidates(query, items):
        jev_payload.extend(items)
        return [0.5] * len(items)

    monkeypatch.setattr("app.services.context_pack.score_relevance", capture_context_candidates)
    handoff = await client.post(
        f"/repositories/{repo_id}/context",
        json={"task": "Check authentication implementation", "max_tokens": 1200},
    )
    assert handoff.status_code == 200, handoff.text
    assert not any(
        "verify_user" in item.get("content", "") for item in jev_payload
    )

    conflict = await client.post(
        f"/repositories/{repo_id}/memory/facts",
        json={
            "title": "Conflicting authentication note",
            "content": "Authentication is handled elsewhere.",
            "topic_key": "auth-implementation",
            "fact_type": "architecture",
            "source_type": "manual",
            "confidence": 0.4,
        },
    )
    assert conflict.status_code == 201, conflict.text
    assert conflict.json()["conflicts"] == [first["id"]]
    assert conflict.json()["fact"]["conflict_status"] == "needs_review"
    active = await client.get(f"/repositories/{repo_id}/memory/facts")
    assert active.json() == []
    archived_conflict = await client.delete(
        f"/repositories/{repo_id}/memory/facts/{conflict.json()['fact']['id']}"
    )
    assert archived_conflict.status_code == 204
    active_after_conflict_archive = await client.get(
        f"/repositories/{repo_id}/memory/facts"
    )
    assert [row["id"] for row in active_after_conflict_archive.json()] == [first["id"]]

    old = await client.post(
        f"/repositories/{repo_id}/memory/facts",
        json={
            "title": "Old task direction",
            "content": "Use the old route.",
            "topic_key": "task-direction",
            "source_type": "manual",
        },
    )
    replacement = await client.post(
        f"/repositories/{repo_id}/memory/facts",
        json={
            "title": "Current task direction",
            "content": "Use the versioned route.",
            "topic_key": "task-direction",
            "source_type": "manual",
            "supersedes_fact_id": old.json()["fact"]["id"],
            "confidence": 0.95,
            "verified": True,
        },
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["fact"]["conflict_status"] == "clear"

    source.write_text("def verify_user(): return False\n", encoding="utf-8")
    refreshed = await client.post(f"/repositories/{repo_id}/ingest")
    assert refreshed.status_code == 200, refreshed.text
    stale = await client.get(
        f"/repositories/{repo_id}/memory/facts", params={"include_stale": True}
    )
    stale_fact = next(row for row in stale.json() if row["id"] == first["id"])
    assert stale_fact["is_stale"] is True

    context = await client.post(
        f"/repositories/{repo_id}/context",
        json={"task": "What route should be used next?", "max_tokens": 1200},
    )
    assert any(item["title"] == "Current task direction" for item in context.json()["items"])
    assert not any(item["title"] == "Conflicting authentication note" for item in context.json()["items"])

    deleted = await client.delete(
        f"/repositories/{repo_id}/memory/facts/{replacement.json()['fact']['id']}"
    )
    assert deleted.status_code == 204
    after_delete = await client.get(f"/repositories/{repo_id}/memory/facts")
    assert all(row["id"] != replacement.json()["fact"]["id"] for row in after_delete.json())
