"""Encrypt existing endpoint signing secrets and record their versions.

Revision ID: 0004_encrypted_signing_secrets
Revises: 0003_failure_concurrency
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from eventflow.secrets import encrypt_secret

revision: str = "0004_encrypted_signing_secrets"
down_revision: str | None = "0003_failure_concurrency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("endpoints", sa.Column("signing_secret_key_id", sa.String(40), nullable=True))
    op.add_column(
        "endpoints",
        sa.Column("signing_secret_version", sa.Integer(), server_default="1", nullable=False),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, organization_id, signing_secret_ciphertext FROM endpoints FOR UPDATE")
    ).all()
    for row in rows:
        key_id, ciphertext = encrypt_secret(
            row.signing_secret_ciphertext, row.organization_id, row.id, 1
        )
        connection.execute(
            sa.text(
                "UPDATE endpoints SET signing_secret_key_id = :key_id, "
                "signing_secret_ciphertext = :ciphertext WHERE id = :endpoint_id "
                "AND organization_id = :organization_id"
            ),
            {
                "key_id": key_id,
                "ciphertext": ciphertext,
                "endpoint_id": row.id,
                "organization_id": row.organization_id,
            },
        )
    op.alter_column("endpoints", "signing_secret_key_id", nullable=False)


def downgrade() -> None:
    raise RuntimeError("Cannot downgrade encrypted signing secrets to plaintext")
