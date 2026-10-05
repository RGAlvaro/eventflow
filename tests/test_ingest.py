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
async def test_ingest_commits_tenant_scoped_delivery_and_outbox_without_broker() -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    app.state.engine = engine
    app.state.redis = object()  # Broker unavailable: acceptance depends only on PostgreSQL.
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    endpoint_a, endpoint_b = uuid.uuid4(), uuid.uuid4()
    raw_key = secrets.token_urlsafe(32)
    async with engine.begin() as connection:
        await connection.execute(
            insert(Organization),
            [{"id": tenant_a, "name": "ingest-a"}, {"id": tenant_b, "name": "ingest-b"}],
        )
        await connection.execute(
            insert(ApiKey).values(
                id=uuid.uuid4(),
                organization_id=tenant_a,
                key_prefix=raw_key[:12],
                key_hash=hash_api_key(raw_key),
                scope="publish",
            )
        )
        await connection.execute(
            insert(Endpoint),
            [
                {
                    "id": endpoint_a,
                    "organization_id": tenant_a,
                    "url": "https://example.com/a",
                    "signing_secret_ciphertext": b"fixture-only",
                    "active": True,
                },
                {
                    "id": endpoint_b,
                    "organization_id": tenant_b,
                    "url": "https://example.com/b",
                    "signing_secret_ciphertext": b"fixture-only",
                    "active": True,
                },
            ],
        )
        await connection.execute(
            insert(Subscription),
            [
                {
                    "id": uuid.uuid4(),
                    "organization_id": tenant_a,
                    "endpoint_id": endpoint_a,
                    "event_type": "order.created",
                },
                {
                    "id": uuid.uuid4(),
                    "organization_id": tenant_b,
                    "endpoint_id": endpoint_b,
                    "event_type": "order.created",
                },
            ],
        )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": f"Bearer {raw_key}"}
            accepted = await client.post(
                "/api/v1/events",
                headers=headers,
                json={"type": "order.created", "payload": {"order_id": "o-1"}},
            )
            assert accepted.status_code == 202
            assert accepted.headers["X-Request-Id"] == accepted.json()["request_id"]
            event_id = uuid.UUID(accepted.json()["event_id"])
            unauthorized = await client.post(
                "/api/v1/events",
                headers={"Authorization": "Bearer invalid"},
                json={"type": "order.created", "payload": {}},
            )
            assert unauthorized.status_code == 401
            assert unauthorized.json()["code"] == "unauthorized"
            invalid = await client.post(
                "/api/v1/events",
                headers={**headers, "Content-Type": "application/json"},
                content=b'{"type":"Order.Created","payload":{}}',
            )
            assert invalid.status_code == 422
            non_json = await client.post(
                "/api/v1/events",
                headers={**headers, "Content-Type": "application/json"},
                content=b'{"type":"order.created","payload":{"x":NaN}}',
            )
            assert non_json.status_code == 422
            oversized = await client.post(
                "/api/v1/events",
                headers={**headers, "Content-Type": "application/json"},
                content=b"{" + b" " * (256 * 1024) + b"}",
            )
            assert oversized.status_code == 413
        async with engine.connect() as connection:
            event = (await connection.execute(select(Event).where(Event.id == event_id))).one()
            assert event.organization_id == tenant_a
            delivery = (
                await connection.execute(select(Delivery).where(Delivery.event_id == event_id))
            ).one()
            assert delivery.organization_id == tenant_a
            assert delivery.endpoint_id == endpoint_a
            outbox_count = await connection.scalar(
                select(func.count())
                .select_from(OutboxMessage)
                .where(
                    OutboxMessage.delivery_id == delivery.id,
                    OutboxMessage.organization_id == tenant_a,
                )
            )
            assert outbox_count == 1
            event_count = await connection.scalar(
                select(func.count()).select_from(Event).where(Event.organization_id == tenant_a)
            )
            assert event_count == 1
    finally:
        async with engine.begin() as connection:
            tenant_ids = [tenant_a, tenant_b]
            await connection.execute(
                delete(OutboxMessage).where(OutboxMessage.organization_id.in_(tenant_ids))
            )
            await connection.execute(
                delete(Delivery).where(Delivery.organization_id.in_(tenant_ids))
            )
            await connection.execute(delete(Event).where(Event.organization_id.in_(tenant_ids)))
            await connection.execute(
                delete(Subscription).where(Subscription.organization_id.in_(tenant_ids))
            )
            await connection.execute(
                delete(Endpoint).where(Endpoint.organization_id.in_(tenant_ids))
            )
            await connection.execute(delete(ApiKey).where(ApiKey.organization_id.in_(tenant_ids)))
            await connection.execute(delete(Organization).where(Organization.id.in_(tenant_ids)))
        await engine.dispose()
