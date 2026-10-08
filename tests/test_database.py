import os
import uuid

import pytest
from sqlalchemy import insert, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.models import Endpoint, Organization, Subscription
from tests.support import sealed_secret


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_initial_migration_on_postgresql() -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            assert {
                "organizations",
                "api_keys",
                "endpoints",
                "subscriptions",
                "events",
                "deliveries",
                "delivery_attempts",
                "outbox_messages",
                "replay_audits",
                "endpoint_secret_versions",
                "management_audits",
                "operators",
                "operator_sessions",
            } <= set(tables)
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            assert result.scalar_one() == "0008_operator_sessions"
    finally:
        await engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_subscription_cannot_reference_another_tenant_endpoint() -> None:
    engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    tenant_a, tenant_b, endpoint_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    insert(Organization),
                    [{"id": tenant_a, "name": "A"}, {"id": tenant_b, "name": "B"}],
                )
                await connection.execute(
                    insert(Endpoint).values(
                        id=endpoint_id,
                        organization_id=tenant_a,
                        url="https://example.com/hook",
                        **sealed_secret(b"fixture-only", tenant_a, endpoint_id),
                        active=True,
                    )
                )
                await connection.execute(
                    insert(Subscription).values(
                        id=uuid.uuid4(),
                        organization_id=tenant_b,
                        endpoint_id=endpoint_id,
                        event_type="order.created",
                    )
                )
    finally:
        await engine.dispose()
