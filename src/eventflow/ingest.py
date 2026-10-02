import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.models import ApiKey, Delivery, Endpoint, Event, OutboxMessage, Subscription


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def publishing_organization(session: AsyncSession, raw_key: str) -> uuid.UUID | None:
    result = await session.scalar(
        select(ApiKey.organization_id).where(
            ApiKey.key_hash == hash_api_key(raw_key),
            ApiKey.scope == "publish",
            ApiKey.revoked_at.is_(None),
        )
    )
    return result


async def ingest_event(
    session: AsyncSession, organization_id: uuid.UUID, event_type: str, payload: dict[str, object]
) -> uuid.UUID:
    event_id = uuid.uuid4()
    async with session.begin():
        endpoint_ids = (
            await session.scalars(
                select(Endpoint.id)
                .join(
                    Subscription,
                    (Subscription.endpoint_id == Endpoint.id)
                    & (Subscription.organization_id == Endpoint.organization_id),
                )
                .where(
                    Endpoint.organization_id == organization_id,
                    Endpoint.active.is_(True),
                    Subscription.event_type == event_type,
                )
            )
        ).all()
        session.add(
            Event(
                id=event_id,
                organization_id=organization_id,
                event_type=event_type,
                payload=payload,
            )
        )
        await session.flush()
        deliveries = [
            Delivery(
                id=uuid.uuid4(),
                organization_id=organization_id,
                event_id=event_id,
                endpoint_id=endpoint_id,
                status="pending",
                generation=1,
                attempt_count=0,
            )
            for endpoint_id in endpoint_ids
        ]
        session.add_all(deliveries)
        await session.flush()
        session.add_all(
            OutboxMessage(
                id=uuid.uuid4(),
                organization_id=organization_id,
                delivery_id=delivery.id,
                generation=1,
            )
            for delivery in deliveries
        )
    return event_id
