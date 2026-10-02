"""Create tenant-scoped event delivery tables.

Revision ID: 0002_delivery_foundation
Revises: 0001_organizations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_delivery_foundation"
down_revision: str | None = "0001_organizations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def tenant_id() -> sa.Column[object]:
    return sa.Column(
        "organization_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id"),
        nullable=False,
    )


def created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        tenant_id(),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        created_at(),
    )
    op.create_table(
        "endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        tenant_id(),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("signing_secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        created_at(),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        tenant_id(),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("fingerprint", sa.String(64)),
        created_at(),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        tenant_id(),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "endpoint_id"], ["endpoints.organization_id", "endpoints.id"]
        ),
        sa.UniqueConstraint("organization_id", "endpoint_id", "event_type"),
    )
    op.create_table(
        "deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        tenant_id(),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        created_at(),
        sa.ForeignKeyConstraint(
            ["organization_id", "event_id"], ["events.organization_id", "events.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "endpoint_id"], ["endpoints.organization_id", "endpoints.id"]
        ),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("event_id", "endpoint_id"),
    )
    op.create_index(
        "ix_deliveries_work", "deliveries", ["status", "next_attempt_at", "lease_expires_at"]
    )
    op.create_table(
        "delivery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        tenant_id(),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("error_category", sa.String(48)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["organization_id", "delivery_id"], ["deliveries.organization_id", "deliveries.id"]
        ),
        sa.UniqueConstraint("delivery_id", "number"),
    )
    op.create_table(
        "outbox_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        tenant_id(),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        created_at(),
        sa.ForeignKeyConstraint(
            ["organization_id", "delivery_id"], ["deliveries.organization_id", "deliveries.id"]
        ),
        sa.UniqueConstraint("delivery_id", "generation"),
    )
    op.create_index("ix_outbox_unpublished", "outbox_messages", ["published_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_unpublished", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_table("delivery_attempts")
    op.drop_index("ix_deliveries_work", table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_table("subscriptions")
    op.drop_table("events")
    op.drop_table("endpoints")
    op.drop_table("api_keys")
