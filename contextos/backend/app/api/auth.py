"""Authentication endpoints for the configured workspace operator."""
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import auth_is_configured, issue_token, verify_password
from app.core.config import settings
from app.api.dependencies import require_bearer_auth
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


@router.get("/status")
async def auth_status():
    enabled = settings.AUTH_ENABLED and settings.APP_ENV != "test"
    return {"enabled": enabled, "configured": auth_is_configured() if enabled else True}


@router.post("/login")
async def login(payload: LoginRequest):
    if not settings.AUTH_ENABLED or settings.APP_ENV == "test":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Authentication is disabled.")
    if not auth_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is enabled but not configured. Set the workspace auth secrets.",
        )
    if (
        payload.username != settings.AUTH_USERNAME
        or not verify_password(payload.password, settings.AUTH_PASSWORD_HASH)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_at = issue_token(payload.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "username": payload.username,
    }


@router.get("/me")
async def current_user(request: Request, principal: str = Depends(require_bearer_auth)):
    return {"username": principal}
