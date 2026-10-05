"""Durable claims and broker notifications for webhook deliveries."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import create_engine, func, or_, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eventflow.config import get_settings
from eventflow.models import Delivery, DeliveryAttempt, Endpoint, Event, OutboxMessage

Publisher = Callable[[uuid.UUID], None]

LEASE_SECONDS = 60
GLOBAL_IN_FLIGHT = 4


def make_sync_engine() -> Engine:
    url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


@dataclass(frozen=True)
class ClaimedDelivery:
    delivery_id: uuid.UUID
    organization_id: uuid.UUID
    attempt_id: uuid.UUID
    token: uuid.UUID
    event_id: uuid.UUID
    generation: int
    event_type: str
    payload: dict[str, object]
    url: str
    secret: bytes


def due_filter(now: datetime):  # type: ignore[no-untyped-def]
    return or_(
        Delivery.status == "pending",
        (Delivery.status == "retry_scheduled") & (Delivery.next_attempt_at <= now),
        (Delivery.status == "processing") & (Delivery.lease_expires_at <= now),
    )


def claim_delivery(engine: Engine, delivery_id: uuid.UUID) -> ClaimedDelivery | None:
    with Session(engine) as session, session.begin():
        # Serialize the global capacity check across worker processes.
        session.execute(text("SELECT pg_advisory_xact_lock(457219, 1)"))
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        active = session.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.status == "processing", Delivery.lease_expires_at > now)
        )
        if active is not None and active >= GLOBAL_IN_FLIGHT:
            return None
        delivery = session.scalar(
            select(Delivery).where(Delivery.id == delivery_id).with_for_update()
        )
        if delivery is None or not (
            delivery.status == "pending"
            or delivery.status == "retry_scheduled"
            and delivery.next_attempt_at is not None
            and delivery.next_attempt_at <= now
            or delivery.status == "processing"
            and delivery.lease_expires_at is not None
            and delivery.lease_expires_at <= now
        ):
            return None
        if delivery.status == "processing":
            session.execute(
                update(DeliveryAttempt)
                .where(
                    DeliveryAttempt.organization_id == delivery.organization_id,
                    DeliveryAttempt.delivery_id == delivery.id,
                    DeliveryAttempt.status == "processing",
                )
                .values(status="lease_expired", finished_at=now)
            )
        endpoint = session.scalar(
            select(Endpoint).where(
                Endpoint.id == delivery.endpoint_id,
                Endpoint.organization_id == delivery.organization_id,
            )
        )
        event = session.scalar(
            select(Event).where(
                Event.id == delivery.event_id,
                Event.organization_id == delivery.organization_id,
            )
        )
        if endpoint is None or event is None:
            raise RuntimeError("Delivery has no tenant-matched endpoint or event")
        token, attempt_id = uuid.uuid4(), uuid.uuid4()
        delivery.status = "processing"
        delivery.lease_token = token
        delivery.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        delivery.next_attempt_at = None
        delivery.attempt_count += 1
        session.add(
            DeliveryAttempt(
                id=attempt_id,
                organization_id=delivery.organization_id,
                delivery_id=delivery.id,
                number=delivery.attempt_count,
                generation=delivery.generation,
                status="processing",
                started_at=now,
            )
        )
        return ClaimedDelivery(
            delivery.id,
            delivery.organization_id,
            attempt_id,
            token,
            event.id,
            delivery.generation,
            event.event_type,
            event.payload,
            endpoint.url,
            endpoint.signing_secret_ciphertext,
        )


def finish_delivery(
    engine: Engine, claim: ClaimedDelivery, response_status: int | None, error: str | None
) -> None:
    with Session(engine) as session, session.begin():
        now = session.scalar(select(func.clock_timestamp()))
        delivery = session.scalar(
            select(Delivery)
            .where(
                Delivery.id == claim.delivery_id,
                Delivery.organization_id == claim.organization_id,
            )
            .with_for_update()
        )
        attempt = session.scalar(
            select(DeliveryAttempt).where(
                DeliveryAttempt.id == claim.attempt_id,
                DeliveryAttempt.organization_id == claim.organization_id,
                DeliveryAttempt.delivery_id == claim.delivery_id,
            )
        )
        if delivery is None or attempt is None or now is None:
            raise RuntimeError("Claimed delivery or attempt disappeared")
        owns_lease = (
            delivery.lease_token == claim.token
            and delivery.status == "processing"
            and delivery.lease_expires_at is not None
            and delivery.lease_expires_at > now
        )
        attempt.response_status = response_status
        attempt.error_category = error
        attempt.finished_at = now
        attempt.status = (
            (
                "succeeded"
                if response_status is not None and 200 <= response_status < 300
                else "failed"
            )
            if owns_lease
            else "late_result"
        )
        if not owns_lease:
            return
        delivery.lease_token = None
        delivery.lease_expires_at = None
        if attempt.status == "succeeded":
            delivery.status = "succeeded"
        else:
            # Hito 2 refines response classification and backoff.
            if delivery.attempt_count >= 7:
                delivery.status = "dead_lettered"
            else:
                delivery.status = "retry_scheduled"
                delivery.next_attempt_at = now + timedelta(seconds=30)


def dispatch_outbox(engine: Engine, publish: "Publisher", limit: int = 100) -> int:
    published = 0
    with Session(engine) as session:
        rows = session.execute(
            select(OutboxMessage.id, OutboxMessage.organization_id, OutboxMessage.delivery_id)
            .where(OutboxMessage.published_at.is_(None))
            .order_by(OutboxMessage.created_at)
            .limit(limit)
        ).all()
    for row in rows:
        publish(row.delivery_id)
        with Session(engine) as session, session.begin():
            session.execute(
                update(OutboxMessage)
                .where(
                    OutboxMessage.id == row.id,
                    OutboxMessage.organization_id == row.organization_id,
                    OutboxMessage.published_at.is_(None),
                )
                .values(published_at=func.clock_timestamp())
            )
        published += 1
    return published


def reconcile_deliveries(engine: Engine, publish: "Publisher", limit: int = 100) -> int:
    with Session(engine) as session:
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        ids = session.scalars(
            select(Delivery.id).where(due_filter(now)).order_by(Delivery.created_at).limit(limit)
        ).all()
    for delivery_id in ids:
        publish(delivery_id)
    return len(ids)
