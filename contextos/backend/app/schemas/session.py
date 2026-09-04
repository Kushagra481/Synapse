from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict, Field
from app.models.session import SessionStatus

class SessionBase(BaseModel):
    llm_provider: str = Field(..., max_length=64)
    llm_model: str = Field(..., max_length=128)
    developer_name: Optional[str] = Field(None, max_length=255)
    status: SessionStatus = SessionStatus.ACTIVE
    objective: Optional[str] = None
    summary: Optional[str] = None
    conversation_summary: Optional[str] = None
    files_modified: Optional[List[Any]] = None
    decisions_made: Optional[List[Any]] = None
    tasks_completed: Optional[List[Any]] = None
    bugs_found: Optional[List[Any]] = None
    open_questions: Optional[List[Any]] = None
    next_steps: Optional[List[Any]] = None

class SessionCreate(SessionBase):
    repository_id: str = Field(..., max_length=36)

class SessionUpdate(BaseModel):
    llm_provider: Optional[str] = Field(None, max_length=64)
    llm_model: Optional[str] = Field(None, max_length=128)
    developer_name: Optional[str] = Field(None, max_length=255)
    status: Optional[SessionStatus] = None
    objective: Optional[str] = None
    summary: Optional[str] = None
    conversation_summary: Optional[str] = None
    files_modified: Optional[List[Any]] = None
    decisions_made: Optional[List[Any]] = None
    tasks_completed: Optional[List[Any]] = None
    bugs_found: Optional[List[Any]] = None
    open_questions: Optional[List[Any]] = None
    next_steps: Optional[List[Any]] = None

class SessionResponse(SessionBase):
    id: str
    repository_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationBase(BaseModel):
    summary: str
    decisions: Optional[List[Any]] = None
    task_updates: Optional[List[Any]] = None
    files_modified: Optional[List[Any]] = None
    bugs_discovered: Optional[List[Any]] = None
    unresolved_questions: Optional[List[Any]] = None
    next_actions: Optional[List[Any]] = None
    raw_content: Optional[str] = None

class ConversationCreate(ConversationBase):
    session_id: str = Field(..., max_length=36)
    repository_id: str = Field(..., max_length=36)

class ConversationUpdate(BaseModel):
    summary: Optional[str] = None
    decisions: Optional[List[Any]] = None
    task_updates: Optional[List[Any]] = None
    files_modified: Optional[List[Any]] = None
    bugs_discovered: Optional[List[Any]] = None
    unresolved_questions: Optional[List[Any]] = None
    next_actions: Optional[List[Any]] = None
    raw_content: Optional[str] = None

class ConversationResponse(ConversationBase):
    id: str
    session_id: str
    repository_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
