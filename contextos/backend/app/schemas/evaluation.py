"""Typed evaluation benchmark API contracts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvalCaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    query: str = Field(min_length=2, max_length=3000)
    expected_files: list[str] = Field(default_factory=list, max_length=50)
    expected_symbols: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True


class EvalCaseResponse(EvalCaseCreate):
    id: str
    repository_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvalRunCreate(BaseModel):
    profiles: list[Literal["lexical", "hybrid", "jev"]] = Field(
        default_factory=lambda: ["lexical", "hybrid"], min_length=1, max_length=3
    )
    top_k: int = Field(default=10, ge=1, le=50)


class EvalRunResponse(BaseModel):
    id: str
    repository_id: str
    index_commit_sha: str | None
    case_count: int
    top_k: int
    profiles: list[str]
    metrics: dict
    case_results: list[dict]
    latency_ms: float
    estimated_tokens: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
