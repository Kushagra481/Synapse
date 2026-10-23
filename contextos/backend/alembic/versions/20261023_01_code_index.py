"""Add repository file and symbol index tables.

This migration assumes the original ContextOS tables already exist, as they do
for databases bootstrapped by the application's initial schema setup.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from app.core.config import settings


revision = "20261023_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "repositories" not in existing_tables:
        raise RuntimeError("Start ContextOS once to bootstrap its existing schema before applying this migration.")
    repository_columns = {column["name"] for column in sa.inspect(bind).get_columns("repositories")}
    if "owner_subject" not in repository_columns:
        op.add_column(
            "repositories",
            sa.Column(
                "owner_subject",
                sa.String(length=255),
                nullable=False,
                server_default=(
                    settings.AUTH_USERNAME
                    if settings.AUTH_ENABLED and settings.AUTH_USERNAME
                    else "local"
                ),
            ),
        )
    repository_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("repositories")}
    if "ix_repositories_owner_subject" not in repository_indexes:
        op.create_index("ix_repositories_owner_subject", "repositories", ["owner_subject"])
    if "sessions" in existing_tables:
        session_columns = {column["name"] for column in sa.inspect(bind).get_columns("sessions")}
        handoff_columns = {
            "starting_branch": sa.String(length=255),
            "starting_commit_sha": sa.String(length=40),
            "starting_working_tree_dirty": sa.Boolean(),
            "handoff_branch": sa.String(length=255),
            "handoff_commit_sha": sa.String(length=40),
            "handoff_changed_files": sa.JSON(),
            "handoff_working_tree_dirty": sa.Boolean(),
            "git_snapshot_status": sa.String(length=32),
        }
        for name, type_ in handoff_columns.items():
            if name not in session_columns:
                op.add_column("sessions", sa.Column(name, type_, nullable=True))
    index_tables = {
        "indexed_files", "code_symbols", "code_imports", "repository_index_state",
        "retrieval_eval_cases", "retrieval_eval_runs",
        "project_memory_facts",
        "audit_events",
    }
    if index_tables.issubset(existing_tables):
        # The app's create_all bootstrap may already have created these tables.
        # Mark the revision as applied without attempting duplicate DDL.
        return
    if existing_tables.intersection(index_tables):
        raise RuntimeError("Partial repository-index schema found; reconcile it before applying this migration.")
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "indexed_files",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("parser", sa.String(length=32), nullable=False),
        sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "relative_path", name="uq_indexed_file_repository_path"),
    )
    op.create_index("ix_indexed_files_repository_id", "indexed_files", ["repository_id"])
    op.create_index("ix_indexed_files_repository_sha", "indexed_files", ["repository_id", "content_sha256"])

    op.create_table(
        "code_symbols",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("qualified_name", sa.String(length=1024), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            Vector(settings.EMBEDDING_DIMENSION).with_variant(sa.JSON(none_as_null=True), "sqlite"),
            nullable=True,
        ),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["indexed_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", "qualified_name", "start_line", name="uq_code_symbol_file_name_line"),
    )
    op.create_index("ix_code_symbols_file_id", "code_symbols", ["file_id"])
    op.create_index("ix_code_symbols_repository_id", "code_symbols", ["repository_id"])
    op.create_index("ix_code_symbols_repository_name", "code_symbols", ["repository_id", "name"])
    op.create_index("ix_code_symbols_repository_kind", "code_symbols", ["repository_id", "kind"])

    op.create_table(
        "code_imports",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("target_module", sa.String(length=1024), nullable=False),
        sa.Column("target_file_path", sa.String(length=1024), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["indexed_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", "target_module", "start_line", name="uq_code_import_file_target_line"),
    )
    op.create_index("ix_code_imports_file_id", "code_imports", ["file_id"])
    op.create_index("ix_code_imports_repository_id", "code_imports", ["repository_id"])
    op.create_index("ix_code_imports_repository_target", "code_imports", ["repository_id", "target_module"])

    op.create_table(
        "repository_index_state",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("symbol_count", sa.Integer(), nullable=False),
        sa.Column("import_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("working_tree_dirty", sa.Boolean(), nullable=False),
        sa.Column("embedding_status", sa.String(length=32), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_count", sa.Integer(), nullable=False),
        sa.Column("graph_sync_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("repository_id"),
    )

    op.create_table(
        "retrieval_eval_cases",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("expected_files", sa.JSON(), nullable=False),
        sa.Column("expected_symbols", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retrieval_eval_cases_repository_id", "retrieval_eval_cases", ["repository_id"])

    op.create_table(
        "retrieval_eval_runs",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("index_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("profiles", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("case_results", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retrieval_eval_runs_repository_id", "retrieval_eval_runs", ["repository_id"])

    op.create_table(
        "project_memory_facts",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("topic_key", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("source_file_path", sa.String(length=1024), nullable=True),
        sa.Column("source_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("source_content_sha256", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False),
        sa.Column("conflict_status", sa.String(length=32), nullable=False),
        sa.Column("conflicts_with", sa.JSON(), nullable=False),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_memory_facts_repository_id", "project_memory_facts", ["repository_id"])
    op.create_index("ix_memory_facts_repo_topic", "project_memory_facts", ["repository_id", "topic_key"])
    op.create_index(
        "ix_memory_facts_repo_status",
        "project_memory_facts",
        ["repository_id", "conflict_status", "is_stale"],
    )
    op.create_table(
        "audit_events",
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=512), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_project_created", "audit_events", ["project_id", "created_at"])
    op.create_index("ix_audit_actor_created", "audit_events", ["actor", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_actor_created", table_name="audit_events")
    op.drop_index("ix_audit_project_created", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_memory_facts_repo_status", table_name="project_memory_facts")
    op.drop_index("ix_memory_facts_repo_topic", table_name="project_memory_facts")
    op.drop_index("ix_project_memory_facts_repository_id", table_name="project_memory_facts")
    op.drop_table("project_memory_facts")
    op.drop_index("ix_retrieval_eval_runs_repository_id", table_name="retrieval_eval_runs")
    op.drop_table("retrieval_eval_runs")
    op.drop_index("ix_retrieval_eval_cases_repository_id", table_name="retrieval_eval_cases")
    op.drop_table("retrieval_eval_cases")
    op.drop_table("repository_index_state")
    op.drop_index("ix_code_imports_repository_target", table_name="code_imports")
    op.drop_index("ix_code_imports_repository_id", table_name="code_imports")
    op.drop_index("ix_code_imports_file_id", table_name="code_imports")
    op.drop_table("code_imports")
    op.drop_index("ix_code_symbols_repository_kind", table_name="code_symbols")
    op.drop_index("ix_code_symbols_repository_name", table_name="code_symbols")
    op.drop_index("ix_code_symbols_repository_id", table_name="code_symbols")
    op.drop_index("ix_code_symbols_file_id", table_name="code_symbols")
    op.drop_table("code_symbols")
    op.drop_index("ix_indexed_files_repository_sha", table_name="indexed_files")
    op.drop_index("ix_indexed_files_repository_id", table_name="indexed_files")
    op.drop_table("indexed_files")
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("repositories")}
    if "ix_repositories_owner_subject" in indexes:
        op.drop_index("ix_repositories_owner_subject", table_name="repositories")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("repositories")}
    if "owner_subject" in columns:
        op.drop_column("repositories", "owner_subject")
    if "sessions" in set(sa.inspect(bind).get_table_names()):
        session_columns = {column["name"] for column in sa.inspect(bind).get_columns("sessions")}
        for name in (
            "git_snapshot_status", "handoff_working_tree_dirty", "handoff_changed_files",
            "handoff_commit_sha", "handoff_branch", "starting_working_tree_dirty",
            "starting_commit_sha", "starting_branch",
        ):
            if name in session_columns:
                op.drop_column("sessions", name)
