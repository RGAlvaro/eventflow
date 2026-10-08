import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.app import app
from eventflow.delivery import make_sync_engine
from eventflow.ingest import hash_api_key
from eventflow.models import (
    ApiKey,
    Delivery,
    Endpoint,
    Event,
    ManagementAudit,
    Operator,
    OperatorSession,
    Organization,
    ReplayAudit,
)
from eventflow.operator_admin import change_operator, create_operator
from eventflow.operator_password import hash_password, verify_password
from eventflow.operator_session import CSRF_COOKIE, session_cookie_name, token_hash
from tests.support import clean_organizations, sealed_secret


def test_operator_password_hash_is_salted_and_checks_password() -> None:
    first = hash_password("example-password")
    second = hash_password("example-password")
    assert first != second
    assert "example-password" not in first
    assert verify_password("example-password", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("example-password", "invalid")


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_operator_cookie_csrf_tenant_audit_logout_and_rotation() -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    sync_engine = make_sync_engine()
    redis = Redis.from_url(os.environ["EVENTFLOW_REDIS_URL"])
    app.state.engine, app.state.redis = engine, redis
    tenant, other_tenant = uuid.uuid4(), uuid.uuid4()
    endpoint_id, other_endpoint_id = uuid.uuid4(), uuid.uuid4()
    event_id, other_event = uuid.uuid4(), uuid.uuid4()
    delivery_id, other_delivery = uuid.uuid4(), uuid.uuid4()
    username = "demo-" + uuid.uuid4().hex[:12]
    manage_key = secrets.token_urlsafe(32)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Organization),
                [{"id": tenant, "name": "session-a"}, {"id": other_tenant, "name": "session-b"}],
            )
            await connection.execute(
                insert(ApiKey).values(
                    id=uuid.uuid4(),
                    organization_id=tenant,
                    key_prefix=manage_key[:12],
                    key_hash=hash_api_key(manage_key),
                    scope="manage",
                )
            )
            for org, endpoint, event, delivery in (
                (tenant, endpoint_id, event_id, delivery_id),
                (other_tenant, other_endpoint_id, other_event, other_delivery),
            ):
                await connection.execute(
                    insert(Endpoint).values(
                        id=endpoint,
                        organization_id=org,
                        url="https://example.com/hook",
                        active=True,
                        **sealed_secret(b"fixture", org, endpoint),
                    )
                )
                await connection.execute(
                    insert(Event).values(
                        id=event,
                        organization_id=org,
                        event_type="order.created",
                        payload={"private": "tenant-data"},
                    )
                )
                await connection.execute(
                    insert(Delivery).values(
                        id=delivery,
                        organization_id=org,
                        event_id=event,
                        endpoint_id=endpoint,
                        status="dead_lettered",
                        generation=1,
                        attempt_count=0,
                    )
                )
        operator_id, password = create_operator(sync_engine, tenant, username)
        async with engine.connect() as connection:
            stored = await connection.scalar(
                select(Operator.password_hash).where(Operator.id == operator_id)
            )
            assert stored is not None and password not in stored
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client:
            assert (
                await client.post(
                    "/api/v1/session/login", json={"username": username, "password": "wrong"}
                )
            ).status_code == 401
            login = await client.post(
                "/api/v1/session/login", json={"username": username, "password": password}
            )
            assert login.status_code == 200
            assert login.json()["organization_id"] == str(tenant)
            assert password not in login.text and manage_key not in login.text
            cookies = login.headers.get_list("set-cookie")
            assert any(
                session_cookie_name() in item
                and "httponly" in item.lower()
                and "secure" in item.lower()
                and "samesite=strict" in item.lower()
                for item in cookies
            )
            first_token = client.cookies.get(session_cookie_name())
            csrf = client.cookies.get(CSRF_COOKIE)
            assert first_token and csrf
            first_csrf = csrf
            current = await client.get("/api/v1/session")
            assert current.status_code == 200 and current.headers["cache-control"] == "no-store"
            own_event = await client.get(f"/api/v1/management/events/{event_id}")
            assert own_event.status_code == 200
            assert (await client.get(f"/api/v1/management/events/{other_event}")).status_code == 404
            assert (
                await client.get(
                    f"/api/v1/management/events/{event_id}",
                    headers={"Authorization": "Bearer invalid"},
                )
            ).status_code == 401
            replay_path = f"/api/v1/management/deliveries/{delivery_id}/replay"
            assert (await client.post(replay_path)).status_code == 403
            assert (
                await client.post(replay_path, headers={"X-CSRF-Token": "wrong"})
            ).status_code == 403
            assert (
                await client.post(
                    f"/api/v1/management/deliveries/{other_delivery}/replay",
                    headers={"X-CSRF-Token": csrf},
                )
            ).status_code == 404
            replay = await client.post(replay_path, headers={"X-CSRF-Token": csrf})
            assert replay.status_code == 200 and replay.json()["generation"] == 2
            async with engine.connect() as connection:
                actor = (
                    await connection.execute(
                        select(ReplayAudit.actor_key_id, ReplayAudit.actor_operator_id).where(
                            ReplayAudit.delivery_id == delivery_id
                        )
                    )
                ).one()
                assert actor.actor_key_id is None and actor.actor_operator_id == operator_id
                audit = await connection.scalar(
                    select(ManagementAudit.actor_operator_id).where(
                        ManagementAudit.organization_id == tenant,
                        ManagementAudit.action == "delivery_replayed",
                    )
                )
                assert audit == operator_id
            second_login = await client.post(
                "/api/v1/session/login", json={"username": username, "password": password}
            )
            assert second_login.status_code == 200
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(
                        select(OperatorSession.id).where(
                            OperatorSession.token_hash == token_hash(first_token)
                        )
                    )
                ) is None
            csrf = client.cookies.get(CSRF_COOKIE)
            assert csrf
            assert (
                await client.post("/api/v1/session/logout", headers={"X-CSRF-Token": first_csrf})
            ).status_code == 403
            assert (await client.post("/api/v1/session/logout")).status_code == 403
            assert (
                await client.post("/api/v1/session/logout", headers={"X-CSRF-Token": csrf})
            ).status_code == 204
            assert (await client.get("/api/v1/session")).status_code == 401
            third_login = await client.post(
                "/api/v1/session/login", json={"username": username, "password": password}
            )
            assert third_login.status_code == 200
            new_password = change_operator(sync_engine, username)
            assert new_password is not None and new_password != password
            assert (await client.get("/api/v1/session")).status_code == 401
            fourth_login = await client.post(
                "/api/v1/session/login", json={"username": username, "password": new_password}
            )
            assert fourth_login.status_code == 200
            async with engine.begin() as connection:
                await connection.execute(
                    update(OperatorSession)
                    .where(OperatorSession.operator_id == operator_id)
                    .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            assert (await client.get("/api/v1/session")).status_code == 401
            change_operator(sync_engine, username, disable=True)
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(
                        select(Operator.disabled_at).where(Operator.id == operator_id)
                    )
                ) is not None
    finally:
        await redis.delete(f"eventflow:login:{token_hash(username)}")
        await clean_organizations(engine, [tenant, other_tenant])
        await redis.aclose()
        await engine.dispose()
        sync_engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_login_is_shared_rate_limited_and_fails_closed_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    redis = Redis.from_url(os.environ["EVENTFLOW_REDIS_URL"])
    app.state.engine, app.state.redis = engine, redis
    username = "absent-" + uuid.uuid4().hex[:12]
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client:
            for _ in range(5):
                denied = await client.post(
                    "/api/v1/session/login", json={"username": username, "password": "wrong"}
                )
                assert denied.status_code == 401 and denied.json()["code"] == "invalid_credentials"
            limited = await client.post(
                "/api/v1/session/login", json={"username": username, "password": "wrong"}
            )
            assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1

            async def unavailable(*args: object) -> None:
                raise RedisError("unavailable")

            monkeypatch.setattr("eventflow.operator_session.admit_login", unavailable)
            failed = await client.post(
                "/api/v1/session/login",
                json={"username": "another-" + uuid.uuid4().hex[:8], "password": "wrong"},
            )
            assert failed.status_code == 503 and failed.json()["code"] == "login_limit_unavailable"
    finally:
        await redis.delete(f"eventflow:login:{token_hash(username)}")
        await redis.aclose()
        await engine.dispose()
