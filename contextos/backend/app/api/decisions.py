from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.repository import Repository
from app.models.decision import Decision
from app.schemas.decision import DecisionCreate, DecisionResponse, DecisionUpdate

router = APIRouter()


@router.post("/{repo_id}/decisions", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
async def create_decision(repo_id: str, payload: DecisionCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")
    row = Decision(repository_id=repo_id, **payload.model_dump(exclude={"repository_id"}))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{repo_id}/decisions")
async def list_decisions(repo_id: str, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")
    limit = min(max(limit, 1), 200)
    total = await db.scalar(select(func.count()).select_from(Decision).where(Decision.repository_id == repo_id)) or 0
    rows = await db.scalars(select(Decision).where(Decision.repository_id == repo_id).order_by(Decision.updated_at.desc()).offset(max(skip, 0)).limit(limit))
    return {"items": rows.all(), "total": total}


@router.patch("/{repo_id}/decisions/{decision_id}", response_model=DecisionResponse)
async def update_decision(repo_id: str, decision_id: str, payload: DecisionUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Decision, decision_id)
    if not row or row.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Decision not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{repo_id}/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_decision(repo_id: str, decision_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Decision, decision_id)
    if not row or row.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Decision not found")
    await db.delete(row)
    await db.commit()
    return None
