"""Add tenant keyset pagination indexes.

Revision ID: 0007_observation_indexes
Revises: 0006_management
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_observation_indexes"
down_revision: str | None = "0006_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_events_tenant_created", table_name="events")
    op.create_index("ix_events_tenant_created", "events", ["organization_id", "created_at", "id"])
    op.create_index(
        "ix_deliveries_tenant_created", "deliveries", ["organization_id", "created_at", "id"]
    )
    op.create_index(
        "ix_attempts_tenant_started",
        "delivery_attempts",
        ["organization_id", "delivery_id", "started_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_attempts_tenant_started", table_name="delivery_attempts")
    op.drop_index("ix_deliveries_tenant_created", table_name="deliveries")
    op.drop_index("ix_events_tenant_created", table_name="events")
    op.create_index("ix_events_tenant_created", "events", ["organization_id", "created_at"])
