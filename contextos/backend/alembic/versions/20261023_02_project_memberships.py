"""Add repository member roles and backfill existing owners."""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "20261023_02"
down_revision = "20261023_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "project_memberships" not in existing_tables:
        op.create_table(
            "project_memberships",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "repository_id",
                sa.String(length=36),
                sa.ForeignKey("repositories.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_subject", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "repository_id", "user_subject", name="uq_project_membership_user"
            ),
            sa.CheckConstraint(
                "role IN ('owner', 'editor', 'viewer')", name="ck_project_membership_role"
            ),
        )
    indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("project_memberships")
    }
    if "ix_project_memberships_repository_id" not in indexes:
        op.create_index(
            "ix_project_memberships_repository_id", "project_memberships", ["repository_id"]
        )
    if "ix_project_memberships_user_subject" not in indexes:
        op.create_index(
            "ix_project_memberships_user_subject", "project_memberships", ["user_subject"]
        )

    repositories = bind.execute(
        sa.text(
            "SELECT r.id, r.owner_subject FROM repositories r "
            "WHERE NOT EXISTS (SELECT 1 FROM project_memberships m "
            "WHERE m.repository_id = r.id AND m.user_subject = r.owner_subject)"
        )
    ).all()
    membership_table = sa.table(
        "project_memberships",
        sa.column("id", sa.String),
        sa.column("repository_id", sa.String),
        sa.column("user_subject", sa.String),
        sa.column("role", sa.String),
    )
    if repositories:
        op.bulk_insert(
            membership_table,
            [
                {
                    "id": str(uuid.uuid4()),
                    "repository_id": repository_id,
                    "user_subject": owner_subject,
                    "role": "owner",
                }
                for repository_id, owner_subject in repositories
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_project_memberships_user_subject", table_name="project_memberships")
    op.drop_index("ix_project_memberships_repository_id", table_name="project_memberships")
    op.drop_table("project_memberships")
