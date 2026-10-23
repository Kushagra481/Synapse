"""Provenance-aware, append-oriented project facts."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProjectMemoryFact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_memory_facts"
    __table_args__ = (
        Index("ix_memory_facts_repo_topic", "repository_id", "topic_key"),
        Index("ix_memory_facts_repo_status", "repository_id", "conflict_status", "is_stale"),
    )

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False, default="project")
    topic_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    conflict_status: Mapped[str] = mapped_column(String(32), default="clear", nullable=False)
    conflicts_with: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
