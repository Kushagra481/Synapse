"""
ProjectMemory model — the persistent external memory for a repository.

This is one of the most important models in ContextOS.
It stores the complete project state that any LLM can read at session start.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProjectMemory(Base, UUIDMixin, TimestampMixin):
    """
    Persistent project memory — exists independently of any LLM.

    A single ProjectMemory record per repository. Contains structured
    information about the project that any LLM can consume immediately.
    """
    __tablename__ = "project_memories"

    repository_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Core Project Info ──────────────────────────────────────────────────────
    project_goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    architecture_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Technology Stack ───────────────────────────────────────────────────────
    tech_stack: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # e.g. [{"name": "FastAPI", "version": "0.115", "role": "web framework"}]

    # ── Task State ────────────────────────────────────────────────────────────
    current_task: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active_tasks: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    completed_tasks: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    blocked_tasks: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    next_steps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # ── Issues & Questions ─────────────────────────────────────────────────────
    known_bugs: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    open_questions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # ── Recent Activity ───────────────────────────────────────────────────────
    recent_changes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    recently_modified_files: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    recent_commits: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    conversation_summaries: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # ── Custom Notes ──────────────────────────────────────────────────────────
    custom_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    repository: Mapped["Repository"] = relationship(  # noqa: F821
        "Repository", back_populates="memory"
    )

    def __repr__(self) -> str:
        return f"<ProjectMemory repository_id={self.repository_id}>"


class Bug(Base, UUIDMixin, TimestampMixin):
    """A known bug or issue tracked in project memory."""
    __tablename__ = "bugs"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)  # file:line
    severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    is_resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="bugs")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Bug id={self.id} title={self.title!r} resolved={self.is_resolved}>"
