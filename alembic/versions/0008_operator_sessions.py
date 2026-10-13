"""Add operator credentials, server sessions, and operator audit identity.

Revision ID: 0008_operator_sessions
Revises: 0007_observation_indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_operator_sessions"
down_revision: str | None = "0007_observation_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("username", sa.String(80), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "operator_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "operator_id"], ["operators.organization_id", "operators.id"]
        ),
    )
    op.create_index("ix_operator_sessions_expiry", "operator_sessions", ["expires_at"])
    op.add_column("replay_audits", sa.Column("actor_operator_id", postgresql.UUID(as_uuid=True)))
    op.alter_column("replay_audits", "actor_key_id", existing_type=postgresql.UUID(), nullable=True)
    op.create_foreign_key(
        "fk_replay_audits_operator",
        "replay_audits",
        "operators",
        ["organization_id", "actor_operator_id"],
        ["organization_id", "id"],
    )
    op.create_check_constraint(
        "ck_replay_audits_one_actor",
        "replay_audits",
        "(actor_key_id IS NOT NULL) <> (actor_operator_id IS NOT NULL)",
    )
    op.add_column(
        "management_audits", sa.Column("actor_operator_id", postgresql.UUID(as_uuid=True))
    )
    op.create_foreign_key(
        "fk_management_audits_operator",
        "management_audits",
        "operators",
        ["organization_id", "actor_operator_id"],
        ["organization_id", "id"],
    )
    op.create_check_constraint(
        "ck_management_audits_one_actor",
        "management_audits",
        "NOT (actor_key_id IS NOT NULL AND actor_operator_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_management_audits_one_actor", "management_audits", type_="check")
    op.drop_constraint("fk_management_audits_operator", "management_audits", type_="foreignkey")
    op.drop_column("management_audits", "actor_operator_id")
    op.drop_constraint("ck_replay_audits_one_actor", "replay_audits", type_="check")
    op.drop_constraint("fk_replay_audits_operator", "replay_audits", type_="foreignkey")
    op.execute("DELETE FROM replay_audits WHERE actor_key_id IS NULL")
    op.alter_column(
        "replay_audits", "actor_key_id", existing_type=postgresql.UUID(), nullable=False
    )
    op.drop_column("replay_audits", "actor_operator_id")
    op.drop_index("ix_operator_sessions_expiry", table_name="operator_sessions")
    op.drop_table("operator_sessions")
    op.drop_table("operators")
