from pathlib import Path

import pytest
from git import Repo
from httpx import AsyncClient

from app.core.config import settings


def _repo(path: Path) -> Repo:
    path.mkdir(parents=True)
    repo = Repo.init(path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "ContextOS Eval")
        config.set_value("user", "email", "eval@example.invalid")
    (path / "auth.py").write_text(
        "def verify_user_token(token: str) -> bool:\n"
        "    return bool(token)\n",
        encoding="utf-8",
    )
    repo.index.add(["auth.py"])
    repo.index.commit("Add token verification")
    return repo


@pytest.mark.asyncio
async def test_benchmark_compares_profiles_and_persists_metrics(
    client: AsyncClient, tmp_path, monkeypatch
):
    repo_path = tmp_path / "repo"
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))
    _repo(repo_path)
    created = await client.post(
        "/repositories", json={"name": "eval-demo", "local_path": str(repo_path)}
    )
    repository_id = created.json()["id"]
    indexed = await client.post(f"/repositories/{repository_id}/ingest")
    assert indexed.status_code == 200, indexed.text

    case = await client.post(
        f"/repositories/{repository_id}/evaluations/cases",
        json={
            "name": "find token verification",
            "query": "Where is user token verification implemented?",
            "expected_files": ["auth.py"],
            "expected_symbols": ["verify_user_token"],
        },
    )
    assert case.status_code == 201, case.text

    run = await client.post(
        f"/repositories/{repository_id}/evaluations/runs",
        json={"profiles": ["lexical", "hybrid", "jev"], "top_k": 3},
    )
    assert run.status_code == 201, run.text
    result = run.json()
    assert result["case_count"] == 1
    assert result["metrics"]["lexical"]["recall_at_k"] == 1.0
    assert result["metrics"]["hybrid"]["recall_at_k"] == 1.0
    assert result["metrics"]["hybrid"]["mrr"] == 1.0
    assert result["metrics"]["jev"]["jev_used"] == 0.0
    jev_case = next(row for row in result["case_results"] if row["profile"] == "jev")
    assert jev_case["retrieval"]["jev_status"] == "disabled_by_policy"
    assert result["metrics"]["hybrid"]["provenance_coverage"] > 0
    assert result["estimated_tokens"] > 0
    assert result["index_commit_sha"] == indexed.json()["indexed_commit_sha"]

    persisted = await client.get(
        f"/repositories/{repository_id}/evaluations/runs/{result['id']}"
    )
    assert persisted.status_code == 200
    assert persisted.json()["metrics"] == result["metrics"]


@pytest.mark.asyncio
async def test_benchmark_requires_at_least_one_case(client: AsyncClient, tmp_path, monkeypatch):
    repo_path = tmp_path / "empty-eval"
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))
    _repo(repo_path)
    created = await client.post(
        "/repositories", json={"name": "empty-eval", "local_path": str(repo_path)}
    )
    response = await client.post(
        f"/repositories/{created.json()['id']}/evaluations/runs", json={}
    )
    assert response.status_code == 409
