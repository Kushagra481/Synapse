"""Authentication endpoints for configured workspace users."""
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import auth_is_configured, configured_users, issue_token, verify_password
from app.core.config import is_test_runtime, settings
from app.api.dependencies import require_bearer_auth
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


@router.get("/status")
async def auth_status():
    enabled = settings.AUTH_ENABLED and not is_test_runtime()
    return {"enabled": enabled, "configured": auth_is_configured() if enabled else True}


@router.post("/login")
async def login(payload: LoginRequest):
    if not settings.AUTH_ENABLED or is_test_runtime():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Authentication is disabled.")
    if not auth_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is enabled but not configured. Set the workspace auth secrets.",
        )
    users = configured_users()
    password_hash = users.get(payload.username)
    # Verify against a configured verifier even for unknown usernames so login
    # failures do not immediately reveal whether the account name exists.
    verifier_to_check = password_hash or next(iter(users.values()))
    password_valid = verify_password(payload.password, verifier_to_check)
    if not password_hash or not password_valid:
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
