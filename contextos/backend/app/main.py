"""
ContextOS Backend — Application Entry Point

Initializes FastAPI application with:
- Lifespan management (startup/shutdown hooks)
- Database connection verification
- Neo4j connection verification
- CORS middleware
- Structured logging
- All API routers
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.graph import init_graph, close_graph
from app.core.logging import configure_logging

from app.api import health, repositories, tasks, decisions, memory, sessions

# Configure structured logging before anything else
configure_logging()
logger = structlog.get_logger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks."""
    start = time.monotonic()
    logger.info("contextos.startup", version=settings.APP_VERSION, env=settings.APP_ENV)

    # Initialize PostgreSQL
    await init_db()
    logger.info("contextos.postgres.connected")

    # Initialize Neo4j
    await init_graph()
    logger.info("contextos.neo4j.connected")

    elapsed = time.monotonic() - start
    logger.info("contextos.startup.complete", elapsed_ms=round(elapsed * 1000, 2))

    yield  # Application runs here

    # Shutdown
    logger.info("contextos.shutdown")
    await close_db()
    await close_graph()
    logger.info("contextos.shutdown.complete")


# ─── App Factory ──────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ContextOS",
        description=(
            "Model-agnostic persistent memory and context infrastructure "
            "for AI-powered software development.\n\n"
            "**Your codebase has memory, not your LLM.**"
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router, tags=["Health"])
    app.include_router(repositories.router, prefix="/repositories", tags=["Repositories"])
    app.include_router(tasks.router, prefix="/repositories", tags=["Tasks"])
    app.include_router(decisions.router, prefix="/repositories", tags=["Decisions"])
    app.include_router(memory.router, prefix="/repositories", tags=["Memory"])
    app.include_router(sessions.router, prefix="/repositories", tags=["Sessions"])

    return app


app = create_app()
