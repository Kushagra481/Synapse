"""Shared access checks for repository-scoped routers."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import auth_is_configured, verify_token
from app.core.config import settings
from app.core.database import get_db
from app.models.repository import Repository

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
    if not repository or repository.owner_subject != principal:
        # Do not disclose whether another operator's repository exists.
        raise HTTPException(status_code=404, detail="Repository not found")
