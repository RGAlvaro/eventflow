import hashlib
import json
import math
import uuid
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.models import (
    ApiKey,
    Delivery,
    Endpoint,
    Event,
    Organization,
    OutboxMessage,
    Subscription,
)

DAILY_EVENTS = 1_000
PENDING_DELIVERIES = 10_000


class IdempotencyConflict(Exception):
    pass


class DailyQuotaExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class PendingCapacityExceeded(Exception):
    pass


def event_fingerprint(event_type: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"type": event_type, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_type: str,
    payload: dict[str, object],
    idempotency_key: str | None = None,
) -> uuid.UUID:
    event_id = uuid.uuid4()
    fingerprint = event_fingerprint(event_type, payload) if idempotency_key else None
    async with session.begin():
        # One tenant row serializes both quota checks and inserts across API instances.
        tenant = await session.scalar(
            select(Organization.id).where(Organization.id == organization_id).with_for_update()
        )
        if tenant is None:
            raise RuntimeError("Publishing organization disappeared")
        now = await session.scalar(select(func.clock_timestamp()))
        assert now is not None
        if idempotency_key is not None:
            original = (
                await session.execute(
                    select(Event.id, Event.fingerprint).where(
                        Event.organization_id == organization_id,
                        Event.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if original is not None:
                if original.fingerprint != fingerprint:
                    raise IdempotencyConflict()
                return uuid.UUID(str(original.id))
        utc_now = now.astimezone(UTC)
        day_start = datetime.combine(utc_now.date(), time.min, tzinfo=UTC)
        next_day = day_start + timedelta(days=1)
        today_count = (
            await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.organization_id == organization_id,
                    Event.created_at >= day_start,
                    Event.created_at < next_day,
                )
            )
            or 0
        )
        if today_count >= DAILY_EVENTS:
            raise DailyQuotaExceeded(max(1, math.ceil((next_day - utc_now).total_seconds())))
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
        outstanding = (
            await session.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(
                    Delivery.organization_id == organization_id,
                    Delivery.status.in_(("pending", "processing", "retry_scheduled")),
                )
            )
            or 0
        )
        if outstanding + len(endpoint_ids) > PENDING_DELIVERIES:
            raise PendingCapacityExceeded()
        if idempotency_key is not None:
            inserted = await session.scalar(
                insert(Event)
                .values(
                    id=event_id,
                    organization_id=organization_id,
                    event_type=event_type,
                    payload=payload,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                    terminal_at=now if not endpoint_ids else None,
                )
                .on_conflict_do_nothing(
                    index_elements=[Event.organization_id, Event.idempotency_key]
                )
                .returning(Event.id)
            )
            if inserted is None:
                original = (
                    await session.execute(
                        select(Event.id, Event.fingerprint).where(
                            Event.organization_id == organization_id,
                            Event.idempotency_key == idempotency_key,
                        )
                    )
                ).one()
                if original.fingerprint != fingerprint:
                    raise IdempotencyConflict()
                return uuid.UUID(str(original.id))
        if idempotency_key is None:
            session.add(
                Event(
                    id=event_id,
                    organization_id=organization_id,
                    event_type=event_type,
                    payload=payload,
                    terminal_at=now if not endpoint_ids else None,
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
