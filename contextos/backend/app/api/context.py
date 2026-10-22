from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.repository import Repository
from app.models.memory import ProjectMemory
from app.models.task import Task
from app.models.decision import Decision
from app.models.session import Session
from app.services.context_pack import build_context_pack

router = APIRouter()


class ContextRequest(BaseModel):
    task: str = Field("", max_length=6000)
    max_tokens: int = Field(4000, ge=128, le=32000)


async def _build(repo_id: str, task: str, max_tokens: int, db: AsyncSession):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    memory = await db.scalar(select(ProjectMemory).where(ProjectMemory.repository_id == repo_id))
    tasks = (await db.scalars(select(Task).where(Task.repository_id == repo_id).order_by(Task.updated_at.desc()).limit(50))).all()
    decisions = (await db.scalars(select(Decision).where(Decision.repository_id == repo_id).order_by(Decision.updated_at.desc()).limit(50))).all()
    sessions = (await db.scalars(select(Session).where(Session.repository_id == repo_id).order_by(Session.updated_at.desc()).limit(10))).all()
    return await build_context_pack(repo, memory, tasks, decisions, sessions, task, max_tokens)


@router.get("/{repo_id}/context")
async def get_context(repo_id: str, task: str = Query("", max_length=6000), max_tokens: int = Query(4000, ge=128, le=32000), db: AsyncSession = Depends(get_db)):
    return await _build(repo_id, task, max_tokens, db)


@router.post("/{repo_id}/context")
async def create_context(repo_id: str, payload: ContextRequest, db: AsyncSession = Depends(get_db)):
    return await _build(repo_id, payload.task, payload.max_tokens, db)
