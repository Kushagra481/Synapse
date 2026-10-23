"""Repository model — represents a tracked Git repository."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from sqlalchemy import String, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class IngestionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Repository(Base, UUIDMixin, TimestampMixin):
    """
    A tracked Git repository.

    This is the root entity around which all other project context is organized.
    """
    __tablename__ = "repositories"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_subject: Mapped[str] = mapped_column(String(255), default="local", nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    local_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Ingestion state
    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, name="ingestion_status"),
        default=IngestionStatus.PENDING,
        nullable=False,
    )
    last_ingested_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ingestion_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships (lazy loaded)
    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        "Task", back_populates="repository", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(  # noqa: F821
        "Decision", back_populates="repository", cascade="all, delete-orphan"
    )
    memory: Mapped[Optional["ProjectMemory"]] = relationship(  # noqa: F821
        "ProjectMemory", back_populates="repository", uselist=False, cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        "Session", back_populates="repository", cascade="all, delete-orphan"
    )
    bugs: Mapped[list["Bug"]] = relationship(  # noqa: F821
        "Bug", back_populates="repository", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Repository id={self.id} name={self.name}>"
