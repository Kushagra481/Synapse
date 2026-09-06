from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Simple OAuth2 password bearer (token URL would be provided in a real app)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dummy token → user mapping for demonstration purposes
FAKE_USERS_DB = {
    "example-token": {"username": "testuser", "id": "user-123"},
}

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Retrieve a fake user based on the supplied Bearer token.

    In a production system you would verify the token (e.g., JWT) and fetch the
    user from your database. Here we simply look up a hard‑coded mapping.
    """
    user = FAKE_USERS_DB.get(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
