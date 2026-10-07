import asyncio
import os
import secrets
import uuid

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.app import app
from eventflow.ingest import hash_api_key
from eventflow.ingest_limits import admit_ingest
from eventflow.models import (
    ApiKey,
    Delivery,
    Endpoint,
    Event,
    Organization,
    OutboxMessage,
    Subscription,
)
from tests.support import clean_organizations, sealed_secret


@pytest.mark.skipif(not os.getenv("EVENTFLOW_REDIS_URL"), reason="Redis integration URL unset")
async def test_token_bucket_is_shared_under_concurrent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("eventflow.ingest_limits.BURST_TOKENS", 2)
    monkeypatch.setattr("eventflow.ingest_limits.TOKENS_PER_SECOND", 1)
    redis = Redis.from_url(os.environ["EVENTFLOW_REDIS_URL"])
    tenant = uuid.uuid4()
    try:
        results = await asyncio.gather(*(admit_ingest(redis, tenant) for _ in range(3)))
        assert results.count(None) == 2
        assert results.count(1) == 1
    finally:
        await redis.delete(f"eventflow:ingest:{tenant}")
        await redis.aclose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_daily_quota_idempotency_and_capacity_are_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    redis = Redis.from_url(os.getenv("EVENTFLOW_REDIS_URL", "redis://localhost:6379/0"))
    app.state.engine, app.state.redis = engine, redis
    daily_tenant, capacity_tenant = uuid.uuid4(), uuid.uuid4()
    endpoint_id = uuid.uuid4()
    daily_key, capacity_key = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Organization),
                [
                    {"id": daily_tenant, "name": "daily"},
                    {"id": capacity_tenant, "name": "capacity"},
                ],
            )
            await connection.execute(
                insert(ApiKey),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": tenant,
                        "key_prefix": key[:12],
                        "key_hash": hash_api_key(key),
                        "scope": "publish",
                    }
                    for tenant, key in ((daily_tenant, daily_key), (capacity_tenant, capacity_key))
                ],
            )
            await connection.execute(
                insert(Endpoint).values(
                    id=endpoint_id,
                    organization_id=capacity_tenant,
                    url="https://example.com/hook",
                    active=True,
                    **sealed_secret(b"fixture", capacity_tenant, endpoint_id),
                )
            )
            await connection.execute(
                insert(Subscription).values(
                    id=uuid.uuid4(),
                    organization_id=capacity_tenant,
                    endpoint_id=endpoint_id,
                    event_type="order.created",
                )
            )
        monkeypatch.setattr("eventflow.ingest.DAILY_EVENTS", 2)
        monkeypatch.setattr("eventflow.ingest.PENDING_DELIVERIES", 1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def publish(key: str, idempotency: str) -> httpx.Response:
                return await client.post(
                    "/api/v1/events",
                    headers={"Authorization": f"Bearer {key}", "Idempotency-Key": idempotency},
                    json={"type": "order.created", "payload": {}},
                )

            first = await publish(daily_key, "one")
            second = await publish(daily_key, "two")
            limited = await publish(daily_key, "three")
            repeated = await publish(daily_key, "one")
            assert first.status_code == second.status_code == repeated.status_code == 202
            assert repeated.json()["event_id"] == first.json()["event_id"]
            assert limited.status_code == 429
            assert limited.json()["code"] == "ingest_daily_quota_exceeded"
            assert int(limited.headers["Retry-After"]) > 0
            capacity_first = await publish(capacity_key, "one")
            capacity_denied = await publish(capacity_key, "two")
            capacity_repeat = await publish(capacity_key, "one")
            assert capacity_first.status_code == capacity_repeat.status_code == 202
            assert capacity_denied.status_code == 503
            assert capacity_denied.json()["code"] == "ingest_capacity_exhausted"
            assert capacity_denied.headers["Retry-After"] == "5"
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.organization_id == daily_tenant)
                )
                == 2
            )
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.organization_id == capacity_tenant)
                )
                == 1
            )
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(Delivery)
                    .where(Delivery.organization_id == capacity_tenant)
                )
                == 1
            )
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(OutboxMessage)
                    .where(OutboxMessage.organization_id == capacity_tenant)
                )
                == 1
            )
    finally:
        await clean_organizations(engine, [daily_tenant, capacity_tenant])
        await engine.dispose()
        await redis.aclose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_redis_failure_rejects_before_event_commit() -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    broken_redis = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.1)
    app.state.engine, app.state.redis = engine, broken_redis
    tenant = uuid.uuid4()
    key = secrets.token_urlsafe(32)
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(Organization).values(id=tenant, name="redis-down"))
            await connection.execute(
                insert(ApiKey).values(
                    id=uuid.uuid4(),
                    organization_id=tenant,
                    key_prefix=key[:12],
                    key_hash=hash_api_key(key),
                    scope="publish",
                )
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {key}"},
                json={"type": "order.created", "payload": {}},
            )
            assert response.status_code == 503
            assert response.headers["Retry-After"] == "5"
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    select(func.count()).select_from(Event).where(Event.organization_id == tenant)
                )
                == 0
            )
    finally:
        await clean_organizations(engine, [tenant])
        await engine.dispose()
        await broken_redis.aclose()
