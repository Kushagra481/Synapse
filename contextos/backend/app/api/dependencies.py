"""Shared access checks for repository-scoped routers."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import auth_is_configured, verify_token
from app.core.config import settings
from app.core.database import get_db
from app.models.repository import Repository
from app.models.membership import ProjectMembership

bearer_scheme = HTTPBearer(auto_error=False)


async def require_bearer_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if settings.APP_ENV == "test":
        return "test"
    if not settings.AUTH_ENABLED:
        return "local"
    if not auth_is_configured():
        raise HTTPException(
            status_code=503,
            detail="Authentication is enabled but not configured. Set the workspace auth secrets.",
        )
    principal = verify_token(credentials.credentials) if credentials else None
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


async def require_repository_access(
    request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    if settings.APP_ENV == "test":
        return
    repository_id = request.path_params.get("repo_id")
    if not repository_id:
        return
    repository = await db.get(Repository, repository_id)
    principal = getattr(request.state, "principal", None)
    if not repository:
        # Do not disclose whether another operator's repository exists.
        raise HTTPException(status_code=404, detail="Repository not found")
    if repository.owner_subject == principal:
        request.state.repository_role = "owner"
        return
    membership = await db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.repository_id == repository_id,
            ProjectMembership.user_subject == principal,
        )
    )
    if not membership:
        # Do not disclose whether another operator's repository exists.
        raise HTTPException(status_code=404, detail="Repository not found")
    request.state.repository_role = membership.role


async def require_repository_editor(request: Request) -> None:
    """Allow repository mutations to editors and owners, not viewers."""
    if settings.APP_ENV == "test":
        return
    if getattr(request.state, "repository_role", None) not in {"owner", "editor"}:
        raise HTTPException(status_code=403, detail="Editor access is required.")


async def require_repository_owner(request: Request) -> None:
    """Restrict destructive and membership-management actions to owners."""
    if settings.APP_ENV == "test":
        return
    if getattr(request.state, "repository_role", None) != "owner":
        raise HTTPException(status_code=403, detail="Owner access is required.")
