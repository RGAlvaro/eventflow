"""Add versioned endpoint secrets and tenant management audit.

Revision ID: 0006_management
Revises: 0005_ingest_retention
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_management"
down_revision: str | None = "0005_ingest_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "endpoint_secret_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("encryption_key_id", sa.String(40), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["organization_id", "endpoint_id"], ["endpoints.organization_id", "endpoints.id"]
        ),
        sa.UniqueConstraint("organization_id", "endpoint_id", "version"),
    )
    op.create_table(
        "management_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("actor_key_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_key_id"], ["api_keys.organization_id", "api_keys.id"]
        ),
    )
    op.create_index(
        "ix_management_audits_tenant_time", "management_audits", ["organization_id", "created_at"]
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, organization_id, signing_secret_version, signing_secret_key_id, "
            "signing_secret_ciphertext, created_at FROM endpoints"
        )
    ).all()
    for row in rows:
        connection.execute(
            sa.text(
                "INSERT INTO endpoint_secret_versions "
                "(id, organization_id, endpoint_id, version, encryption_key_id, ciphertext, "
                "status, created_at, activated_at) VALUES "
                "(:id, :organization_id, :endpoint_id, :version, :key_id, :ciphertext, "
                "'active', :created_at, :created_at)"
            ),
            {
                "id": uuid.uuid4(),
                "organization_id": row.organization_id,
                "endpoint_id": row.id,
                "version": row.signing_secret_version,
                "key_id": row.signing_secret_key_id,
                "ciphertext": row.signing_secret_ciphertext,
                "created_at": row.created_at,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_management_audits_tenant_time", table_name="management_audits")
    op.drop_table("management_audits")
    op.drop_table("endpoint_secret_versions")
