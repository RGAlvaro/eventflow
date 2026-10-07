"""Add event terminal time and index daily quota lookups.

Revision ID: 0005_ingest_retention
Revises: 0004_encrypted_signing_secrets
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_ingest_retention"
down_revision: str | None = "0004_encrypted_signing_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("terminal_at", sa.DateTime(timezone=True)))
    op.create_index("ix_events_tenant_created", "events", ["organization_id", "created_at"])
    op.execute(
        "UPDATE events AS e SET terminal_at = clock_timestamp() "
        "WHERE NOT EXISTS (SELECT 1 FROM deliveries AS d "
        "WHERE d.event_id = e.id AND d.organization_id = e.organization_id "
        "AND d.status NOT IN ('succeeded', 'dead_lettered'))"
    )


def downgrade() -> None:
    op.drop_index("ix_events_tenant_created", table_name="events")
    op.drop_column("events", "terminal_at")
