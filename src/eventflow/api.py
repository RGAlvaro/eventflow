import json
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.config import get_settings
from eventflow.ingest import ingest_event, publishing_organization

router = APIRouter(prefix="/api/v1")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


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
    if request.headers.get("idempotency-key"):
        raise ApiError(422, "idempotency_unavailable", "Idempotency is not available yet")
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
        event_id = await ingest_event(session, organization_id, data.type, data.payload)
    return {"event_id": str(event_id), "request_id": str(request.state.request_id)}


def new_request_id() -> uuid.UUID:
    return uuid.uuid4()
