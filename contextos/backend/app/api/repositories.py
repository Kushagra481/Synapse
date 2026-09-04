from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.repository import Repository, IngestionStatus
from app.schemas.repository import RepositoryCreate, RepositoryResponse, RepositoryListResponse

router = APIRouter()

@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(repo_in: RepositoryCreate, db: AsyncSession = Depends(get_db)):
    # Check if repo exists by local_path
    result = await db.execute(select(Repository).where(Repository.local_path == repo_in.local_path))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Repository with this local path already exists")
        
    repo = Repository(
        name=repo_in.name,
        local_path=repo_in.local_path,
        description=repo_in.description,
        default_branch=repo_in.default_branch,
        language=repo_in.language
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo

@router.get("", response_model=RepositoryListResponse)
async def list_repositories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repository))
    repos = result.scalars().all()
    return {"items": repos, "total": len(repos)}

@router.post("/{repo_id}/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_repository(repo_id: str, db: AsyncSession = Depends(get_db)):
    # This will later trigger a background task for ingestion
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalars().first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    repo.ingestion_status = IngestionStatus.RUNNING
    await db.commit()
    
    # TODO: Trigger background ingestion here
    
    return {"message": "Ingestion started", "status": "running"}
