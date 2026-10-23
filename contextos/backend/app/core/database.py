"""PostgreSQL / SQLAlchemy async database layer."""
from __future__ import annotations
from typing import AsyncIterator
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text
from app.core.config import settings
from app.models import Base  # noqa: F401 - registers every model for initial schema creation
logger = structlog.get_logger(__name__)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> AsyncEngine:
    return create_async_engine(settings.DATABASE_URL, pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW, pool_timeout=settings.DB_POOL_TIMEOUT, pool_pre_ping=True, echo=settings.APP_DEBUG)


def get_engine() -> AsyncEngine:
    if _engine is None: raise RuntimeError("Database engine not initialized. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None: raise RuntimeError("Session factory not initialized. Call init_db() first.")
    return _session_factory


async def init_db() -> None:
    global _engine, _session_factory
    _engine = _create_engine()
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False, autocommit=False)
    async with _engine.begin() as conn:
        await conn.execute(text("SELECT version()"))
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Bootstrap the first-run schema. Use Alembic revisions for future changes.
        await conn.run_sync(Base.metadata.create_all)
    logger.info("contextos.postgres.schema_ready")


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
