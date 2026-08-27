"""
Decision model — captures architectural and technical decisions.

Decisions persist the reasoning behind important choices so any LLM
can understand WHY the project is built the way it is.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class DecisionCategory(str, Enum):
    ARCHITECTURE = "architecture"
    TECHNOLOGY = "technology"
    API = "api"
    DATABASE = "database"
    SECURITY = "security"
    PERFORMANCE = "performance"
    PROCESS = "process"
    OTHER = "other"


class Decision(Base, UUIDMixin, TimestampMixin):
    """An architectural or technical decision."""
    __tablename__ = "decisions"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # What was the problem?
    decision: Mapped[str] = mapped_column(Text, nullable=False)          # What was decided?
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Why?
    consequences: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Tradeoffs

    status: Mapped[DecisionStatus] = mapped_column(
        SAEnum(DecisionStatus, name="decision_status"),
        default=DecisionStatus.ACCEPTED,
        nullable=False,
        index=True,
    )
    category: Mapped[DecisionCategory] = mapped_column(
        SAEnum(DecisionCategory, name="decision_category"),
        default=DecisionCategory.OTHER,
        nullable=False,
    )

    # Which session created this decision
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="decisions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Decision id={self.id} title={self.title!r} status={self.status}>"
