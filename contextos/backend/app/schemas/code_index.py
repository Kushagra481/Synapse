"""Typed API contracts for repository indexing and code search."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class IngestionResponse(BaseModel):
    repository_id: str
    ingestion_status: Literal["completed"]
    indexed_commit_sha: str | None
    file_count: int
    symbol_count: int
    skipped_count: int
    added_count: int
    changed_count: int
    removed_count: int
    unchanged_count: int
    working_tree_dirty: bool
    indexed_at: datetime


class RepositoryIndexStatus(BaseModel):
    repository_id: str
    ingestion_status: str
    ingestion_error: str | None = None
    indexed_commit_sha: str | None = None
    indexed_at: datetime | None = None
    file_count: int = 0
    symbol_count: int = 0
    skipped_count: int = 0
    working_tree_dirty: bool = False


class CodeSearchResult(BaseModel):
    file_path: str
    language: str | None
    symbol: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    source_text: str
    source_truncated: bool
    indexed_commit_sha: str | None
    freshness: str
    relevance_score: float
    relevance_reason: str


class CodeSearchResponse(BaseModel):
    query: str
    results: list[CodeSearchResult]
    total: int
    index: RepositoryIndexStatus | None = None
