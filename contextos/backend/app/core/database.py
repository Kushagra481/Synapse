"""
ContextOS — PostgreSQL / SQLAlchemy Async Database Layer

Provides:
- Async engine and session factory
- Dependency-injectable session (get_db)
- init_db() and close_db() lifecycle functions
"""

from __future__ import annotations

from typing import AsyncIterator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ─── Engine & Session Factory ─────────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        echo=settings.APP_DEBUG,
    )


def get_engine() -> AsyncEngine:
    """Return the global async engine (must call init_db first)."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Session factory not initialized. Call init_db() first.")
    return _session_factory


# ─── Lifecycle ────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Initialize the database engine and verify connectivity."""
    global _engine, _session_factory

    _engine = _create_engine()
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    # Verify connection
    async with _engine.begin() as conn:
        result = await conn.execute(text("SELECT version()"))
        version = result.scalar()
        logger.info("contextos.postgres.version", version=version)


async def close_db() -> None:
    """Close the database engine gracefully."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("contextos.postgres.closed")


# ─── Dependency ───────────────────────────────────────────────────────────────

async def get_db() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency that yields an async database session.

    Usage:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
