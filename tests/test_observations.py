import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.app import app
from eventflow.ingest import hash_api_key
from eventflow.models import ApiKey, Delivery, DeliveryAttempt, Endpoint, Event, Organization
from tests.support import clean_organizations, sealed_secret


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_observation_pages_are_stable_tenant_scoped_and_sanitized() -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    app.state.engine = engine
    tenant, other_tenant = uuid.uuid4(), uuid.uuid4()
    endpoint_id, other_endpoint_id = uuid.uuid4(), uuid.uuid4()
    event_ids = [uuid.uuid4() for _ in range(4)]
    other_event = uuid.uuid4()
    delivery_ids = [uuid.uuid4() for _ in range(3)]
    other_delivery = uuid.uuid4()
    manage_key, publish_key, other_manage_key = [secrets.token_urlsafe(32) for _ in range(3)]
    shared_time = datetime(2026, 10, 8, 8, 0, tzinfo=UTC)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Organization),
                [{"id": tenant, "name": "observations"}, {"id": other_tenant, "name": "other"}],
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
            for org, endpoint in ((tenant, endpoint_id), (other_tenant, other_endpoint_id)):
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
                insert(Event),
                [
                    {
                        "id": event_id,
                        "organization_id": tenant,
                        "event_type": "order.created" if index < 3 else "order.updated",
                        "payload": {"private": "payload-marker"},
                        "created_at": shared_time,
                    }
                    for index, event_id in enumerate(event_ids)
                ]
                + [
                    {
                        "id": other_event,
                        "organization_id": other_tenant,
                        "event_type": "order.created",
                        "payload": {"private": "other-tenant"},
                        "created_at": shared_time,
                    }
                ],
            )
            await connection.execute(
                insert(Delivery),
                [
                    {
                        "id": delivery_id,
                        "organization_id": tenant,
                        "event_id": event_id,
                        "endpoint_id": endpoint_id,
                        "status": "retry_scheduled" if index == 0 else "pending",
                        "generation": 1,
                        "attempt_count": 2 if index == 0 else 0,
                        "created_at": shared_time,
                    }
                    for index, (delivery_id, event_id) in enumerate(
                        zip(delivery_ids, event_ids[:3], strict=True)
                    )
                ]
                + [
                    {
                        "id": other_delivery,
                        "organization_id": other_tenant,
                        "event_id": other_event,
                        "endpoint_id": other_endpoint_id,
                        "status": "pending",
                        "generation": 1,
                        "attempt_count": 0,
                        "created_at": shared_time,
                    }
                ],
            )
            await connection.execute(
                insert(DeliveryAttempt),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": tenant,
                        "delivery_id": delivery_ids[0],
                        "number": number,
                        "generation": 1,
                        "status": "failed",
                        "response_status": 503,
                        "started_at": shared_time + timedelta(seconds=number),
                    }
                    for number in (1, 2)
                ],
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            auth = {"Authorization": f"Bearer {manage_key}"}
            publish = {"Authorization": f"Bearer {publish_key}"}
            first = await client.get("/api/v1/management/events?limit=2", headers=auth)
            assert first.status_code == 200
            first_ids = [item["id"] for item in first.json()["items"]]
            assert first_ids == [str(item) for item in sorted(event_ids, reverse=True)[:2]]
            assert "payload-marker" not in first.text
            cursor = first.json()["next_cursor"]
            assert isinstance(cursor, str)
            newest = uuid.uuid4()
            async with engine.begin() as connection:
                await connection.execute(
                    insert(Event).values(
                        id=newest,
                        organization_id=tenant,
                        event_type="order.created",
                        payload={},
                        created_at=shared_time + timedelta(seconds=1),
                    )
                )
            second = await client.get(
                "/api/v1/management/events", headers=auth, params={"limit": 2, "cursor": cursor}
            )
            second_ids = [item["id"] for item in second.json()["items"]]
            assert second.status_code == 200
            assert set(first_ids).isdisjoint(second_ids)
            assert str(newest) not in second.text and str(other_event) not in second.text
            assert set(first_ids + second_ids) == {str(item) for item in event_ids}
            assert second.json()["next_cursor"] is None
            filtered = await client.get(
                "/api/v1/management/events", headers=auth, params={"event_type": "order.updated"}
            )
            assert [item["id"] for item in filtered.json()["items"]] == [str(event_ids[3])]
            for params in (
                {"cursor": cursor, "event_type": "order.created"},
                {"cursor": "invalid"},
                {"limit": 101},
            ):
                assert (
                    await client.get("/api/v1/management/events", headers=auth, params=params)
                ).status_code == 422
            assert (
                await client.get(
                    "/api/v1/management/events",
                    headers={"Authorization": f"Bearer {other_manage_key}"},
                    params={"cursor": cursor},
                )
            ).status_code == 422
            assert (
                await client.get("/api/v1/management/events", headers=publish)
            ).status_code == 401
            assert (
                await client.get(f"/api/v1/management/events/{other_event}", headers=auth)
            ).status_code == 404
            detail = await client.get(f"/api/v1/management/events/{event_ids[0]}", headers=auth)
            assert detail.json()["payload"] == {"private": "payload-marker"}

            deliveries = await client.get(
                "/api/v1/management/deliveries", headers=auth, params={"limit": 2}
            )
            assert deliveries.status_code == 200
            assert len(deliveries.json()["items"]) == 2
            next_page = await client.get(
                "/api/v1/management/deliveries",
                headers=auth,
                params={"limit": 2, "cursor": deliveries.json()["next_cursor"]},
            )
            assert len(next_page.json()["items"]) == 1
            assert str(other_delivery) not in deliveries.text + next_page.text
            retrying = await client.get(
                "/api/v1/management/deliveries",
                headers=auth,
                params={"status": "retry_scheduled"},
            )
            assert [item["id"] for item in retrying.json()["items"]] == [str(delivery_ids[0])]
            assert (
                await client.get(
                    "/api/v1/management/deliveries", headers=auth, params={"status": "unknown"}
                )
            ).status_code == 422
            assert (
                await client.get(f"/api/v1/management/deliveries/{other_delivery}", headers=auth)
            ).status_code == 404
            attempts = await client.get(
                f"/api/v1/management/deliveries/{delivery_ids[0]}/attempts",
                headers=auth,
                params={"limit": 1},
            )
            assert attempts.status_code == 200
            assert attempts.json()["items"][0]["number"] == 2
            attempts_next = await client.get(
                f"/api/v1/management/deliveries/{delivery_ids[0]}/attempts",
                headers=auth,
                params={"cursor": attempts.json()["next_cursor"]},
            )
            assert attempts_next.json()["items"][0]["number"] == 1
            assert attempts_next.json()["next_cursor"] is None
            assert (
                await client.get(
                    f"/api/v1/management/deliveries/{other_delivery}/attempts", headers=auth
                )
            ).status_code == 404
    finally:
        await clean_organizations(engine, [tenant, other_tenant])
        await engine.dispose()
