"""Tenant-scoped operational counters from durable PostgreSQL state."""

from fastapi import APIRouter, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.management import management_actor
from eventflow.models import Delivery, DeliveryAttempt, Event

router = APIRouter(prefix="/api/v1/management")


@router.get("/metrics")
async def metrics(request: Request) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        events = await session.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.organization_id == actor.organization_id)
        )
        delivery_rows = (
            await session.execute(
                select(Delivery.status, func.count())
                .where(Delivery.organization_id == actor.organization_id)
                .group_by(Delivery.status)
            )
        ).all()
        attempt_rows = (
            await session.execute(
                select(DeliveryAttempt.status, func.count())
                .where(DeliveryAttempt.organization_id == actor.organization_id)
                .group_by(DeliveryAttempt.status)
            )
        ).all()
        average_seconds = await session.scalar(
            select(
                func.avg(
                    func.extract("epoch", DeliveryAttempt.finished_at - DeliveryAttempt.started_at)
                )
            ).where(
                DeliveryAttempt.organization_id == actor.organization_id,
                DeliveryAttempt.finished_at.is_not(None),
            )
        )
    return {
        "events": events or 0,
        "deliveries": {status: count for status, count in delivery_rows},
        "attempts": {status: count for status, count in attempt_rows},
        "mean_attempt_duration_ms": (
            round(float(average_seconds) * 1000, 1) if average_seconds is not None else None
        ),
    }
