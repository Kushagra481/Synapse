from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.memory import ProjectMemory, Bug
from app.models.repository import Repository
from app.schemas.memory import ProjectMemoryCreate, ProjectMemoryResponse, ProjectMemoryUpdate, BugCreate, BugUpdate, BugResponse

router = APIRouter()


async def _repo(db: AsyncSession, repo_id: str):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")


@router.get("/{repo_id}/memory", response_model=ProjectMemoryResponse)
async def get_memory(repo_id: str, db: AsyncSession = Depends(get_db)):
    await _repo(db, repo_id)
    memory = await db.scalar(select(ProjectMemory).where(ProjectMemory.repository_id == repo_id))
    if not memory:
        memory = ProjectMemory(repository_id=repo_id)
        db.add(memory)
        await db.commit()
        await db.refresh(memory)
    return memory


@router.post("/{repo_id}/memory", response_model=ProjectMemoryResponse, status_code=status.HTTP_200_OK)
async def upsert_memory(repo_id: str, payload: ProjectMemoryCreate, db: AsyncSession = Depends(get_db)):
    await _repo(db, repo_id)
    memory = await db.scalar(select(ProjectMemory).where(ProjectMemory.repository_id == repo_id))
    values = payload.model_dump(exclude={"repository_id"}, exclude_unset=True)
    if memory is None:
        memory = ProjectMemory(repository_id=repo_id, **values)
        db.add(memory)
    else:
        for key, value in values.items():
            setattr(memory, key, value)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.patch("/{repo_id}/memory", response_model=ProjectMemoryResponse)
async def update_memory(repo_id: str, payload: ProjectMemoryUpdate, db: AsyncSession = Depends(get_db)):
    await _repo(db, repo_id)
    memory = await db.scalar(select(ProjectMemory).where(ProjectMemory.repository_id == repo_id))
    if memory is None:
        memory = ProjectMemory(repository_id=repo_id)
        db.add(memory)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(memory, key, value)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.get("/{repo_id}/bugs")
async def list_bugs(repo_id: str, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    await _repo(db, repo_id)
    limit = min(max(limit, 1), 200)
    total = await db.scalar(select(func.count()).select_from(Bug).where(Bug.repository_id == repo_id)) or 0
    rows = await db.scalars(select(Bug).where(Bug.repository_id == repo_id).order_by(Bug.updated_at.desc()).offset(max(skip, 0)).limit(limit))
    return {"items": rows.all(), "total": total}


@router.post("/{repo_id}/bugs", response_model=BugResponse, status_code=status.HTTP_201_CREATED)
async def create_bug(repo_id: str, payload: BugCreate, db: AsyncSession = Depends(get_db)):
    await _repo(db, repo_id)
    bug = Bug(repository_id=repo_id, **payload.model_dump(exclude={"repository_id"}))
    db.add(bug)
    await db.commit()
    await db.refresh(bug)
    return bug


@router.patch("/{repo_id}/bugs/{bug_id}", response_model=BugResponse)
async def update_bug(repo_id: str, bug_id: str, payload: BugUpdate, db: AsyncSession = Depends(get_db)):
    bug = await db.get(Bug, bug_id)
    if not bug or bug.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Bug not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(bug, key, value)
    await db.commit()
    await db.refresh(bug)
    return bug


@router.delete("/{repo_id}/bugs/{bug_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bug(repo_id: str, bug_id: str, db: AsyncSession = Depends(get_db)):
    bug = await db.get(Bug, bug_id)
    if not bug or bug.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Bug not found")
    await db.delete(bug)
    await db.commit()
    return None
