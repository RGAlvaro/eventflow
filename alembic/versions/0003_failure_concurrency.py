"""Add endpoint pause and tenant-scoped replay audit.

Revision ID: 0003_failure_concurrency
Revises: 0002_delivery_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_failure_concurrency"
down_revision: str | None = "0002_delivery_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("endpoints", sa.Column("pause_until", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_api_keys_tenant_id", "api_keys", ["organization_id", "id"])
    op.create_index("ix_delivery_attempts_started_at", "delivery_attempts", ["started_at"])
    op.create_table(
        "replay_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "delivery_id"], ["deliveries.organization_id", "deliveries.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_key_id"], ["api_keys.organization_id", "api_keys.id"]
        ),
        sa.UniqueConstraint("delivery_id", "generation"),
    )


def downgrade() -> None:
    op.drop_table("replay_audits")
    op.drop_index("ix_delivery_attempts_started_at", table_name="delivery_attempts")
    op.drop_constraint("uq_api_keys_tenant_id", "api_keys", type_="unique")
    op.drop_column("endpoints", "pause_until")
