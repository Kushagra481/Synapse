from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate, RepositoryListResponse, RepositoryResponse, RepositoryUpdate

router = APIRouter()


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(payload: RepositoryCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Repository).where(Repository.local_path == payload.local_path))
    if existing:
        raise HTTPException(status_code=409, detail="A repository with this URL or path already exists")
    repo = Repository(**payload.model_dump())
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


@router.get("", response_model=RepositoryListResponse)
async def list_repositories(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    limit = min(max(limit, 1), 200)
    total = await db.scalar(select(__import__('sqlalchemy').func.count()).select_from(Repository)) or 0
    rows = await db.scalars(select(Repository).order_by(Repository.updated_at.desc()).offset(max(skip, 0)).limit(limit))
    return {"items": rows.all(), "total": total}


@router.get("/{repo_id}", response_model=RepositoryResponse)
async def get_repository(repo_id: str, db: AsyncSession = Depends(get_db)):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.patch("/{repo_id}", response_model=RepositoryResponse)
async def update_repository(repo_id: str, payload: RepositoryUpdate, db: AsyncSession = Depends(get_db)):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(repo, key, value)
    await db.commit()
    await db.refresh(repo)
    return repo


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(repo_id: str, db: AsyncSession = Depends(get_db)):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    await db.delete(repo)
    await db.commit()
    return None


@router.post("/{repo_id}/ingest", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def ingest_repository(repo_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")
    raise HTTPException(status_code=501, detail="Automatic source ingestion is not available yet. Context is managed through sessions, tasks, decisions, and memory.")
