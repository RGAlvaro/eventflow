"""Tenant-scoped, keyset-paginated read API for the operator."""

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.api import ApiError
from eventflow.management import management_actor
from eventflow.models import Delivery, DeliveryAttempt, Endpoint, Event

router = APIRouter(prefix="/api/v1/management")
PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DELIVERY_STATUSES = frozenset(
    {"pending", "processing", "retry_scheduled", "succeeded", "dead_lettered"}
)


def encode_cursor(at: datetime, row_id: uuid.UUID, context: str) -> str:
    data = json.dumps(
        {"v": 1, "at": at.isoformat(), "id": str(row_id), "context": context},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None, context: str) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    if len(cursor) > 1024:
        raise ApiError(422, "invalid_cursor", "Pagination cursor is invalid")
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        data = json.loads(raw)
        if (
            not isinstance(data, dict)
            or set(data) != {"v", "at", "id", "context"}
            or data["v"] != 1
            or data["context"] != context
        ):
            raise ValueError("Cursor context mismatch")
        at = datetime.fromisoformat(data["at"])
        row_id = uuid.UUID(data["id"])
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Cursor timestamp lacks timezone")
        return at, row_id
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, binascii.Error):
        raise ApiError(422, "invalid_cursor", "Pagination cursor is invalid") from None


def older_than(at_column: Any, id_column: Any, position: tuple[datetime, uuid.UUID]) -> Any:
    at, row_id = position
    return or_(at_column < at, and_(at_column == at, id_column < row_id))


def event_item(event: Event) -> dict[str, object]:
    return {
        "id": str(event.id),
        "type": event.event_type,
        "created_at": event.created_at,
        "terminal_at": event.terminal_at,
    }


def delivery_item(delivery: Delivery, pause_until: datetime | None) -> dict[str, object]:
    return {
        "id": str(delivery.id),
        "event_id": str(delivery.event_id),
        "endpoint_id": str(delivery.endpoint_id),
        "status": delivery.status,
        "generation": delivery.generation,
        "attempt_count": delivery.attempt_count,
        "next_attempt_at": delivery.next_attempt_at,
        "lease_expires_at": delivery.lease_expires_at,
        "endpoint_pause_until": pause_until,
        "created_at": delivery.created_at,
    }


def attempt_item(attempt: DeliveryAttempt) -> dict[str, object]:
    return {
        "id": str(attempt.id),
        "delivery_id": str(attempt.delivery_id),
        "number": attempt.number,
        "generation": attempt.generation,
        "status": attempt.status,
        "response_status": attempt.response_status,
        "error_category": attempt.error_category,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
    }


@router.get("/events")
async def list_events(
    request: Request,
    limit: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = None,
    event_type: str | None = Query(default=None, min_length=1, max_length=100),
) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        context = f"events:{actor.organization_id}:{event_type or ''}"
        position = decode_cursor(cursor, context)
        query = select(Event).where(Event.organization_id == actor.organization_id)
        if event_type is not None:
            query = query.where(Event.event_type == event_type)
        if position is not None:
            query = query.where(older_than(Event.created_at, Event.id, position))
        rows = (
            await session.scalars(
                query.order_by(Event.created_at.desc(), Event.id.desc()).limit(limit + 1)
            )
        ).all()
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1].created_at, page[-1].id, context) if len(rows) > limit else None
    )
    return {"items": [event_item(item) for item in page], "next_cursor": next_cursor}


@router.get("/events/{event_id}")
async def get_event(request: Request, event_id: uuid.UUID) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        event = await session.scalar(
            select(Event).where(
                Event.id == event_id, Event.organization_id == actor.organization_id
            )
        )
        if event is None:
            raise ApiError(404, "not_found", "Event not found")
        return {**event_item(event), "payload": event.payload}


@router.get("/deliveries")
async def list_deliveries(
    request: Request,
    limit: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = None,
    event_id: uuid.UUID | None = None,
    status: str | None = None,
) -> dict[str, object]:
    if status is not None and status not in DELIVERY_STATUSES:
        raise ApiError(422, "invalid_status", "Delivery status is invalid")
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        context = f"deliveries:{actor.organization_id}:{event_id or ''}:{status or ''}"
        position = decode_cursor(cursor, context)
        query = (
            select(Delivery, Endpoint.pause_until)
            .join(
                Endpoint,
                and_(
                    Endpoint.id == Delivery.endpoint_id,
                    Endpoint.organization_id == Delivery.organization_id,
                ),
            )
            .where(Delivery.organization_id == actor.organization_id)
        )
        if event_id is not None:
            query = query.where(Delivery.event_id == event_id)
        if status is not None:
            query = query.where(Delivery.status == status)
        if position is not None:
            query = query.where(older_than(Delivery.created_at, Delivery.id, position))
        rows = (
            await session.execute(
                query.order_by(Delivery.created_at.desc(), Delivery.id.desc()).limit(limit + 1)
            )
        ).all()
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1][0].created_at, page[-1][0].id, context)
        if len(rows) > limit
        else None
    )
    return {
        "items": [delivery_item(delivery, pause_until) for delivery, pause_until in page],
        "next_cursor": next_cursor,
    }


@router.get("/deliveries/{delivery_id}")
async def get_delivery(request: Request, delivery_id: uuid.UUID) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        row = (
            await session.execute(
                select(Delivery, Endpoint.pause_until)
                .join(
                    Endpoint,
                    and_(
                        Endpoint.id == Delivery.endpoint_id,
                        Endpoint.organization_id == Delivery.organization_id,
                    ),
                )
                .where(
                    Delivery.id == delivery_id,
                    Delivery.organization_id == actor.organization_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise ApiError(404, "not_found", "Delivery not found")
        return delivery_item(row[0], row[1])


@router.get("/deliveries/{delivery_id}/attempts")
async def list_attempts(
    request: Request,
    delivery_id: uuid.UUID,
    limit: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = None,
) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        delivery = await session.scalar(
            select(Delivery.id).where(
                Delivery.id == delivery_id, Delivery.organization_id == actor.organization_id
            )
        )
        if delivery is None:
            raise ApiError(404, "not_found", "Delivery not found")
        context = f"attempts:{actor.organization_id}:{delivery_id}"
        position = decode_cursor(cursor, context)
        query = select(DeliveryAttempt).where(
            DeliveryAttempt.organization_id == actor.organization_id,
            DeliveryAttempt.delivery_id == delivery_id,
        )
        if position is not None:
            query = query.where(
                older_than(DeliveryAttempt.started_at, DeliveryAttempt.id, position)
            )
        rows = (
            await session.scalars(
                query.order_by(DeliveryAttempt.started_at.desc(), DeliveryAttempt.id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1].started_at, page[-1].id, context) if len(rows) > limit else None
    )
    return {"items": [attempt_item(item) for item in page], "next_cursor": next_cursor}
