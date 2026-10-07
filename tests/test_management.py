import asyncio
import base64
import os
import secrets
import uuid

import httpx
import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.app import app
from eventflow.bootstrap import create_organization
from eventflow.config import get_settings
from eventflow.ingest import hash_api_key
from eventflow.models import (
    ApiKey,
    Delivery,
    Endpoint,
    EndpointSecretVersion,
    Event,
    Organization,
    ReplayAudit,
)
from eventflow.secrets import decrypt_secret
from eventflow.webhook import UnsafeDestination, validated_destination
from tests.support import clean_organizations


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_management_keys_endpoints_rotation_and_tenant_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    app.state.engine = engine
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    manage_a, manage_b, publish_a = [secrets.token_urlsafe(32) for _ in range(3)]
    monkeypatch.setattr(
        "eventflow.management.validated_destination", lambda url: (url, "example.com")
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Organization),
                [{"id": tenant_a, "name": "manage-a"}, {"id": tenant_b, "name": "manage-b"}],
            )
            await connection.execute(
                insert(ApiKey),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": tenant,
                        "key_prefix": key[:12],
                        "key_hash": hash_api_key(key),
                        "scope": scope,
                    }
                    for tenant, key, scope in (
                        (tenant_a, manage_a, "manage"),
                        (tenant_b, manage_b, "manage"),
                        (tenant_a, publish_a, "publish"),
                    )
                ],
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            auth_a = {"Authorization": f"Bearer {manage_a}"}
            auth_b = {"Authorization": f"Bearer {manage_b}"}
            auth_publish = {"Authorization": f"Bearer {publish_a}"}
            denied = await client.post(
                "/api/v1/management/api-keys", headers=auth_publish, json={"scope": "publish"}
            )
            assert denied.status_code == 401
            issued = await client.post(
                "/api/v1/management/api-keys", headers=auth_a, json={"scope": "publish"}
            )
            assert issued.status_code == 201
            issued_id = uuid.UUID(issued.json()["id"])
            issued_key = issued.json()["key"]
            listing = await client.get("/api/v1/management/api-keys", headers=auth_a)
            assert listing.status_code == 200
            assert issued_key not in listing.text and "key_hash" not in listing.text
            assert any(row["id"] == str(issued_id) for row in listing.json())
            monkeypatch.setattr("eventflow.management.MAX_KEYS", 3)
            competing = await asyncio.gather(
                *(
                    client.post(
                        "/api/v1/management/api-keys",
                        headers=auth_a,
                        json={"scope": "publish"},
                    )
                    for _ in range(2)
                )
            )
            assert sorted(item.status_code for item in competing) == [201, 409]

            created = await client.post(
                "/api/v1/management/endpoints",
                headers=auth_a,
                json={"url": "https://example.com/hook"},
            )
            assert created.status_code == 201
            endpoint_id = uuid.UUID(created.json()["id"])
            secret1 = base64.urlsafe_b64decode(created.json()["signing_secret"])
            assert len(secret1) == 32 and created.json()["key_id"] == 1
            monkeypatch.setattr("eventflow.management.MAX_ENDPOINTS", 1)
            assert (
                await client.post(
                    "/api/v1/management/endpoints",
                    headers=auth_a,
                    json={"url": "https://example.com/another"},
                )
            ).status_code == 409
            assert (
                "signing_secret"
                not in (await client.get("/api/v1/management/endpoints", headers=auth_a)).text
            )
            cross_tenant = await client.patch(
                f"/api/v1/management/endpoints/{endpoint_id}",
                headers=auth_b,
                json={"active": False},
            )
            assert cross_tenant.status_code == 404
            subscribed = await client.post(
                f"/api/v1/management/endpoints/{endpoint_id}/subscriptions",
                headers=auth_a,
                json={"event_type": "order.created"},
            )
            assert subscribed.status_code == 201
            monkeypatch.setattr("eventflow.management.MAX_SUBSCRIPTIONS", 1)
            assert (
                await client.post(
                    f"/api/v1/management/endpoints/{endpoint_id}/subscriptions",
                    headers=auth_a,
                    json={"event_type": "order.updated"},
                )
            ).status_code == 409
            assert (
                len((await client.get("/api/v1/management/subscriptions", headers=auth_a)).json())
                == 1
            )
            prepared = await client.post(
                f"/api/v1/management/endpoints/{endpoint_id}/secrets", headers=auth_a
            )
            assert prepared.status_code == 201 and prepared.json()["key_id"] == 2
            secret2 = base64.urlsafe_b64decode(prepared.json()["signing_secret"])
            assert secret2 != secret1
            activated = await client.post(
                f"/api/v1/management/endpoints/{endpoint_id}/secrets/2/activate",
                headers=auth_a,
                json={"immediate": False},
            )
            assert activated.status_code == 200
            event_id, delivery_id = uuid.uuid4(), uuid.uuid4()
            async with engine.begin() as connection:
                await connection.execute(
                    insert(Event).values(
                        id=event_id,
                        organization_id=tenant_a,
                        event_type="order.created",
                        payload={},
                        terminal_at=await connection.scalar(select(func.clock_timestamp())),
                    )
                )
                await connection.execute(
                    insert(Delivery).values(
                        id=delivery_id,
                        organization_id=tenant_a,
                        event_id=event_id,
                        endpoint_id=endpoint_id,
                        status="dead_lettered",
                        generation=1,
                        attempt_count=0,
                    )
                )
            assert (
                await client.post(
                    f"/api/v1/management/deliveries/{delivery_id}/replay", headers=auth_publish
                )
            ).status_code == 401
            assert (
                await client.post(
                    f"/api/v1/management/deliveries/{delivery_id}/replay", headers=auth_b
                )
            ).status_code == 404
            replayed = await client.post(
                f"/api/v1/management/deliveries/{delivery_id}/replay", headers=auth_a
            )
            assert replayed.status_code == 200 and replayed.json()["generation"] == 2
            revoked = await client.delete(
                f"/api/v1/management/api-keys/{issued_id}", headers=auth_a
            )
            assert revoked.status_code == 204
            assert (
                await client.get(
                    "/api/v1/management/api-keys",
                    headers={"Authorization": f"Bearer {issued_key}"},
                )
            ).status_code == 401
        async with engine.connect() as connection:
            endpoint = (
                await connection.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
            ).scalar_one()
            assert endpoint.signing_secret_version == 2
            assert (
                decrypt_secret(
                    endpoint.signing_secret_key_id,
                    endpoint.signing_secret_ciphertext,
                    tenant_a,
                    endpoint_id,
                    2,
                )
                == secret2
            )
            versions = (
                (
                    await connection.execute(
                        select(EndpointSecretVersion)
                        .where(EndpointSecretVersion.endpoint_id == endpoint_id)
                        .order_by(EndpointSecretVersion.version)
                    )
                )
                .scalars()
                .all()
            )
            assert [item.status for item in versions] == ["retiring", "active"]
            assert versions[0].expires_at is not None
            assert (
                decrypt_secret(
                    versions[0].encryption_key_id,
                    versions[0].ciphertext,
                    tenant_a,
                    endpoint_id,
                    1,
                )
                == secret1
            )
            assert (
                await connection.scalar(
                    select(ReplayAudit.generation).where(ReplayAudit.delivery_id == delivery_id)
                )
                == 2
            )
    finally:
        await clean_organizations(engine, [tenant_a, tenant_b])
        await engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_operator_bootstrap_stores_only_management_key_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVENTFLOW_DATABASE_URL", os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    get_settings.cache_clear()
    organization_id, raw_key = create_organization("bootstrap-test")
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    select(ApiKey).where(ApiKey.organization_id == organization_id)
                )
            ).scalar_one()
            assert row.scope == "manage" and row.key_hash == hash_api_key(raw_key)
            assert raw_key != row.key_hash
    finally:
        await clean_organizations(engine, [organization_id])
        await engine.dispose()
        get_settings.cache_clear()


def test_endpoint_url_policy_rejects_internal_destination() -> None:
    with pytest.raises(UnsafeDestination):
        validated_destination("http://127.0.0.1/hook")
