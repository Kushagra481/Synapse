"""Capture metadata-only Git start/end snapshots for durable agent handoffs."""
from __future__ import annotations

from typing import Any

from git.exc import GitCommandError, InvalidGitRepositoryError

from app.services.repository_index import RepositoryIndexError, validate_repository_path


def capture_git_snapshot(local_path: str) -> dict[str, Any]:
    """Return branch, commit, dirty state, and changed path names without reading diffs."""
    try:
        _, git_repo = validate_repository_path(local_path)
    except RepositoryIndexError:
        return {
            "status": "outside_allowlist_or_not_git",
            "branch": None,
            "commit_sha": None,
            "changed_files": [],
            "working_tree_dirty": None,
        }

    try:
        try:
            branch = git_repo.active_branch.name
        except TypeError:
            branch = None
        commit_sha = git_repo.head.commit.hexsha if git_repo.head.is_valid() else None
        changed = set(git_repo.git.diff("--name-only", "-z", "HEAD").split("\0")) if commit_sha else set()
        changed.update(git_repo.untracked_files)
        changed.discard("")
        ordered = sorted(path.replace("\\", "/") for path in changed)
        truncated = len(ordered) > 1000
        return {
            "status": "captured_truncated" if truncated else "captured",
            "branch": branch,
            "commit_sha": commit_sha,
            "changed_files": ordered[:1000],
            "working_tree_dirty": git_repo.is_dirty(untracked_files=True),
        }
    except (GitCommandError, InvalidGitRepositoryError, OSError, ValueError):
        return {
            "status": "capture_failed",
            "branch": None,
            "commit_sha": None,
            "changed_files": [],
            "working_tree_dirty": None,
        }
