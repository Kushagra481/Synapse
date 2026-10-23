"""Owner-managed repository membership endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_repository_owner
from app.core.auth import auth_is_configured, configured_users
from app.core.config import settings
from app.core.database import get_db
from app.models.membership import ProjectMembership
from app.models.repository import Repository


router = APIRouter()


class MembershipCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    role: Literal["editor", "viewer"]


class MembershipUpdate(BaseModel):
    role: Literal["editor", "viewer"]


def _require_configured_accounts() -> dict[str, str]:
    if not settings.AUTH_ENABLED or not auth_is_configured():
        raise HTTPException(
            status_code=503,
            detail="Repository sharing requires authentication and configured user accounts.",
        )
    return configured_users()


async def _require_repo(db: AsyncSession, repo_id: str) -> Repository:
    repository = await db.get(Repository, repo_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@router.get("/{repo_id}/members")
async def list_members(
    repo_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    repository = await _require_repo(db, repo_id)
    memberships = await db.scalars(
        select(ProjectMembership)
        .where(ProjectMembership.repository_id == repo_id)
        .order_by(ProjectMembership.user_subject.asc())
    )
    items = [
        {"username": row.user_subject, "role": row.role}
        for row in memberships.all()
    ]
    if not any(row["username"] == repository.owner_subject for row in items):
        items.insert(0, {"username": repository.owner_subject, "role": "owner"})
    principal = getattr(request.state, "principal", None)
    current_role = (
        "owner"
        if principal == repository.owner_subject
        else next((row["role"] for row in items if row["username"] == principal), None)
    )
    return {"items": items, "total": len(items), "current_role": current_role}


@router.post(
    "/{repo_id}/members",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_repository_owner)],
)
async def add_member(
    repo_id: str, payload: MembershipCreate, db: AsyncSession = Depends(get_db)
):
    repository = await _require_repo(db, repo_id)
    users = _require_configured_accounts()
    username = payload.username.strip()
    if not username or username not in users:
        raise HTTPException(
            status_code=422,
            detail="Choose a username from the configured workspace accounts.",
        )
    if username == repository.owner_subject:
        raise HTTPException(status_code=409, detail="The repository owner is already a member.")
    existing = await db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.repository_id == repo_id,
            ProjectMembership.user_subject == username,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="That account is already a member.")
    membership = ProjectMembership(
        repository_id=repo_id, user_subject=username, role=payload.role
    )
    db.add(membership)
    await db.commit()
    return {"username": username, "role": payload.role}


@router.patch(
    "/{repo_id}/members/{username}",
    dependencies=[Depends(require_repository_owner)],
)
async def update_member(
    repo_id: str,
    username: str,
    payload: MembershipUpdate,
    db: AsyncSession = Depends(get_db),
):
    repository = await _require_repo(db, repo_id)
    if username == repository.owner_subject:
        raise HTTPException(status_code=409, detail="The repository owner's role cannot be changed.")
    membership = await db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.repository_id == repo_id,
            ProjectMembership.user_subject == username,
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found.")
    membership.role = payload.role
    await db.commit()
    return {"username": username, "role": payload.role}


@router.delete(
    "/{repo_id}/members/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_repository_owner)],
)
async def remove_member(
    repo_id: str, username: str, db: AsyncSession = Depends(get_db)
):
    repository = await _require_repo(db, repo_id)
    if username == repository.owner_subject:
        raise HTTPException(status_code=409, detail="The repository owner cannot be removed.")
    membership = await db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.repository_id == repo_id,
            ProjectMembership.user_subject == username,
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found.")
    await db.delete(membership)
    await db.commit()
    return None
