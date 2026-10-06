import asyncio
import os
import secrets
import uuid

import httpx
import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.app import app
from eventflow.ingest import hash_api_key
from eventflow.models import (
    ApiKey,
    Delivery,
    Endpoint,
    Event,
    Organization,
    OutboxMessage,
    Subscription,
)


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_concurrent_idempotency_conflict_and_tenant_scope() -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    app.state.engine = engine
    tenants = [uuid.uuid4(), uuid.uuid4()]
    endpoints = [uuid.uuid4(), uuid.uuid4()]
    keys = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Organization),
                [
                    {"id": tenant, "name": f"idempotency-{index}"}
                    for index, tenant in enumerate(tenants)
                ],
            )
            await connection.execute(
                insert(ApiKey),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": tenants[index],
                        "key_prefix": keys[index][:12],
                        "key_hash": hash_api_key(keys[index]),
                        "scope": "publish",
                    }
                    for index in range(2)
                ],
            )
            await connection.execute(
                insert(Endpoint),
                [
                    {
                        "id": endpoints[index],
                        "organization_id": tenants[index],
                        "url": "https://example.com/hook",
                        "signing_secret_ciphertext": b"fixture",
                        "active": True,
                    }
                    for index in range(2)
                ],
            )
            await connection.execute(
                insert(Subscription),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": tenants[index],
                        "endpoint_id": endpoints[index],
                        "event_type": "order.created",
                    }
                    for index in range(2)
                ],
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def publish(
                key: str, payload: dict[str, object], idempotency_key: str = "same-key"
            ) -> httpx.Response:
                return await client.post(
                    "/api/v1/events",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Idempotency-Key": idempotency_key,
                    },
                    json={"type": "order.created", "payload": payload},
                )

            first, second = await asyncio.gather(
                publish(keys[0], {"a": 1, "b": 2}),
                publish(keys[0], {"b": 2, "a": 1}),
            )
            assert first.status_code == second.status_code == 202
            assert first.json()["event_id"] == second.json()["event_id"]
            event_id = uuid.UUID(first.json()["event_id"])
            conflict = await publish(keys[0], {"a": 3})
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "idempotency_conflict"
            other_tenant = await publish(keys[1], {"a": 3})
            assert other_tenant.status_code == 202
            assert other_tenant.json()["event_id"] != str(event_id)
            racing_first, racing_second = await asyncio.gather(
                publish(keys[0], {"racing": 1}, "racing-conflict"),
                publish(keys[0], {"racing": 2}, "racing-conflict"),
            )
            assert sorted((racing_first.status_code, racing_second.status_code)) == [202, 409]
            invalid = await client.post(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {keys[0]}", "Idempotency-Key": "bad key"},
                json={"type": "order.created", "payload": {}},
            )
            assert invalid.status_code == 422
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.organization_id == tenants[0])
                )
                == 2
            )
            assert (
                await connection.scalar(
                    select(func.count()).select_from(Delivery).where(Delivery.event_id == event_id)
                )
                == 1
            )
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(OutboxMessage)
                    .where(OutboxMessage.organization_id == tenants[0])
                )
                == 2
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(OutboxMessage).where(OutboxMessage.organization_id.in_(tenants))
            )
            await connection.execute(delete(Delivery).where(Delivery.organization_id.in_(tenants)))
            await connection.execute(delete(Event).where(Event.organization_id.in_(tenants)))
            await connection.execute(
                delete(Subscription).where(Subscription.organization_id.in_(tenants))
            )
            await connection.execute(delete(Endpoint).where(Endpoint.organization_id.in_(tenants)))
            await connection.execute(delete(ApiKey).where(ApiKey.organization_id.in_(tenants)))
            await connection.execute(delete(Organization).where(Organization.id.in_(tenants)))
        await engine.dispose()
