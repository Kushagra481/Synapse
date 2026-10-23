from datetime import datetime, timezone
from pathlib import PurePosixPath
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.memory import ProjectMemory, Bug
from app.models.repository import Repository
from app.schemas.memory import ProjectMemoryCreate, ProjectMemoryResponse, ProjectMemoryUpdate, BugCreate, BugUpdate, BugResponse
from app.models.memory_fact import ProjectMemoryFact
from app.models.code_index import IndexedFile, RepositoryIndexState
from app.schemas.memory_fact import MemoryFactCreate, MemoryFactCreateResponse, MemoryFactResponse

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


@router.get("/{repo_id}/memory/facts", response_model=list[MemoryFactResponse])
async def list_memory_facts(
    repo_id: str,
    q: str | None = Query(None, max_length=300),
    fact_type: str | None = Query(None, max_length=64),
    source_type: str | None = Query(None, max_length=32),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    include_stale: bool = False,
    db: AsyncSession = Depends(get_db),
):
    await _repo(db, repo_id)
    statement = select(ProjectMemoryFact).where(
        ProjectMemoryFact.repository_id == repo_id,
        ProjectMemoryFact.deleted_at.is_(None),
        ProjectMemoryFact.confidence >= min_confidence,
    )
    if not include_stale:
        statement = statement.where(
            ProjectMemoryFact.is_stale.is_(False),
            ProjectMemoryFact.conflict_status == "clear",
            ProjectMemoryFact.superseded_by_id.is_(None),
        )
    if fact_type:
        statement = statement.where(ProjectMemoryFact.fact_type == fact_type)
    if source_type:
        statement = statement.where(ProjectMemoryFact.source_type == source_type)
    if q:
        pattern = f"%{q}%"
        statement = statement.where(
            or_(
                ProjectMemoryFact.title.ilike(pattern),
                ProjectMemoryFact.content.ilike(pattern),
                ProjectMemoryFact.topic_key.ilike(pattern),
            )
        )
    rows = await db.scalars(statement.order_by(ProjectMemoryFact.updated_at.desc()).limit(200))
    return rows.all()


@router.post(
    "/{repo_id}/memory/facts",
    response_model=MemoryFactCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_memory_fact(
    repo_id: str, payload: MemoryFactCreate, db: AsyncSession = Depends(get_db)
):
    await _repo(db, repo_id)
    topic_key = payload.topic_key.strip().lower()
    if not topic_key:
        raise HTTPException(status_code=422, detail="A stable topic key is required.")
    source_file = None
    source_sha = None
    source_commit = payload.source_commit_sha
    if payload.source_type == "repository_file":
        if not payload.source_file_path:
            raise HTTPException(
                status_code=422,
                detail="Repository-file facts require a relative source file path.",
            )
        normalized_path = payload.source_file_path.replace("\\", "/").strip()
        parsed_path = PurePosixPath(normalized_path)
        if parsed_path.is_absolute() or any(
            part in {"", ".", ".."} for part in parsed_path.parts
        ):
            raise HTTPException(status_code=422, detail="Source file path must be repository-relative.")
        source_file = await db.scalar(
            select(IndexedFile).where(
                IndexedFile.repository_id == repo_id,
                IndexedFile.relative_path == parsed_path.as_posix(),
            )
        )
        index_state = await db.get(RepositoryIndexState, repo_id)
        if not source_file or not index_state or not index_state.indexed_commit_sha:
            raise HTTPException(status_code=422, detail="Index the cited file before recording this fact.")
        if source_commit and source_commit != source_file.indexed_commit_sha:
            raise HTTPException(
                status_code=409,
                detail="The cited commit does not match the indexed source snapshot.",
            )
        source_commit = source_file.indexed_commit_sha
        source_sha = source_file.content_sha256
    elif payload.source_file_path or payload.source_commit_sha:
        raise HTTPException(
            status_code=422,
            detail="File path and commit provenance are only valid for repository-file facts.",
        )

    prior = (
        await db.scalars(
            select(ProjectMemoryFact).where(
                ProjectMemoryFact.repository_id == repo_id,
                ProjectMemoryFact.topic_key == topic_key,
                ProjectMemoryFact.deleted_at.is_(None),
                ProjectMemoryFact.superseded_by_id.is_(None),
            )
        )
    ).all()
    superseded = None
    if payload.supersedes_fact_id:
        superseded = await db.get(ProjectMemoryFact, payload.supersedes_fact_id)
        if (
            not superseded
            or superseded.repository_id != repo_id
            or superseded.deleted_at is not None
            or superseded.superseded_by_id is not None
        ):
            raise HTTPException(status_code=404, detail="Active fact to supersede was not found.")
        if superseded.topic_key != topic_key:
            raise HTTPException(status_code=422, detail="A replacement fact must use the same topic key.")
        prior = [fact for fact in prior if fact.id != superseded.id]

    fact = ProjectMemoryFact(
        repository_id=repo_id,
        title=payload.title.strip(),
        content=payload.content.strip(),
        fact_type=payload.fact_type.strip(),
        topic_key=topic_key,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        evidence_quote=payload.evidence_quote,
        source_file_path=source_file.relative_path if source_file else None,
        source_commit_sha=source_commit,
        source_content_sha256=source_sha,
        confidence=payload.confidence,
        verified=payload.verified,
        conflict_status="needs_review" if prior else "clear",
        conflicts_with=[row.id for row in prior],
    )
    db.add(fact)
    await db.flush()
    conflict_ids = [row.id for row in prior]
    for previous in prior:
        previous.conflict_status = "needs_review"
        previous.conflicts_with = list(set((previous.conflicts_with or []) + [fact.id]))
    if superseded:
        superseded.superseded_by_id = fact.id
        superseded.is_stale = True
        superseded.conflict_status = "superseded"
        superseded.conflicts_with = []
    await db.commit()
    await db.refresh(fact)
    return {"fact": fact, "conflicts": conflict_ids}


@router.delete("/{repo_id}/memory/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_memory_fact(
    repo_id: str, fact_id: str, db: AsyncSession = Depends(get_db)
):
    fact = await db.get(ProjectMemoryFact, fact_id)
    if not fact or fact.repository_id != repo_id or fact.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Memory fact not found")
    conflict_ids = list(fact.conflicts_with or [])
    fact.deleted_at = datetime.now(timezone.utc)
    fact.conflicts_with = []
    for conflict_id in conflict_ids:
        other = await db.get(ProjectMemoryFact, conflict_id)
        if (
            not other
            or other.repository_id != repo_id
            or other.deleted_at is not None
            or fact.id not in (other.conflicts_with or [])
        ):
            continue
        other.conflicts_with = [value for value in other.conflicts_with if value != fact.id]
        if not other.conflicts_with:
            other.conflict_status = "clear"
    await db.commit()
    return None
