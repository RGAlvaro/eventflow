import json
import re
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.config import get_settings
from eventflow.ingest import (
    DailyQuotaExceeded,
    IdempotencyConflict,
    PendingCapacityExceeded,
    ingest_event,
    publishing_organization,
)
from eventflow.ingest_limits import admit_ingest

router = APIRouter(prefix="/api/v1")


class ApiError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
    )
    payload: dict[str, object]


def reject_non_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


async def bounded_body(request: Request) -> bytes:
    limit = get_settings().max_event_bytes
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise ApiError(413, "body_too_large", "Event body exceeds the configured limit")
    return bytes(body)


@router.post("/events", status_code=202)
async def publish_event(request: Request) -> dict[str, str]:
    authorization = request.headers.get("authorization", "")
    scheme, separator, raw_key = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not raw_key:
        raise ApiError(401, "unauthorized", "A publication API key is required")
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session:
        organization_id = await publishing_organization(session, raw_key)
        if organization_id is None:
            raise ApiError(401, "unauthorized", "A valid publication API key is required")
    try:
        retry_after = await admit_ingest(request.app.state.redis, organization_id)
    except RedisError:
        raise ApiError(
            503,
            "ingest_limit_unavailable",
            "Ingestion is temporarily unavailable",
            {"Retry-After": "5"},
        ) from None
    if retry_after is not None:
        raise ApiError(
            429,
            "ingest_rate_limited",
            "Organization ingestion rate exceeded",
            {"Retry-After": str(retry_after)},
        )
    idempotency_key = request.headers.get("idempotency-key")
    if idempotency_key is not None and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}", idempotency_key
    ):
        raise ApiError(422, "invalid_idempotency_key", "Idempotency-Key is invalid")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json")
    raw_body = await bounded_body(request)
    try:
        data = PublishRequest.model_validate(
            json.loads(raw_body, parse_constant=reject_non_json_constant)
        )
    except (ValueError, ValidationError):
        raise ApiError(422, "invalid_event", "Event type or payload is invalid") from None
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session:
        try:
            event_id = await ingest_event(
                session, organization_id, data.type, data.payload, idempotency_key
            )
        except IdempotencyConflict:
            raise ApiError(
                409, "idempotency_conflict", "Idempotency-Key was used for another event"
            ) from None
        except DailyQuotaExceeded as exc:
            raise ApiError(
                429,
                "ingest_daily_quota_exceeded",
                "Organization daily event quota exceeded",
                {"Retry-After": str(exc.retry_after)},
            ) from None
        except PendingCapacityExceeded:
            raise ApiError(
                503,
                "ingest_capacity_exhausted",
                "Organization delivery capacity exhausted",
                {"Retry-After": "5"},
            ) from None
    return {"event_id": str(event_id), "request_id": str(request.state.request_id)}


def new_request_id() -> uuid.UUID:
    return uuid.uuid4()
