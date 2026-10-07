"""Durable claims and broker notifications for webhook deliveries."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import create_engine, func, or_, select, text, tuple_, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eventflow.config import get_settings
from eventflow.models import Delivery, DeliveryAttempt, Endpoint, Event, OutboxMessage
from eventflow.retry import backoff_seconds, classify_result, retry_after_seconds
from eventflow.secrets import decrypt_secret

Publisher = Callable[[uuid.UUID], None]

LEASE_SECONDS = 60
GLOBAL_IN_FLIGHT = 4
ENDPOINT_IN_FLIGHT = 2
GLOBAL_STARTS_PER_SECOND = 4
ENDPOINT_STARTS_PER_SECOND = 1
MAX_ATTEMPTS_PER_GENERATION = 7


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
    key_id: int = 1


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
        secret = decrypt_secret(
            endpoint.signing_secret_key_id,
            endpoint.signing_secret_ciphertext,
            delivery.organization_id,
            endpoint.id,
            endpoint.signing_secret_version,
        )
        generation_attempts = (
            session.scalar(
                select(func.count())
                .select_from(DeliveryAttempt)
                .where(
                    DeliveryAttempt.organization_id == delivery.organization_id,
                    DeliveryAttempt.delivery_id == delivery.id,
                    DeliveryAttempt.generation == delivery.generation,
                )
            )
            or 0
        )
        if generation_attempts >= MAX_ATTEMPTS_PER_GENERATION:
            delivery.status = "dead_lettered"
            delivery.lease_token = None
            delivery.lease_expires_at = None
            delivery.next_attempt_at = None
            return None
        if endpoint.pause_until is not None and endpoint.pause_until > now:
            return None
        active_global = (
            session.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(Delivery.status == "processing", Delivery.lease_expires_at > now)
            )
            or 0
        )
        active_endpoint = (
            session.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(
                    Delivery.endpoint_id == delivery.endpoint_id,
                    Delivery.organization_id == delivery.organization_id,
                    Delivery.status == "processing",
                    Delivery.lease_expires_at > now,
                )
            )
            or 0
        )
        recent_global = (
            session.scalar(
                select(func.count())
                .select_from(DeliveryAttempt)
                .where(DeliveryAttempt.started_at > now - timedelta(seconds=1))
            )
            or 0
        )
        recent_endpoint = (
            session.scalar(
                select(func.count())
                .select_from(DeliveryAttempt)
                .join(
                    Delivery,
                    (Delivery.id == DeliveryAttempt.delivery_id)
                    & (Delivery.organization_id == DeliveryAttempt.organization_id),
                )
                .where(
                    Delivery.endpoint_id == delivery.endpoint_id,
                    Delivery.organization_id == delivery.organization_id,
                    DeliveryAttempt.started_at > now - timedelta(seconds=1),
                )
            )
            or 0
        )
        if (
            active_global >= GLOBAL_IN_FLIGHT
            or active_endpoint >= ENDPOINT_IN_FLIGHT
            or recent_global >= GLOBAL_STARTS_PER_SECOND
            or recent_endpoint >= ENDPOINT_STARTS_PER_SECOND
        ):
            return None
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
            secret,
            endpoint.signing_secret_version,
        )


def finish_delivery(
    engine: Engine,
    claim: ClaimedDelivery,
    response_status: int | None,
    error: str | None,
    retry_after: str | None = None,
) -> None:
    with Session(engine) as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(457219, 1)"))
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
        outcome = classify_result(response_status, error)
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
            ("succeeded" if outcome == "success" else "failed") if owns_lease else "late_result"
        )
        if not owns_lease:
            return
        delivery.lease_token = None
        delivery.lease_expires_at = None
        if outcome == "success":
            delivery.status = "succeeded"
            return
        generation_attempts = (
            session.scalar(
                select(func.count())
                .select_from(DeliveryAttempt)
                .where(
                    DeliveryAttempt.organization_id == claim.organization_id,
                    DeliveryAttempt.delivery_id == claim.delivery_id,
                    DeliveryAttempt.generation == claim.generation,
                )
            )
            or 0
        )
        if outcome == "permanent" or generation_attempts >= MAX_ATTEMPTS_PER_GENERATION:
            delivery.status = "dead_lettered"
            delivery.next_attempt_at = None
            return
        next_attempt_at = now + timedelta(seconds=backoff_seconds(generation_attempts))
        if response_status == 429:
            delay = retry_after_seconds(retry_after, now)
            if delay is not None:
                endpoint = session.scalar(
                    select(Endpoint)
                    .where(
                        Endpoint.id == delivery.endpoint_id,
                        Endpoint.organization_id == delivery.organization_id,
                    )
                    .with_for_update()
                )
                if endpoint is None:
                    raise RuntimeError("Delivery endpoint disappeared")
                pause_until = now + timedelta(seconds=delay)
                if endpoint.pause_until is None or endpoint.pause_until < pause_until:
                    endpoint.pause_until = pause_until
                if endpoint.pause_until > next_attempt_at:
                    next_attempt_at = endpoint.pause_until
        delivery.status = "retry_scheduled"
        delivery.next_attempt_at = next_attempt_at


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
    if limit < 1:
        raise ValueError("Reconciliation page size must be positive")
    with Session(engine) as session:
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
    cursor: tuple[datetime, uuid.UUID] | None = None
    published = 0
    while True:
        with Session(engine) as session:
            query = select(Delivery.id, Delivery.created_at).where(due_filter(now))
            if cursor is not None:
                query = query.where(tuple_(Delivery.created_at, Delivery.id) > cursor)
            rows = session.execute(
                query.order_by(Delivery.created_at, Delivery.id).limit(limit)
            ).all()
        for delivery_id, _created_at in rows:
            publish(delivery_id)
            published += 1
        if len(rows) < limit:
            return published
        cursor = (rows[-1].created_at, rows[-1].id)
