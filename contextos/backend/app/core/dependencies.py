from fastapi import HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import TypeVar, Callable, Optional, Dict

from app.core.database import get_db

ModelType = TypeVar('ModelType')

async def get_entity_or_404(
    model: Callable[..., ModelType],
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    detail: Optional[str] = None,
) -> ModelType:
    """Fetch an ORM entity by primary key or raise a 404 HTTPException.

    Args:
        model: The ORM model class to query.
        entity_id: Primary key of the entity.
        db: Async SQLAlchemy session (injected via FastAPI Depends).
        detail: Optional custom error message.
    Returns:
        The ORM instance.
    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(select(model).where(model.id == entity_id))
    instance = result.scalars().first()
    if not instance:
        raise HTTPException(status_code=404, detail=detail or f"{model.__name__} not found")
    return instance


def pagination_params(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
) -> Dict[str, int]:
    """Common pagination parameters for list endpoints.

    Returns a dict suitable for unpacking into query functions.
    """
    return {"skip": skip, "limit": limit}
