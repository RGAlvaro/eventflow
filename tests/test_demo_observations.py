import ipaddress
import json
import os
import secrets
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import create_async_engine

import eventflow.demo_observations as bridge
from eventflow.api import ApiError
from eventflow.app import app
from eventflow.config import get_settings
from eventflow.delivery import ClaimedDelivery
from eventflow.demo_receiver import ReceiverConfig, Route, SigningKey, create_app
from eventflow.ingest import hash_api_key
from eventflow.models import ApiKey, Delivery, Endpoint, Event, Organization
from eventflow.webhook import signed_request
from tests.support import clean_organizations, sealed_secret

SECRET = bytes(range(32))
TOKEN = "server-only-token-012345678901234567890123"
ORIGIN = "https://receiver.example.org"


class CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self, target: httpx.AsyncBaseTransport) -> None:
        self.target = target
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return await self.target.handle_async_request(request)


def write_bridge_config(
    path: Path,
    organization_id: uuid.UUID,
    endpoints: dict[uuid.UUID, str],
    origin: str = ORIGIN,
) -> None:
    path.write_text(
        json.dumps(
            {
                "organization_id": str(organization_id),
                "origin": origin,
                "observation_token": TOKEN,
                "endpoints": {str(key): value for key, value in endpoints.items()},
            }
        )
    )
    path.chmod(0o600)


@pytest.mark.parametrize(
    "origin",
    [
        "http://receiver.example.org",
        "https://127.0.0.1",
        "https://receiver.example.org:8443",
        "https://user@receiver.example.org",
        "https://receiver.example.org/path",
        "https://receiver.example.org?x=1",
        "https://receiver.example.org%2F.evil.test",
    ],
)
def test_bridge_config_rejects_untrusted_origin(tmp_path: Path, origin: str) -> None:
    path = tmp_path / "bridge.json"
    write_bridge_config(path, uuid.uuid4(), {uuid.uuid4(): "success"}, origin)
    with pytest.raises(bridge.BridgeUnavailable):
        bridge.load_bridge_config(path)


def test_bridge_config_rejects_broad_permissions_and_reused_route(tmp_path: Path) -> None:
    path = tmp_path / "bridge.json"
    write_bridge_config(path, uuid.uuid4(), {uuid.uuid4(): "success"})
    path.chmod(0o644)
    with pytest.raises(bridge.BridgeUnavailable):
        bridge.load_bridge_config(path)
    write_bridge_config(
        path,
        uuid.uuid4(),
        {
            uuid.uuid4(): "success",
            uuid.uuid4(): "success",
        },
    )
    with pytest.raises(bridge.BridgeUnavailable):
        bridge.load_bridge_config(path)


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_receiver_observation_requires_tenant_and_fixed_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    app.state.engine = engine
    tenant, other_tenant = uuid.uuid4(), uuid.uuid4()
    endpoint_id, unconfigured_endpoint, other_endpoint = [uuid.uuid4() for _ in range(3)]
    event_id, unconfigured_event, other_event = [uuid.uuid4() for _ in range(3)]
    delivery_id, unconfigured_delivery, other_delivery = [uuid.uuid4() for _ in range(3)]
    manage_key, publish_key, other_manage_key = [secrets.token_urlsafe(32) for _ in range(3)]
    config_path = tmp_path / "bridge.json"
    write_bridge_config(config_path, tenant, {endpoint_id: "success"})
    monkeypatch.setenv("EVENTFLOW_DEMO_RECEIVER_BRIDGE_CONFIG_PATH", str(config_path))
    get_settings.cache_clear()
    receiver = create_app(
        ReceiverConfig(
            {"success": Route("success", {1: SigningKey(SECRET)})},
            TOKEN,
            tmp_path / "receiver.sqlite",
        )
    )
    receiver_transport = CountingTransport(httpx.ASGITransport(app=receiver))
    monkeypatch.setattr(bridge, "observation_transport", lambda: receiver_transport)
    monkeypatch.setattr(bridge, "resolve_public", lambda _host: [ipaddress.ip_address("8.8.8.8")])
    claim = ClaimedDelivery(
        delivery_id,
        tenant,
        uuid.uuid4(),
        uuid.uuid4(),
        event_id,
        1,
        "order.created",
        {"private": "payload-marker"},
        f"{ORIGIN}/hooks/success",
        SECRET,
    )
    body, headers = signed_request(claim)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=receiver), base_url=ORIGIN
    ) as client:
        assert (
            await client.post("/hooks/success", content=body, headers=headers)
        ).status_code == 200
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Organization),
                [
                    {"id": tenant, "name": "receiver-bridge"},
                    {"id": other_tenant, "name": "receiver-bridge-other"},
                ],
            )
            await connection.execute(
                insert(ApiKey),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": org,
                        "key_prefix": key[:12],
                        "key_hash": hash_api_key(key),
                        "scope": scope,
                    }
                    for org, key, scope in (
                        (tenant, manage_key, "manage"),
                        (tenant, publish_key, "publish"),
                        (other_tenant, other_manage_key, "manage"),
                    )
                ],
            )
            for org, endpoint in (
                (tenant, endpoint_id),
                (tenant, unconfigured_endpoint),
                (other_tenant, other_endpoint),
            ):
                await connection.execute(
                    insert(Endpoint).values(
                        id=endpoint,
                        organization_id=org,
                        url=f"{ORIGIN}/hooks/success",
                        active=True,
                        **sealed_secret(SECRET, org, endpoint),
                    )
                )
            for org, event in (
                (tenant, event_id),
                (tenant, unconfigured_event),
                (other_tenant, other_event),
            ):
                await connection.execute(
                    insert(Event).values(
                        id=event,
                        organization_id=org,
                        event_type="order.created",
                        payload={},
                    )
                )
            for org, delivery, event, endpoint in (
                (tenant, delivery_id, event_id, endpoint_id),
                (tenant, unconfigured_delivery, unconfigured_event, unconfigured_endpoint),
                (other_tenant, other_delivery, other_event, other_endpoint),
            ):
                await connection.execute(
                    insert(Delivery).values(
                        id=delivery,
                        organization_id=org,
                        event_id=event,
                        endpoint_id=endpoint,
                        status="succeeded",
                        generation=1,
                        attempt_count=1,
                    )
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = f"/api/v1/management/deliveries/{delivery_id}/receiver-observation"
            own = {"Authorization": f"Bearer {manage_key}"}
            foreign = {"Authorization": f"Bearer {other_manage_key}"}
            publish = {"Authorization": f"Bearer {publish_key}"}
            assert (await client.get(path, headers=publish)).status_code == 401
            assert (await client.get(path, headers=foreign)).status_code == 404
            assert (
                await client.get(
                    f"/api/v1/management/deliveries/{other_delivery}/receiver-observation",
                    headers=own,
                )
            ).status_code == 404
            assert (
                await client.get(
                    f"/api/v1/management/deliveries/{unconfigured_delivery}/receiver-observation",
                    headers=own,
                )
            ).status_code == 404
            assert receiver_transport.requests == []
            response = await client.get(path, headers=own)
            assert response.status_code == 200
            assert response.json()["generations"][0]["signature_verified"] is True
            assert response.json()["generations"][0]["event_id"] == str(event_id)
            assert response.headers["Cache-Control"] == "no-store"
            assert TOKEN not in response.text and "payload-marker" not in response.text
            outbound = receiver_transport.requests[0]
            assert str(outbound.url) == f"https://8.8.8.8/observations/success/{delivery_id}"
            assert outbound.headers["Host"] == "receiver.example.org"
            assert outbound.headers["Authorization"] == f"Bearer {TOKEN}"
            assert outbound.extensions["sni_hostname"] == "receiver.example.org"
            assert len(receiver_transport.requests) == 1
            async with engine.begin() as connection:
                await connection.execute(
                    update(Endpoint)
                    .where(Endpoint.id == endpoint_id)
                    .values(url="https://other.example.org/hook")
                )
            assert (await client.get(path, headers=own)).status_code == 404
            assert len(receiver_transport.requests) == 1
    finally:
        await clean_organizations(engine, [tenant, other_tenant])
        await engine.dispose()
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (302, b"", 503),
        (200, b"not-json", 502),
        (200, b"x" * (32 * 1024 + 1), 502),
        (
            200,
            json.dumps(
                {
                    "delivery_id": str(uuid.uuid4()),
                    "generations": [],
                }
            ).encode(),
            502,
        ),
    ],
)
async def test_receiver_bridge_rejects_bad_upstream_response(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: bytes,
    expected: int,
) -> None:
    config = bridge.BridgeConfig(uuid.uuid4(), ORIGIN, TOKEN, {uuid.uuid4(): "success"})
    delivery_id, event_id = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(bridge, "resolve_public", lambda _host: [ipaddress.ip_address("8.8.8.8")])
    monkeypatch.setattr(
        bridge,
        "observation_transport",
        lambda: httpx.MockTransport(
            lambda request: httpx.Response(status, content=body, request=request)
        ),
    )
    with pytest.raises(ApiError) as exc:
        await bridge.fetch_receiver_observation(config, "success", delivery_id, event_id, 1)
    assert exc.value.status_code == expected


async def test_receiver_bridge_rejects_foreign_event_and_future_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = bridge.BridgeConfig(uuid.uuid4(), ORIGIN, TOKEN, {uuid.uuid4(): "success"})
    delivery_id, event_id = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(bridge, "resolve_public", lambda _host: [ipaddress.ip_address("8.8.8.8")])
    for observed_event, generation in ((uuid.uuid4(), 1), (event_id, 2)):
        body = json.dumps(
            {
                "delivery_id": str(delivery_id),
                "generations": [
                    {
                        "event_id": str(observed_event),
                        "generation": generation,
                        "request_count": 1,
                        "signature_verified": True,
                        "processed": True,
                        "last_status": 200,
                        "last_received_at": 1,
                    }
                ],
            }
        ).encode()
        monkeypatch.setattr(
            bridge,
            "observation_transport",
            lambda fixed_body=body: httpx.MockTransport(
                lambda request: httpx.Response(200, content=fixed_body, request=request)
            ),
        )
        with pytest.raises(ApiError) as exc:
            await bridge.fetch_receiver_observation(config, "success", delivery_id, event_id, 1)
        assert exc.value.status_code == 502


async def test_receiver_bridge_timeout_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    config = bridge.BridgeConfig(uuid.uuid4(), ORIGIN, TOKEN, {uuid.uuid4(): "success"})
    monkeypatch.setattr(bridge, "resolve_public", lambda _host: [ipaddress.ip_address("8.8.8.8")])

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timed out")

    monkeypatch.setattr(bridge, "observation_transport", lambda: httpx.MockTransport(timeout))
    with pytest.raises(ApiError) as exc:
        await bridge.fetch_receiver_observation(config, "success", uuid.uuid4(), uuid.uuid4(), 1)
    assert exc.value.status_code == 503
    assert TOKEN not in exc.value.message


async def test_receiver_bridge_rejects_private_dns_without_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = bridge.BridgeConfig(uuid.uuid4(), ORIGIN, TOKEN, {uuid.uuid4(): "success"})
    monkeypatch.setattr(bridge, "resolve_public", lambda _host: [ipaddress.ip_address("127.0.0.1")])
    called = False

    def transport() -> httpx.AsyncBaseTransport:
        nonlocal called
        called = True
        return httpx.MockTransport(lambda _request: httpx.Response(200))

    monkeypatch.setattr(bridge, "observation_transport", transport)
    with pytest.raises(ApiError) as exc:
        await bridge.fetch_receiver_observation(config, "success", uuid.uuid4(), uuid.uuid4(), 1)
    assert exc.value.status_code == 503
    assert called is False
