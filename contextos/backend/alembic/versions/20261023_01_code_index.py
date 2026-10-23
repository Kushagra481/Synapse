"""Add repository file and symbol index tables.

This migration assumes the original ContextOS tables already exist, as they do
for databases bootstrapped by the application's initial schema setup.
"""
from alembic import op
import sqlalchemy as sa


revision = "20261023_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "repositories" not in existing_tables:
        raise RuntimeError("Start ContextOS once to bootstrap its existing schema before applying this migration.")
    index_tables = {"indexed_files", "code_symbols", "repository_index_state"}
    if index_tables.issubset(existing_tables):
        # The app's create_all bootstrap may already have created these tables.
        # Mark the revision as applied without attempting duplicate DDL.
        return
    if existing_tables.intersection(index_tables):
        raise RuntimeError("Partial repository-index schema found; reconcile it before applying this migration.")

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
        "repository_index_state",
        sa.Column("repository_id", sa.String(length=36), nullable=False),
        sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("symbol_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("working_tree_dirty", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("repository_id"),
    )


def downgrade() -> None:
    op.drop_table("repository_index_state")
    op.drop_index("ix_code_symbols_repository_kind", table_name="code_symbols")
    op.drop_index("ix_code_symbols_repository_name", table_name="code_symbols")
    op.drop_index("ix_code_symbols_repository_id", table_name="code_symbols")
    op.drop_index("ix_code_symbols_file_id", table_name="code_symbols")
    op.drop_table("code_symbols")
    op.drop_index("ix_indexed_files_repository_sha", table_name="indexed_files")
    op.drop_index("ix_indexed_files_repository_id", table_name="indexed_files")
    op.drop_table("indexed_files")
