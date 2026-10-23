from pathlib import Path

import pytest
from git import Repo
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import settings
from app.models.code_index import CodeImport, CodeSymbol, IndexedFile
from app.services.embeddings import embed_code_items
from app.services.repository_index import (
    _resolve_import_path,
    _tree_sitter_imports,
    _tree_sitter_parse,
    _tree_sitter_symbols,
)


def _git_repo(path: Path) -> Repo:
    path.mkdir(parents=True)
    repo = Repo.init(path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "ContextOS Test")
        config.set_value("user", "email", "contextos-test@example.invalid")
    return repo


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        ("python", "def lookup_user(): return 1", "lookup_user"),
        ("javascript", "function lookupUser() { return 1; }", "lookupUser"),
        ("typescript", "export function lookupUser(): number { return 1; }", "lookupUser"),
        ("tsx", "export function SearchPanel() { return <div />; }", "SearchPanel"),
        ("java", "class SearchService { void lookupUser() {} }", "lookupUser"),
        ("cpp", "int lookup_user() { return 1; }", "lookup_user"),
    ],
)
def test_tree_sitter_extracts_symbols_for_supported_languages(language, source, expected):
    symbols, _ = _tree_sitter_symbols(source, language)
    assert expected in {symbol["name"] for symbol in symbols}


def test_tree_sitter_import_edges_resolve_only_to_repo_files():
    source = "import helper\n"
    tree, _, _ = _tree_sitter_parse(source, "python")
    imports = _tree_sitter_imports(tree, source.encode(), "python")
    assert imports[0]["target_module"] == "helper"
    assert _resolve_import_path("main.py", "helper", "python", {"main.py", "helper.py"}) == "helper.py"
    assert _resolve_import_path("main.py", "third_party", "python", {"main.py"}) is None


@pytest.mark.asyncio
async def test_source_embeddings_are_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(settings, "EMBEDDINGS_ALLOW_SOURCE_UPLOAD", False)
    result = await embed_code_items(["private-looking source must not be sent"])
    assert result.status == "disabled_by_policy"
    assert result.vectors == [None]


@pytest.mark.asyncio
async def test_ingest_search_and_incremental_refresh(client: AsyncClient, db_session, tmp_path, monkeypatch):
    repo_path = tmp_path / "repositories" / "demo"
    repo_path.parent.mkdir()
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(repo_path.parent))
    git_repo = _git_repo(repo_path)

    (repo_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (repo_path / "main.py").write_text(
        "import helper\n"
        "class AuthService:\n"
        "    def login_user(self, email: str) -> bool:\n"
        "        return bool(email)\n\n"
        "def legacy_handler():\n"
        "    return 'old'\n",
        encoding="utf-8",
    )
    (repo_path / "helper.py").write_text(
        "def reusable_helper():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    (repo_path / "ignored.py").write_text("def should_not_appear(): pass\n", encoding="utf-8")
    (repo_path / ".env").write_text("DATABASE_URL=not-for-indexing\n", encoding="utf-8")
    (repo_path / "config.py").write_text(
        "api_key = 'abcdefghijklmnopqrstuvwxyz1234567890'\n", encoding="utf-8"
    )
    git_repo.index.add([".gitignore", "main.py", "helper.py", "config.py"])
    git_repo.index.commit("Add demo source")

    created = await client.post(
        "/repositories", json={"name": "demo", "local_path": str(repo_path), "language": "Python"}
    )
    assert created.status_code == 201, created.text
    repository_id = created.json()["id"]

    first = await client.post(f"/repositories/{repository_id}/ingest")
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["file_count"] == 2
    assert first_body["added_count"] == 2
    assert first_body["working_tree_dirty"] is True
    assert first_body["import_count"] == 1
    assert first_body["embedding_status"] == "disabled_by_policy"
    assert first_body["embedding_count"] == 0
    assert first_body["graph_sync_status"] == "disabled"
    assert first_body["skipped_count"] >= 3
    secret = await client.get(
        f"/repositories/{repository_id}/code/search", params={"q": "api_key"}
    )
    ignored = await client.get(
        f"/repositories/{repository_id}/code/search", params={"q": "should_not_appear"}
    )
    assert secret.json()["results"] == []
    assert ignored.json()["results"] == []

    before = await client.get(f"/repositories/{repository_id}/code/search", params={"q": "legacy_handler"})
    assert before.status_code == 200, before.text
    assert before.json()["results"][0]["file_path"] == "main.py"
    assert before.json()["results"][0]["start_line"] == 6
    assert "exact_symbol" in before.json()["results"][0]["ranking_signals"]
    assert before.json()["results"][0]["freshness"] == "file_matches_working_tree"
    assert "helper.py" in {
        result["file_path"]
        for result in (
            await client.get(
                f"/repositories/{repository_id}/code/search", params={"q": "reusable_helper"}
            )
        ).json()["results"]
    }

    (repo_path / "main.py").write_text(
        "import helper\n"
        "class AuthService:\n"
        "    def login_user(self, email: str) -> bool:\n"
        "        return bool(email)\n\n"
        "def current_handler():\n"
        "    return 'current'\n",
        encoding="utf-8",
    )
    (repo_path / "helper.py").unlink()
    stale = await client.get(
        f"/repositories/{repository_id}/code/search", params={"q": "legacy_handler"}
    )
    assert stale.json()["results"][0]["freshness"] == "stale_file_changed"

    refreshed = await client.post(f"/repositories/{repository_id}/ingest")
    assert refreshed.status_code == 200, refreshed.text
    refresh_body = refreshed.json()
    assert refresh_body["changed_count"] == 1
    assert refresh_body["removed_count"] == 1
    assert refresh_body["file_count"] == 1

    old_result = await client.get(
        f"/repositories/{repository_id}/code/search", params={"q": "legacy_handler"}
    )
    new_result = await client.get(
        f"/repositories/{repository_id}/code/search", params={"q": "current_handler"}
    )
    assert old_result.json()["results"] == []
    assert new_result.json()["results"][0]["qualified_name"] == "current_handler"
    assert new_result.json()["results"][0]["freshness"] == "file_matches_working_tree"

    again = await client.post(f"/repositories/{repository_id}/ingest")
    assert again.status_code == 200, again.text
    assert again.json()["unchanged_count"] == 1
    status = await client.get(f"/repositories/{repository_id}/index")
    assert status.status_code == 200
    assert status.json()["symbol_count"] >= 2
    handoff = await client.post(
        f"/repositories/{repository_id}/context",
        json={"task": "Update current_handler behavior", "max_tokens": 1200},
    )
    assert handoff.status_code == 200, handoff.text
    assert "main.py:6-7" in handoff.json()["text"]
    assert handoff.json()["retrieval"]["method"] == "reciprocal_rank_fusion"
    assert any(item.get("source", {}).get("file_path") == "main.py" for item in handoff.json()["items"])

    deleted = await client.delete(f"/repositories/{repository_id}")
    assert deleted.status_code == 204
    assert await db_session.scalar(
        select(func.count()).select_from(CodeSymbol).where(CodeSymbol.repository_id == repository_id)
    ) == 0
    assert await db_session.scalar(
        select(func.count()).select_from(IndexedFile).where(IndexedFile.repository_id == repository_id)
    ) == 0
    assert await db_session.scalar(
        select(func.count()).select_from(CodeImport).where(CodeImport.repository_id == repository_id)
    ) == 0


@pytest.mark.asyncio
async def test_ingestion_rejects_path_outside_allowlist(client: AsyncClient, tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    git_repo = _git_repo(outside)
    (outside / "main.py").write_text("def private_code(): pass\n", encoding="utf-8")
    git_repo.index.add(["main.py"])
    git_repo.index.commit("Add source")
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(allowed))

    created = await client.post("/repositories", json={"name": "outside", "local_path": str(outside)})
    repository_id = created.json()["id"]
    response = await client.post(f"/repositories/{repository_id}/ingest")
    assert response.status_code == 422
    assert "outside" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_full_reindex_reparses_unchanged_files(client: AsyncClient, tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))
    git_repo = _git_repo(repo_path)
    (repo_path / "main.py").write_text("def indexed_function(): return 1\n", encoding="utf-8")
    git_repo.index.add(["main.py"])
    git_repo.index.commit("Initial")

    created = await client.post("/repositories", json={"name": "full", "local_path": str(repo_path)})
    repository_id = created.json()["id"]
    initial = await client.post(f"/repositories/{repository_id}/ingest")
    assert initial.status_code == 200, initial.text
    forced = await client.post(
        f"/repositories/{repository_id}/ingest", params={"full_reindex": "true"}
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["changed_count"] == 1
    assert forced.json()["unchanged_count"] == 0


@pytest.mark.asyncio
async def test_failed_refresh_preserves_last_good_index(client: AsyncClient, tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))
    git_repo = _git_repo(repo_path)
    source = repo_path / "main.py"
    source.write_text("def stable_handler(): return 1\n", encoding="utf-8")
    git_repo.index.add(["main.py"])
    git_repo.index.commit("Initial")

    created = await client.post("/repositories", json={"name": "preserve", "local_path": str(repo_path)})
    repository_id = created.json()["id"]
    first = await client.post(f"/repositories/{repository_id}/ingest")
    assert first.status_code == 200, first.text

    source.write_text("def replacement_handler(): return 2\n", encoding="utf-8")
    monkeypatch.setattr(settings, "MAX_INDEXED_TOTAL_BYTES", 1)
    failed = await client.post(f"/repositories/{repository_id}/ingest")
    assert failed.status_code == 422

    old_result = await client.get(
        f"/repositories/{repository_id}/code/search", params={"q": "stable_handler"}
    )
    new_result = await client.get(
        f"/repositories/{repository_id}/code/search", params={"q": "replacement_handler"}
    )
    status = await client.get(f"/repositories/{repository_id}/index")
    assert old_result.json()["results"]
    assert new_result.json()["results"] == []
    assert status.json()["ingestion_status"] == "failed"


@pytest.mark.asyncio
async def test_jev_code_rerank_requires_source_upload_opt_in(
    client: AsyncClient, tmp_path, monkeypatch
):
    repo_path = tmp_path / "repo"
    monkeypatch.setattr(settings, "REPO_ALLOWED_ROOTS", str(tmp_path))
    git_repo = _git_repo(repo_path)
    (repo_path / "a.py").write_text(
        "def account_lookup(): return 'account'\n", encoding="utf-8"
    )
    (repo_path / "b.py").write_text(
        "def account_storage(): return 'account'\n", encoding="utf-8"
    )
    git_repo.index.add(["a.py", "b.py"])
    git_repo.index.commit("Add account helpers")
    created = await client.post(
        "/repositories", json={"name": "jev-opt-in", "local_path": str(repo_path)}
    )
    repository_id = created.json()["id"]
    indexed = await client.post(f"/repositories/{repository_id}/ingest")
    assert indexed.status_code == 200, indexed.text

    sent_items = []

    async def fake_jev(query, items):
        sent_items.extend(items)
        return [1.0 if "b.py" in item["content"] else 0.0 for item in items]

    monkeypatch.setattr("app.services.repository_index.score_relevance", fake_jev)
    monkeypatch.setattr(settings, "JEV_ALLOW_SOURCE_UPLOAD", True)
    monkeypatch.setattr(settings, "TYPESAFE_API_KEY", "test-only-configured-placeholder")
    reranked = await client.get(
        f"/repositories/{repository_id}/code/search",
        params={"q": "account", "profile": "jev", "limit": 2},
    )
    assert reranked.status_code == 200, reranked.text
    assert reranked.json()["retrieval"]["jev_used"] is True
    assert reranked.json()["retrieval"]["jev_status"] == "ranked"
    assert reranked.json()["results"][0]["file_path"] == "b.py"
    assert len(sent_items) == 2
    assert all(len(item["content"]) <= 1800 for item in sent_items)

    async def jev_must_not_run(query, items):
        raise AssertionError("Jev must not receive code when policy is disabled")

    monkeypatch.setattr(settings, "JEV_ALLOW_SOURCE_UPLOAD", False)
    monkeypatch.setattr("app.services.repository_index.score_relevance", jev_must_not_run)
    local = await client.get(
        f"/repositories/{repository_id}/code/search",
        params={"q": "account", "profile": "jev", "limit": 2},
    )
    assert local.status_code == 200, local.text
    assert local.json()["retrieval"]["jev_used"] is False
    assert local.json()["retrieval"]["jev_status"] == "disabled_by_policy"
