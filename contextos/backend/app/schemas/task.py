"""Pydantic schemas for Task API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.task import TaskStatus, TaskPriority


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.MEDIUM
    blocked_reason: Optional[str] = None
    session_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    blocked_reason: Optional[str] = None
    completion_notes: Optional[str] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    model_config = {"from_attributes": True}

    id: str
    repository_id: str
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: TaskPriority
    blocked_reason: Optional[str]
    completion_notes: Optional[str]
    session_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
