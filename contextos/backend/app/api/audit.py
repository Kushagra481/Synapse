from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit import AuditEvent
from app.models.repository import Repository
from app.schemas.audit import AuditEventResponse

router = APIRouter()


@router.get("/{repo_id}/audit-events", response_model=list[AuditEventResponse])
async def list_audit_events(
    repo_id: str,
    skip: int = Query(0, ge=0, le=10000),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")
    rows = await db.scalars(
        select(AuditEvent)
        .where(AuditEvent.project_id == repo_id)
        .order_by(AuditEvent.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return rows.all()
