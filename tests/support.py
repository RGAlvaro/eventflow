import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from eventflow.models import (
    ApiKey,
    Delivery,
    DeliveryAttempt,
    Endpoint,
    EndpointSecretVersion,
    Event,
    ManagementAudit,
    Organization,
    OutboxMessage,
    ReplayAudit,
    Subscription,
)
from eventflow.secrets import encrypt_secret


def sealed_secret(
    secret: bytes, organization_id: uuid.UUID, endpoint_id: uuid.UUID
) -> dict[str, object]:
    key_id, ciphertext = encrypt_secret(secret, organization_id, endpoint_id, 1)
    return {
        "signing_secret_ciphertext": ciphertext,
        "signing_secret_key_id": key_id,
        "signing_secret_version": 1,
    }


async def clean_organizations(engine: AsyncEngine, organization_ids: list[uuid.UUID]) -> None:
    async with engine.begin() as connection:
        for model in (
            ReplayAudit,
            ManagementAudit,
            OutboxMessage,
            DeliveryAttempt,
            Delivery,
            Event,
            Subscription,
            EndpointSecretVersion,
            Endpoint,
            ApiKey,
        ):
            await connection.execute(
                delete(model).where(model.organization_id.in_(organization_ids))
            )
        await connection.execute(delete(Organization).where(Organization.id.in_(organization_ids)))
