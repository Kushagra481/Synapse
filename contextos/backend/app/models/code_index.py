"""Persistent metadata and source excerpts for the repository code index."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class IndexedFile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "indexed_files"
    __table_args__ = (
        UniqueConstraint("repository_id", "relative_path", name="uq_indexed_file_repository_path"),
        Index("ix_indexed_files_repository_sha", "repository_id", "content_sha256"),
    )

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parser: Mapped[str] = mapped_column(String(32), default="fallback", nullable=False)
    indexed_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)


class CodeSymbol(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "code_symbols"
    __table_args__ = (
        UniqueConstraint("file_id", "qualified_name", "start_line", name="uq_code_symbol_file_name_line"),
        Index("ix_code_symbols_repository_name", "repository_id", "name"),
        Index("ix_code_symbols_repository_kind", "repository_id", "kind"),
    )

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("indexed_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)


class RepositoryIndexState(Base, TimestampMixin):
    __tablename__ = "repository_index_state"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    indexed_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    symbol_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    working_tree_dirty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
