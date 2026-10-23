"""ContextOS FastAPI application."""
from __future__ import annotations
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.graph import init_graph, close_graph
from app.core.logging import configure_logging
from app.api import health, repositories, tasks, decisions, memory, sessions, context

configure_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    start = time.monotonic()
    logger.info("contextos.startup", version=settings.APP_VERSION, env=settings.APP_ENV)
    if settings.APP_ENV != "test":
        await init_db()
        logger.info("contextos.postgres.connected")
        await init_graph()
        logger.info("contextos.neo4j.connected")
    logger.info("contextos.startup.complete", elapsed_ms=round((time.monotonic() - start) * 1000, 2))
    yield
    if settings.APP_ENV != "test":
        await close_db()
        await close_graph()


def create_app() -> FastAPI:
    app = FastAPI(title="ContextOS", description="Persistent, compact project context for coding agents. Memory stays in your database; agents request a task-specific handoff packet.", version=settings.APP_VERSION, docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "Authorization"])
    app.include_router(health.router, tags=["Health"])
    app.include_router(repositories.router, prefix="/repositories", tags=["Repositories"])
    app.include_router(tasks.router, prefix="/repositories", tags=["Tasks"])
    app.include_router(decisions.router, prefix="/repositories", tags=["Decisions"])
    app.include_router(memory.router, prefix="/repositories", tags=["Memory"])
    app.include_router(sessions.router, prefix="/repositories", tags=["Sessions"])
    app.include_router(context.router, prefix="/repositories", tags=["Agent Context"])
    return app


app = create_app()
