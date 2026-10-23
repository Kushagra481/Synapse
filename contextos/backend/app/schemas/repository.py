"""Request and response schemas for repository records."""
from datetime import datetime
from typing import Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from app.models.repository import IngestionStatus


class RepositoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    local_path: str = Field(..., min_length=1, validation_alias=AliasChoices("local_path", "url"))
    description: Optional[str] = None
    default_branch: str = Field("main", max_length=255)
    language: Optional[str] = Field(None, validation_alias=AliasChoices("language", "primary_language"))


class RepositoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
