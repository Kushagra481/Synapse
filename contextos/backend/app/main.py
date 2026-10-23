"""ContextOS FastAPI application."""
from __future__ import annotations
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator
import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.auth import auth_is_configured, verify_token
from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.database import get_session_factory
from app.core.graph import init_graph, close_graph
from app.core.logging import configure_logging
from app.api import auth, health, repositories, tasks, decisions, memory, sessions, context, evaluations, audit, memberships
from app.models.audit import AuditEvent
from app.api.dependencies import require_bearer_auth, require_repository_access

configure_logging()
logger = structlog.get_logger(__name__)


async def _record_audit(request: Request, status_code: int, duration_ms: float) -> None:
    if settings.APP_ENV == "test":
        return
    try:
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        params = request.path_params or {}
        project_id = params.get("repo_id")
        resource_id = next(
            (
                params[key]
                for key in ("fact_id", "task_id", "decision_id", "session_id", "case_id")
                if params.get(key)
            ),
            None,
        )
        event = AuditEvent(
            actor=getattr(request.state, "principal", None) or "anonymous",
            action=f"{request.method} {route_template}",
            project_id=project_id,
            resource_id=resource_id,
            outcome="success" if status_code < 400 else "failure",
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            details={"status_code": status_code, "duration_ms": round(duration_ms, 2)},
        )
        async with get_session_factory()() as db:
            db.add(event)
            await db.commit()
    except Exception as exc:
        logger.warning("contextos.audit_write_failed", error_type=type(exc).__name__)


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
    app.include_router(auth.router)
    app.include_router(health.router, tags=["Health"])
    access_check = [Depends(require_bearer_auth), Depends(require_repository_access)]
    app.include_router(repositories.router, prefix="/repositories", tags=["Repositories"], dependencies=access_check)
    app.include_router(tasks.router, prefix="/repositories", tags=["Tasks"], dependencies=access_check)
    app.include_router(decisions.router, prefix="/repositories", tags=["Decisions"], dependencies=access_check)
    app.include_router(memory.router, prefix="/repositories", tags=["Memory"], dependencies=access_check)
    app.include_router(sessions.router, prefix="/repositories", tags=["Sessions"], dependencies=access_check)
    app.include_router(context.router, prefix="/repositories", tags=["Agent Context"], dependencies=access_check)
    app.include_router(evaluations.router, prefix="/repositories", tags=["Evaluations"], dependencies=access_check)
    app.include_router(audit.router, prefix="/repositories", tags=["Audit"], dependencies=access_check)
    app.include_router(memberships.router, prefix="/repositories", tags=["Members"], dependencies=access_check)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if settings.APP_ENV == "test":
            request.state.principal = "test"
            return await call_next(request)
        if not settings.AUTH_ENABLED:
            request.state.principal = "local"
            started = time.monotonic()
            response = await call_next(request)
            if request.url.path.startswith("/repositories/"):
                await _record_audit(request, response.status_code, (time.monotonic() - started) * 1000)
            return response
        if (
            request.url.path in {"/api/health", "/auth/status", "/auth/login", "/openapi.json"}
            or request.url.path.startswith(("/docs", "/redoc"))
            or request.method == "OPTIONS"
        ):
            started = time.monotonic()
            response = await call_next(request)
            if request.url.path == "/auth/login":
                await _record_audit(request, response.status_code, (time.monotonic() - started) * 1000)
            return response
        if not auth_is_configured():
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication is enabled but not configured. Set the workspace auth secrets."},
            )
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        principal = verify_token(token) if scheme.lower() == "bearer" else None
        if not principal:
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Authentication required."},
            )
        request.state.principal = principal
        started = time.monotonic()
        response = await call_next(request)
        if request.url.path.startswith("/repositories/"):
            await _record_audit(request, response.status_code, (time.monotonic() - started) * 1000)
        return response

    return app


app = create_app()
