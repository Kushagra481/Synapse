from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.core.database import get_db
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate, RepositoryListResponse, RepositoryResponse, RepositoryUpdate
from app.schemas.code_index import CodeSearchResponse, IngestionResponse, RepositoryIndexStatus
from app.services.repository_index import (
    RepositoryIndexError,
    get_index_status,
    index_repository,
    search_code,
)
from app.services.graph_index import delete_repository_graph
from app.models.code_index import CodeImport, CodeSymbol, IndexedFile, RepositoryIndexState
from app.models.evaluation import RetrievalEvalCase, RetrievalEvalRun

router = APIRouter()


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(
    payload: RepositoryCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    owner_subject = getattr(request.state, "principal", "local")
    existing = await db.scalar(
        select(Repository).where(
            Repository.local_path == payload.local_path,
            Repository.owner_subject == owner_subject,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="A repository with this URL or path already exists")
    repo = Repository(**payload.model_dump(), owner_subject=owner_subject)
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


@router.get("", response_model=RepositoryListResponse)
async def list_repositories(
    request: Request, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    limit = min(max(limit, 1), 200)
    owner_subject = getattr(request.state, "principal", "local")
    owner_filter = Repository.owner_subject == owner_subject
    total = await db.scalar(
        select(__import__("sqlalchemy").func.count())
        .select_from(Repository)
        .where(owner_filter)
    ) or 0
    rows = await db.scalars(
        select(Repository)
        .where(owner_filter)
        .order_by(Repository.updated_at.desc())
        .offset(max(skip, 0))
        .limit(limit)
    )
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
    graph_result = await delete_repository_graph(repo_id)
    if graph_result in {"failed", "unavailable"}:
        raise HTTPException(
            status_code=503,
            detail="Repository graph could not be verified for deletion; relational records were kept.",
        )
    await db.execute(delete(CodeImport).where(CodeImport.repository_id == repo_id))
    await db.execute(delete(CodeSymbol).where(CodeSymbol.repository_id == repo_id))
    await db.execute(delete(IndexedFile).where(IndexedFile.repository_id == repo_id))
    await db.execute(delete(RetrievalEvalCase).where(RetrievalEvalCase.repository_id == repo_id))
    await db.execute(delete(RetrievalEvalRun).where(RetrievalEvalRun.repository_id == repo_id))
    index_state = await db.get(RepositoryIndexState, repo_id)
    if index_state:
        await db.delete(index_state)
    await db.delete(repo)
    await db.commit()
    return None


@router.post("/{repo_id}/ingest", response_model=IngestionResponse)
async def ingest_repository(
    repo_id: str,
    full_reindex: bool = Query(False, description="Re-parse every eligible file, even when its hash is unchanged."),
    db: AsyncSession = Depends(get_db),
):
    repository = await db.get(Repository, repo_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    try:
        result = await index_repository(db, repository, force=full_reindex)
    except RepositoryIndexError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ingestion_status": "completed", **result}


@router.get("/{repo_id}/index", response_model=RepositoryIndexStatus)
async def repository_index_status(repo_id: str, db: AsyncSession = Depends(get_db)):
    repository = await db.get(Repository, repo_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    state = await get_index_status(db, repo_id)
    return {
        "repository_id": repo_id,
        "ingestion_status": repository.ingestion_status.value,
        "ingestion_error": repository.ingestion_error,
        **(state or {}),
    }


@router.get("/{repo_id}/code/search", response_model=CodeSearchResponse)
async def search_repository_code(
    repo_id: str,
    q: str = Query(..., min_length=2, max_length=300),
    path: str | None = Query(None, max_length=1024),
    limit: int = Query(20, ge=1, le=50),
    profile: Literal["lexical", "hybrid", "jev"] = Query("hybrid"),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Repository, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")
    return await search_code(
        db, repo_id, q, limit=limit, path_filter=path, ranking_profile=profile
    )
