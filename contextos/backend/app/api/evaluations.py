"""Create benchmark cases and run reproducible retrieval comparisons."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.evaluation import RetrievalEvalCase, RetrievalEvalRun
from app.models.repository import Repository
from app.schemas.evaluation import EvalCaseCreate, EvalCaseResponse, EvalRunCreate, EvalRunResponse
from app.services.evaluation import run_retrieval_benchmark

router = APIRouter()


async def _require_repository(db: AsyncSession, repository_id: str) -> None:
    if not await db.get(Repository, repository_id):
        raise HTTPException(status_code=404, detail="Repository not found")


@router.post(
    "/{repo_id}/evaluations/cases",
    response_model=EvalCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case(
    repo_id: str, payload: EvalCaseCreate, db: AsyncSession = Depends(get_db)
):
    await _require_repository(db, repo_id)
    case = RetrievalEvalCase(repository_id=repo_id, **payload.model_dump())
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return case


@router.get("/{repo_id}/evaluations/cases")
async def list_cases(
    repo_id: str, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    await _require_repository(db, repo_id)
    limit = min(max(limit, 1), 200)
    total = await db.scalar(
        select(func.count()).select_from(RetrievalEvalCase).where(
            RetrievalEvalCase.repository_id == repo_id
        )
    ) or 0
    rows = await db.scalars(
        select(RetrievalEvalCase)
        .where(RetrievalEvalCase.repository_id == repo_id)
        .order_by(RetrievalEvalCase.created_at.asc())
        .offset(max(skip, 0))
        .limit(limit)
    )
    return {"items": rows.all(), "total": total}


@router.delete("/{repo_id}/evaluations/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    repo_id: str, case_id: str, db: AsyncSession = Depends(get_db)
):
    case = await db.get(RetrievalEvalCase, case_id)
    if not case or case.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Evaluation case not found")
    await db.delete(case)
    await db.commit()
    return None


@router.post(
    "/{repo_id}/evaluations/runs",
    response_model=EvalRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_run(
    repo_id: str, payload: EvalRunCreate, db: AsyncSession = Depends(get_db)
):
    await _require_repository(db, repo_id)
    try:
        return await run_retrieval_benchmark(
            db, repo_id, payload.profiles, payload.top_k
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{repo_id}/evaluations/runs")
async def list_runs(
    repo_id: str, skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)
):
    await _require_repository(db, repo_id)
    limit = min(max(limit, 1), 200)
    total = await db.scalar(
        select(func.count()).select_from(RetrievalEvalRun).where(
            RetrievalEvalRun.repository_id == repo_id
        )
    ) or 0
    rows = await db.scalars(
        select(RetrievalEvalRun)
        .where(RetrievalEvalRun.repository_id == repo_id)
        .order_by(RetrievalEvalRun.created_at.desc())
        .offset(max(skip, 0))
        .limit(limit)
    )
    return {"items": rows.all(), "total": total}


@router.get("/{repo_id}/evaluations/runs/{run_id}", response_model=EvalRunResponse)
async def get_run(repo_id: str, run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(RetrievalEvalRun, run_id)
    if not run or run.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run
