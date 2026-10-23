from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict, Field

class ProjectMemoryBase(BaseModel):
    project_goal: Optional[str] = None
    architecture_summary: Optional[str] = None
    tech_stack: Optional[List[Dict[str, Any]]] = None
    current_task: Optional[str] = None
    active_tasks: Optional[List[Dict[str, Any]]] = None
    completed_tasks: Optional[List[Dict[str, Any]]] = None
    blocked_tasks: Optional[List[Dict[str, Any]]] = None
    next_steps: Optional[List[Dict[str, Any]]] = None
    known_bugs: Optional[List[Dict[str, Any]]] = None
    open_questions: Optional[List[Dict[str, Any]]] = None
    recent_changes: Optional[List[Dict[str, Any]]] = None
    recently_modified_files: Optional[List[Dict[str, Any]]] = None
    recent_commits: Optional[List[Dict[str, Any]]] = None
    conversation_summaries: Optional[List[Dict[str, Any]]] = None
    custom_notes: Optional[str] = None

class ProjectMemoryCreate(ProjectMemoryBase):
    repository_id: str = Field(..., max_length=36)

class ProjectMemoryUpdate(ProjectMemoryBase):
    pass

class ProjectMemoryResponse(ProjectMemoryBase):
    id: Optional[str] = None
    repository_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class BugBase(BaseModel):
    title: str = Field(..., max_length=512)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=1024)
    severity: str = "medium"
    is_resolved: bool = False
    resolution: Optional[str] = None
    session_id: Optional[str] = None

class BugCreate(BugBase):
    repository_id: str = Field(..., max_length=36)

class BugUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=512)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=1024)
    severity: Optional[str] = None
    is_resolved: Optional[bool] = None
    resolution: Optional[str] = None
    session_id: Optional[str] = None

class BugResponse(BugBase):
    id: str
    repository_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
