"""
Session model — represents a single LLM working session.

A session captures:
- Which LLM was used
- What task was being worked on
- What changed during the session
- What was decided
- The conversation summary
- Next steps

Sessions are the foundation for cross-LLM handoffs.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Enum as SAEnum, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class Session(Base, UUIDMixin, TimestampMixin):
    """An LLM working session."""
    __tablename__ = "sessions"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # LLM info
    llm_provider: Mapped[str] = mapped_column(String(64), nullable=False)  # openai | anthropic | ...
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)    # gpt-4o, claude-3-5 ...
    developer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, name="session_status"),
        default=SessionStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # What happened in this session
    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conversation_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured session data (JSON)
    files_modified: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    decisions_made: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tasks_completed: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    bugs_found: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    open_questions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    next_steps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    starting_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    starting_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    starting_working_tree_dirty: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    handoff_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    handoff_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    handoff_changed_files: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    handoff_working_tree_dirty: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    git_snapshot_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="sessions")  # noqa: F821
    conversations: Mapped[list["Conversation"]] = relationship(  # noqa: F821
        "Conversation", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id} llm={self.llm_model} status={self.status}>"


class Conversation(Base, UUIDMixin, TimestampMixin):
    """
    A summarized conversation record within a session.

    We do NOT store full conversation text by default.
    Instead we store a compact structured summary of what happened.
    """
    __tablename__ = "conversations"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    decisions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    task_updates: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    files_modified: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    bugs_discovered: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    unresolved_questions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    next_actions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Optional: raw conversation storage (disabled by default)
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="conversations")

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} session={self.session_id}>"
