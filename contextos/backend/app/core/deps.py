"""
ContextOS — FastAPI Shared Dependencies

Injectable dependencies for database sessions, graph sessions,
and other cross-cutting concerns.
"""

from __future__ import annotations

from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.graph import GraphSession, get_graph_session

# Type aliases for clean endpoint signatures
DBSession = Annotated[AsyncSession, Depends(get_db)]
GraphDep = Annotated[GraphSession, Depends(get_graph_session)]
