"""Pydantic schemas for health check endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ServiceStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class ServiceHealth(BaseModel):
    name: str
    status: ServiceStatus
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: ServiceStatus
    version: str
    environment: str
    services: list[ServiceHealth]
