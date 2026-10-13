"""Tenant-authorized bridge from EventFlow to the external demo receiver."""

import asyncio
import ipaddress
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.api import ApiError
from eventflow.config import get_settings
from eventflow.management import management_actor
from eventflow.models import Delivery, Endpoint
from eventflow.webhook import UnsafeDestination, resolve_public, validated_destination

router = APIRouter(prefix="/api/v1/management")
MAX_OBSERVATION_BYTES = 32 * 1024
ROUTE_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
PUBLIC_HOST = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+\Z")


class BridgeUnavailable(Exception):
    pass


@dataclass(frozen=True)
class BridgeConfig:
    organization_id: uuid.UUID
    origin: str
    observation_token: str
    endpoints: dict[uuid.UUID, str]


class ReceiverGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID
    generation: StrictInt = Field(ge=1)
    request_count: StrictInt = Field(ge=1)
    signature_verified: StrictBool
    processed: StrictBool
    last_status: StrictInt = Field(ge=100, le=599)
    last_received_at: StrictInt = Field(ge=0)


class ReceiverObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delivery_id: uuid.UUID
    generations: list[ReceiverGeneration] = Field(max_length=100)


def load_bridge_config(path: Path) -> BridgeConfig:
    try:
        if not path.is_absolute() or path.stat().st_mode & 0o077:
            raise ValueError("Bridge configuration must be an owner-only absolute file")
        data = json.loads(path.read_text())
        organization_id = uuid.UUID(data["organization_id"])
        token = data["observation_token"]
        raw_origin = data["origin"]
        raw_endpoints = data["endpoints"]
        if not isinstance(token, str) or len(token) < 32 or not isinstance(raw_origin, str):
            raise ValueError("Invalid bridge credentials")
        origin_url = httpx.URL(raw_origin)
        host = origin_url.host
        if (
            origin_url.scheme != "https"
            or origin_url.port not in (None, 443)
            or host is None
            or not PUBLIC_HOST.fullmatch(host)
            or origin_url.username
            or origin_url.password
            or origin_url.path not in ("", "/")
            or origin_url.query
            or origin_url.fragment
            or "%" in raw_origin
        ):
            raise ValueError("Invalid receiver origin")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("Receiver origin cannot be an IP literal")
        if not isinstance(raw_endpoints, dict) or not raw_endpoints or len(raw_endpoints) > 20:
            raise ValueError("Invalid receiver endpoint map")
        endpoints: dict[uuid.UUID, str] = {}
        for endpoint_id, route in raw_endpoints.items():
            if not isinstance(route, str) or not ROUTE_NAME.fullmatch(route):
                raise ValueError("Invalid receiver route")
            endpoints[uuid.UUID(endpoint_id)] = route
        if len(endpoints) != len(raw_endpoints) or len(set(endpoints.values())) != len(endpoints):
            raise ValueError("Receiver routes must be unique")
        return BridgeConfig(organization_id, f"https://{host}", token, endpoints)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        httpx.InvalidURL,
        json.JSONDecodeError,
    ) as exc:
        raise BridgeUnavailable() from exc


def observation_transport() -> httpx.AsyncBaseTransport | None:
    """Test seam; production always uses HTTPX's verified network transport."""
    return None


async def fetch_receiver_observation(
    config: BridgeConfig,
    route: str,
    delivery_id: uuid.UUID,
    event_id: uuid.UUID,
    current_generation: int,
) -> dict[str, object]:
    raw_url = f"{config.origin}/observations/{route}/{delivery_id}"
    try:
        pinned_url, host = await asyncio.to_thread(validated_destination, raw_url, resolve_public)
    except (UnsafeDestination, OSError):
        raise ApiError(503, "receiver_unavailable", "Receiver observation is unavailable") from None
    async with httpx.AsyncClient(
        transport=observation_transport(),
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(connect=2, read=3, write=2, pool=1),
        http2=False,
    ) as client:
        request = client.build_request(
            "GET",
            pinned_url,
            headers={"Host": host, "Authorization": f"Bearer {config.observation_token}"},
        )
        request.extensions["sni_hostname"] = host
        try:
            response = await client.send(request, stream=True)
            try:
                if response.status_code != 200:
                    raise ApiError(
                        503, "receiver_unavailable", "Receiver observation is unavailable"
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_OBSERVATION_BYTES:
                        raise ApiError(
                            502, "receiver_invalid_response", "Receiver response is invalid"
                        )
            finally:
                await response.aclose()
        except httpx.HTTPError:
            raise ApiError(
                503, "receiver_unavailable", "Receiver observation is unavailable"
            ) from None
    try:
        observation = ReceiverObservation.model_validate_json(bytes(body))
    except ValidationError:
        raise ApiError(502, "receiver_invalid_response", "Receiver response is invalid") from None
    if (
        observation.delivery_id != delivery_id
        or any(
            item.event_id != event_id
            or item.generation > current_generation
            or not item.signature_verified
            for item in observation.generations
        )
        or len({item.generation for item in observation.generations})
        != len(observation.generations)
    ):
        raise ApiError(502, "receiver_invalid_response", "Receiver response is invalid")
    return observation.model_dump(mode="json")


@router.get("/deliveries/{delivery_id}/receiver-observation")
async def get_receiver_observation(request: Request, delivery_id: uuid.UUID) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        row = (
            await session.execute(
                select(Delivery, Endpoint.url)
                .join(
                    Endpoint,
                    and_(
                        Endpoint.id == Delivery.endpoint_id,
                        Endpoint.organization_id == Delivery.organization_id,
                    ),
                )
                .where(
                    Delivery.id == delivery_id, Delivery.organization_id == actor.organization_id
                )
            )
        ).one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Delivery not found")
    delivery, endpoint_url = row
    config_path = get_settings().demo_receiver_bridge_config_path
    if config_path is None:
        raise ApiError(503, "receiver_unavailable", "Receiver observation is unavailable")
    try:
        config = load_bridge_config(Path(config_path))
    except BridgeUnavailable:
        raise ApiError(503, "receiver_unavailable", "Receiver observation is unavailable") from None
    route = config.endpoints.get(delivery.endpoint_id)
    if (
        actor.organization_id != config.organization_id
        or route is None
        or endpoint_url != f"{config.origin}/hooks/{route}"
    ):
        raise ApiError(404, "not_found", "Receiver observation not found")
    return await fetch_receiver_observation(
        config, route, delivery.id, delivery.event_id, delivery.generation
    )
