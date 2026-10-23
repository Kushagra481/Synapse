"""Typed API contracts for repository indexing and code search."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IngestionResponse(BaseModel):
    repository_id: str
    ingestion_status: Literal["completed"]
    indexed_commit_sha: str | None
    file_count: int
    symbol_count: int
    import_count: int
    skipped_count: int
    added_count: int
    changed_count: int
    removed_count: int
    unchanged_count: int
    working_tree_dirty: bool
    embedding_status: str
    embedding_model: str | None
    embedding_count: int
    graph_sync_status: str
    indexed_at: datetime


class RepositoryIndexStatus(BaseModel):
    repository_id: str
    ingestion_status: str
    ingestion_error: str | None = None
    indexed_commit_sha: str | None = None
    indexed_at: datetime | None = None
    file_count: int = 0
    symbol_count: int = 0
    import_count: int = 0
    skipped_count: int = 0
    working_tree_dirty: bool = False
    embedding_status: str = "disabled"
    embedding_model: str | None = None
    embedding_count: int = 0
    graph_sync_status: str = "pending"


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
    ranking_signals: dict[str, float]
    current_commit_sha: str | None = None


class CodeSearchResponse(BaseModel):
    query: str
    results: list[CodeSearchResult]
    total: int
    index: RepositoryIndexStatus | None = None
    retrieval: dict[str, object] = Field(default_factory=dict)
