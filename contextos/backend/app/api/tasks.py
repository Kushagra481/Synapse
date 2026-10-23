from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.repository import Repository
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskListResponse, TaskResponse, TaskUpdate
from app.api.dependencies import require_repository_editor

router = APIRouter()


async def _require_repo(db: AsyncSession, repo_id: str):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")


@router.post(
    "/{repo_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_repository_editor)],
)
async def create_task(repo_id: str, payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    await _require_repo(db, repo_id)
    row = Task(repository_id=repo_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{repo_id}/tasks", response_model=TaskListResponse)
async def list_tasks(repo_id: str, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    await _require_repo(db, repo_id)
    limit = min(max(limit, 1), 200)
    total = await db.scalar(select(func.count()).select_from(Task).where(Task.repository_id == repo_id)) or 0
    rows = await db.scalars(select(Task).where(Task.repository_id == repo_id).order_by(Task.updated_at.desc()).offset(max(skip, 0)).limit(limit))
    return {"items": rows.all(), "total": total}


@router.patch(
    "/{repo_id}/tasks/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_repository_editor)],
)
async def update_task(repo_id: str, task_id: str, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Task, task_id)
    if not row or row.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete(
    "/{repo_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_repository_editor)],
)
async def delete_task(repo_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Task, task_id)
    if not row or row.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(row)
    await db.commit()
    return None
