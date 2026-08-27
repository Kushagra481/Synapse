"""Pydantic schemas for Repository API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.repository import IngestionStatus


# ── Request Schemas ────────────────────────────────────────────────────────────

class RepositoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Repository display name")
    local_path: str = Field(..., description="Absolute path to the local Git repository")
    description: Optional[str] = Field(None, description="Brief repository description")
    default_branch: str = Field("main", description="Default Git branch")
    language: Optional[str] = Field(None, description="Primary programming language")


class RepositoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ── Response Schemas ───────────────────────────────────────────────────────────

class RepositoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: Optional[str]
    local_path: str
    default_branch: str
    language: Optional[str]
    ingestion_status: IngestionStatus
    last_ingested_at: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RepositoryListResponse(BaseModel):
    items: list[RepositoryResponse]
    total: int
