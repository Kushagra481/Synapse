from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/api/health")
async def health_check():
    return {"status": "ok", "environment": settings.APP_ENV}
