"""Persistent, data-driven retrieval benchmark cases and runs."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class RetrievalEvalCase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "retrieval_eval_cases"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_files: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_symbols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RetrievalEvalRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "retrieval_eval_runs"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    case_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    profiles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    case_results: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
