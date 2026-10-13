"""Fixed demo publication through an operator session, without browser API keys."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.api import ApiError
from eventflow.config import get_settings
from eventflow.demo_observations import BridgeConfig, BridgeUnavailable, load_bridge_config
from eventflow.ingest import (
    DailyQuotaExceeded,
    DemoConfigurationError,
    PendingCapacityExceeded,
    ingest_event,
)
from eventflow.ingest_limits import admit_ingest
from eventflow.models import Delivery, Endpoint, Subscription
from eventflow.operator_session import authenticated_session

router = APIRouter(prefix="/api/v1/demo")
logger = logging.getLogger("eventflow.demo")
SCENARIOS = {
    "success": "demo.success",
    "transient": "demo.transient",
    "rate-limit": "demo.rate_limit",
    "replay": "demo.replay",
}


def demo_config() -> BridgeConfig:
    path = get_settings().demo_receiver_bridge_config_path
    if path is None:
        raise ApiError(503, "demo_unavailable", "Demo is not configured")
    try:
        return load_bridge_config(Path(path))
    except BridgeUnavailable:
        raise ApiError(503, "demo_unavailable", "Demo is not configured") from None


@router.get("/scenarios")
async def list_scenarios(request: Request) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        identity, _ = await authenticated_session(session, request)
        config = demo_config()
        if identity.organization_id != config.organization_id:
            raise ApiError(404, "not_found", "Demo not found")
        rows = (
            await session.execute(
                select(Endpoint.id, Endpoint.url, Endpoint.active, Subscription.event_type)
                .join(
                    Subscription,
                    (Subscription.endpoint_id == Endpoint.id)
                    & (Subscription.organization_id == Endpoint.organization_id),
                )
                .where(Endpoint.organization_id == identity.organization_id)
            )
        ).all()
    ready = {(row.id, row.url, row.event_type) for row in rows if row.active}
    return {
        "items": [
            {
                "id": route,
                "event_type": event_type,
                "ready": sum(
                    (endpoint_id, f"{config.origin}/hooks/{route}", event_type) in ready
                    for endpoint_id, configured_route in config.endpoints.items()
                    if configured_route == route
                )
                == 1
                and sum(row.event_type == event_type and row.active for row in rows) == 1,
            }
            for route, event_type in SCENARIOS.items()
        ]
    }


@router.post("/scenarios/{scenario}/events", status_code=202)
async def publish_scenario(request: Request, scenario: str) -> dict[str, str]:
    event_type = SCENARIOS.get(scenario)
    if event_type is None:
        raise ApiError(404, "not_found", "Demo scenario not found")
    async with AsyncSession(request.app.state.engine) as session:
        identity, _ = await authenticated_session(session, request, csrf=True)
    config = demo_config()
    if identity.organization_id != config.organization_id:
        raise ApiError(404, "not_found", "Demo not found")
    matching = [endpoint_id for endpoint_id, route in config.endpoints.items() if route == scenario]
    if len(matching) != 1:
        raise ApiError(503, "demo_unavailable", "Demo scenario is not configured")
    try:
        retry_after = await admit_ingest(request.app.state.redis, identity.organization_id)
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
    # Lock in the same operator-then-organization order used by management mutations.
    # Password rotation or logout cannot revoke this session between the final check
    # and the commit of an accepted event.
    async with AsyncSession(request.app.state.engine) as auth_session, auth_session.begin():
        current, _ = await authenticated_session(auth_session, request, csrf=True, lock=True)
        if current.id != identity.id or current.organization_id != config.organization_id:
            raise ApiError(401, "unauthorized", "A valid operator session is required")
        async with AsyncSession(request.app.state.engine) as session:
            try:
                event_id = await ingest_event(
                    session,
                    identity.organization_id,
                    event_type,
                    {"scenario": scenario, "source": "operator_demo"},
                    expected_endpoint=(matching[0], f"{config.origin}/hooks/{scenario}"),
                )
            except DemoConfigurationError:
                raise ApiError(503, "demo_unavailable", "Demo scenario is not configured") from None
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
            delivery_id = await session.scalar(
                select(Delivery.id).where(
                    Delivery.organization_id == identity.organization_id,
                    Delivery.event_id == event_id,
                    Delivery.endpoint_id == matching[0],
                )
            )
    assert isinstance(delivery_id, uuid.UUID)
    logger.info(
        "demo_event_accepted request_id=%s organization_id=%s event_id=%s delivery_id=%s",
        request.state.request_id,
        identity.organization_id,
        event_id,
        delivery_id,
    )
    return {"event_id": str(event_id), "delivery_id": str(delivery_id)}
