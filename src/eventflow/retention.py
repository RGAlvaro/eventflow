"""Delete expired terminal event aggregates without orphaning recoverable work."""

import uuid
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import delete, func, or_, select
from sqlalchemy.engine import CursorResult, Engine
from sqlalchemy.orm import Session

from eventflow.models import (
    Delivery,
    DeliveryAttempt,
    EndpointSecretVersion,
    Event,
    OperatorSession,
    OutboxMessage,
    ReplayAudit,
)

RETENTION_DAYS = 30


def purge_terminal_events(engine: Engine, limit: int = 100) -> int:
    if limit < 1:
        raise ValueError("Purge page size must be positive")
    with Session(engine) as session:
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        cutoff = now - timedelta(days=RETENTION_DAYS)
        candidates = session.execute(
            select(Event.organization_id, Event.id)
            .where(Event.terminal_at.is_not(None), Event.terminal_at <= cutoff)
            .order_by(Event.terminal_at, Event.id)
            .limit(limit)
        ).all()
    deleted = 0
    for organization_id, event_id in candidates:
        with Session(engine) as session, session.begin():
            # Delivery first matches replay and finish lock order; then recheck the event.
            deliveries = session.scalars(
                select(Delivery)
                .where(Delivery.organization_id == organization_id, Delivery.event_id == event_id)
                .order_by(Delivery.id)
                .with_for_update()
            ).all()
            event = session.scalar(
                select(Event)
                .where(Event.organization_id == organization_id, Event.id == event_id)
                .with_for_update()
            )
            if (
                event is None
                or event.terminal_at is None
                or event.terminal_at > cutoff
                or any(item.status not in ("succeeded", "dead_lettered") for item in deliveries)
            ):
                continue
            delivery_ids: list[uuid.UUID] = [item.id for item in deliveries]
            if delivery_ids:
                session.execute(
                    delete(ReplayAudit).where(
                        ReplayAudit.organization_id == organization_id,
                        ReplayAudit.delivery_id.in_(delivery_ids),
                    )
                )
                session.execute(
                    delete(OutboxMessage).where(
                        OutboxMessage.organization_id == organization_id,
                        OutboxMessage.delivery_id.in_(delivery_ids),
                    )
                )
                session.execute(
                    delete(DeliveryAttempt).where(
                        DeliveryAttempt.organization_id == organization_id,
                        DeliveryAttempt.delivery_id.in_(delivery_ids),
                    )
                )
                session.execute(
                    delete(Delivery).where(
                        Delivery.organization_id == organization_id,
                        Delivery.event_id == event_id,
                    )
                )
            session.execute(
                delete(Event).where(Event.organization_id == organization_id, Event.id == event_id)
            )
            deleted += 1
    return deleted


def purge_expired_secret_versions(engine: Engine) -> int:
    with Session(engine) as session, session.begin():
        result = cast(
            CursorResult[Any],
            session.execute(
                delete(EndpointSecretVersion).where(
                    EndpointSecretVersion.status == "retiring",
                    EndpointSecretVersion.expires_at <= func.clock_timestamp(),
                )
            ),
        )
        return result.rowcount or 0


def purge_expired_operator_sessions(engine: Engine) -> int:
    with Session(engine) as session, session.begin():
        now = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        result = cast(
            CursorResult[Any],
            session.execute(
                delete(OperatorSession).where(
                    or_(
                        OperatorSession.expires_at <= now,
                        OperatorSession.revoked_at <= now - timedelta(days=1),
                    )
                )
            ),
        )
        return result.rowcount or 0
