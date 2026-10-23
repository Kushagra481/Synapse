from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    id: str
    actor: str
    action: str
    project_id: str | None
    resource_id: str | None
    outcome: str
    status_code: int
    duration_ms: float
    details: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
