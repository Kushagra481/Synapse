"""Contracts for provenance-bearing project memory facts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemoryFactCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    content: str = Field(min_length=2, max_length=12000)
    fact_type: str = Field(default="project", min_length=2, max_length=64)
    topic_key: str = Field(min_length=2, max_length=255)
    source_type: Literal["manual", "session", "repository_file", "decision", "task"] = "manual"
    source_ref: str | None = Field(default=None, max_length=2000)
    evidence_quote: str | None = Field(default=None, max_length=2000)
    source_file_path: str | None = Field(default=None, max_length=1024)
    source_commit_sha: str | None = Field(default=None, max_length=40)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verified: bool = False
    supersedes_fact_id: str | None = Field(default=None, max_length=36)


class MemoryFactResponse(BaseModel):
    id: str
    repository_id: str
    title: str
    content: str
    fact_type: str
    topic_key: str
    source_type: str
    source_ref: str | None
    evidence_quote: str | None
    source_file_path: str | None
    source_commit_sha: str | None
    source_content_sha256: str | None
    confidence: float
    verified: bool
    is_stale: bool
    conflict_status: str
    conflicts_with: list[str]
    superseded_by_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryFactCreateResponse(BaseModel):
    fact: MemoryFactResponse
    conflicts: list[str] = Field(default_factory=list)
