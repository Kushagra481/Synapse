"""Append-only request audit metadata; request bodies and secrets are never stored."""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class AuditEvent(Base, UUIDMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_project_created", "project_id", "created_at"),
        Index("ix_audit_actor_created", "actor", "created_at"),
    )

    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(512), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
