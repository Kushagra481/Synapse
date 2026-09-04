from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.decision import DecisionStatus, DecisionCategory

class DecisionBase(BaseModel):
    title: str = Field(..., max_length=512)
    context: Optional[str] = None
    decision: str
    rationale: Optional[str] = None
    consequences: Optional[str] = None
    status: DecisionStatus = DecisionStatus.ACCEPTED
    category: DecisionCategory = DecisionCategory.OTHER
    session_id: Optional[str] = None

class DecisionCreate(DecisionBase):
    repository_id: str = Field(..., max_length=36)

class DecisionUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=512)
    context: Optional[str] = None
    decision: Optional[str] = None
    rationale: Optional[str] = None
    consequences: Optional[str] = None
    status: Optional[DecisionStatus] = None
    category: Optional[DecisionCategory] = None
    session_id: Optional[str] = None

class DecisionResponse(DecisionBase):
    id: str
    repository_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
