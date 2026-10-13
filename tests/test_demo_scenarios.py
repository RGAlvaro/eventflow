import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.app import app
from eventflow.config import get_settings
from eventflow.delivery import make_sync_engine
from eventflow.models import Delivery, Endpoint, Event, Organization, OutboxMessage, Subscription
from eventflow.operator_admin import create_operator
from tests.support import clean_organizations, sealed_secret


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_demo_scenario_requires_session_csrf_tenant_and_exact_subscription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    sync_engine = make_sync_engine()
    redis = Redis.from_url(os.environ["EVENTFLOW_REDIS_URL"])
    app.state.engine, app.state.redis = engine, redis
    tenant, other_tenant = uuid.uuid4(), uuid.uuid4()
    endpoint_id, stray_endpoint_id = uuid.uuid4(), uuid.uuid4()
    username = "scenario-" + uuid.uuid4().hex[:12]
    other_username = "scenario-" + uuid.uuid4().hex[:12]
    config_path = tmp_path / "bridge.json"
    config_path.write_text(
        json.dumps(
            {
                "organization_id": str(tenant),
                "origin": "https://receiver.example.org",
                "observation_token": "example-token-012345678901234567890123",
                "endpoints": {str(endpoint_id): "success"},
            }
        )
    )
    config_path.chmod(0o600)
    monkeypatch.setenv("EVENTFLOW_DEMO_RECEIVER_BRIDGE_CONFIG_PATH", str(config_path))
    get_settings.cache_clear()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Organization),
                [{"id": tenant, "name": "scenario-a"}, {"id": other_tenant, "name": "scenario-b"}],
            )
            for endpoint in (endpoint_id, stray_endpoint_id):
                await connection.execute(
                    insert(Endpoint).values(
                        id=endpoint,
                        organization_id=tenant,
                        url=(
                            "https://receiver.example.org/hooks/success"
                            if endpoint == endpoint_id
                            else "https://other.example.org/hook"
                        ),
                        active=True,
                        **sealed_secret(b"fixture", tenant, endpoint),
                    )
                )
            await connection.execute(
                insert(Subscription).values(
                    id=uuid.uuid4(),
                    organization_id=tenant,
                    endpoint_id=endpoint_id,
                    event_type="demo.success",
                )
            )
        _, password = create_operator(sync_engine, tenant, username)
        _, other_password = create_operator(sync_engine, other_tenant, other_username)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client:
            route = "/api/v1/demo/scenarios/success/events"
            assert (await client.post(route)).status_code == 401
            login = await client.post(
                "/api/v1/session/login", json={"username": username, "password": password}
            )
            assert login.status_code == 200
            csrf = client.cookies["eventflow_csrf"]
            assert (await client.post(route)).status_code == 403
            scenarios = await client.get("/api/v1/demo/scenarios")
            assert scenarios.status_code == 200
            assert scenarios.json()["items"][0] == {
                "id": "success",
                "event_type": "demo.success",
                "ready": True,
            }
            headers = {"X-CSRF-Token": csrf}
            accepted = await client.post(route, headers=headers)
            assert accepted.status_code == 202, accepted.text
            event_id = uuid.UUID(accepted.json()["event_id"])
            delivery_id = uuid.UUID(accepted.json()["delivery_id"])
            async with engine.connect() as connection:
                event_tenant = await connection.scalar(
                    select(Event.organization_id).where(Event.id == event_id)
                )
                delivery_endpoint = await connection.scalar(
                    select(Delivery.endpoint_id).where(Delivery.id == delivery_id)
                )
                outbox_id = await connection.scalar(
                    select(OutboxMessage.id).where(OutboxMessage.delivery_id == delivery_id)
                )
                assert event_tenant == tenant
                assert delivery_endpoint == endpoint_id
                assert outbox_id is not None
            summary = await client.get("/api/v1/management/metrics")
            assert summary.status_code == 200
            assert summary.json()["events"] == 1
            assert summary.json()["deliveries"] == {"pending": 1}
            await client.post(
                "/api/v1/session/login",
                json={"username": other_username, "password": other_password},
            )
            assert (await client.get("/api/v1/demo/scenarios")).status_code == 404
            assert (await client.get("/api/v1/management/metrics")).json()["events"] == 0
            assert (
                await client.post(route, headers={"X-CSRF-Token": client.cookies["eventflow_csrf"]})
            ).status_code == 404
            await client.post(
                "/api/v1/session/login", json={"username": username, "password": password}
            )
            headers = {"X-CSRF-Token": client.cookies["eventflow_csrf"]}
            async with engine.begin() as connection:
                await connection.execute(
                    insert(Subscription).values(
                        id=uuid.uuid4(),
                        organization_id=tenant,
                        endpoint_id=stray_endpoint_id,
                        event_type="demo.success",
                    )
                )
            rejected = await client.post(route, headers=headers)
            assert rejected.status_code == 503
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(
                        select(func.count())
                        .select_from(Event)
                        .where(Event.organization_id == tenant, Event.event_type == "demo.success")
                    )
                    == 1
                )
            async with engine.begin() as connection:
                await connection.execute(
                    update(Endpoint)
                    .where(Endpoint.id == endpoint_id)
                    .values(url="https://other.example.org/hook")
                )
            assert (await client.post(route, headers=headers)).status_code == 503
    finally:
        await clean_organizations(engine, [tenant, other_tenant])
        await redis.aclose()
        await engine.dispose()
        sync_engine.dispose()
        get_settings.cache_clear()
