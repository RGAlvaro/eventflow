import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.delivery import make_sync_engine
from eventflow.ingest import hash_api_key
from eventflow.models import (
    ApiKey,
    Delivery,
    DeliveryAttempt,
    Endpoint,
    Event,
    Organization,
    OutboxMessage,
    ReplayAudit,
)
from eventflow.replay import replay_delivery
from eventflow.retention import purge_terminal_events
from tests.support import clean_organizations, sealed_secret


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
async def test_purge_deletes_only_expired_terminal_aggregates_and_replay_reopens_clock() -> None:
    engine = make_sync_engine()
    async_engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    tenant, endpoint_id, actor_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    expired_event, pending_event, replay_event = [uuid.uuid4() for _ in range(3)]
    expired_delivery, pending_delivery, replay_delivery_id = [uuid.uuid4() for _ in range(3)]
    management_key = secrets.token_urlsafe(32)
    old = datetime.now(UTC) - timedelta(days=31)
    try:
        with engine.begin() as connection:
            connection.execute(insert(Organization).values(id=tenant, name="retention"))
            connection.execute(
                insert(ApiKey).values(
                    id=actor_id,
                    organization_id=tenant,
                    key_prefix=management_key[:12],
                    key_hash=hash_api_key(management_key),
                    scope="manage",
                )
            )
            connection.execute(
                insert(Endpoint).values(
                    id=endpoint_id,
                    organization_id=tenant,
                    url="https://example.com/hook",
                    active=True,
                    **sealed_secret(b"fixture", tenant, endpoint_id),
                )
            )
            connection.execute(
                insert(Event),
                [
                    {
                        "id": event_id,
                        "organization_id": tenant,
                        "event_type": "order.created",
                        "payload": {},
                        "terminal_at": old,
                    }
                    for event_id in (expired_event, pending_event, replay_event)
                ],
            )
            connection.execute(
                insert(Delivery),
                [
                    {
                        "id": delivery_id,
                        "organization_id": tenant,
                        "event_id": event_id,
                        "endpoint_id": endpoint_id,
                        "status": status,
                        "generation": 1,
                        "attempt_count": 1,
                    }
                    for event_id, delivery_id, status in (
                        (expired_event, expired_delivery, "succeeded"),
                        (pending_event, pending_delivery, "pending"),
                        (replay_event, replay_delivery_id, "dead_lettered"),
                    )
                ],
            )
            connection.execute(
                insert(OutboxMessage),
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": tenant,
                        "delivery_id": delivery_id,
                        "generation": 1,
                    }
                    for delivery_id in (expired_delivery, pending_delivery, replay_delivery_id)
                ],
            )
            connection.execute(
                insert(DeliveryAttempt).values(
                    id=uuid.uuid4(),
                    organization_id=tenant,
                    delivery_id=expired_delivery,
                    number=1,
                    generation=1,
                    status="succeeded",
                    started_at=old,
                    finished_at=old,
                )
            )
            connection.execute(
                insert(ReplayAudit).values(
                    id=uuid.uuid4(),
                    organization_id=tenant,
                    delivery_id=expired_delivery,
                    actor_key_id=actor_id,
                    generation=1,
                )
            )
        assert replay_delivery(engine, replay_delivery_id, management_key) == 2
        assert purge_terminal_events(engine) == 1
        async with async_engine.connect() as connection:
            assert (
                await connection.scalar(select(Event.id).where(Event.id == expired_event)) is None
            )
            assert (
                await connection.scalar(select(Delivery.id).where(Delivery.id == expired_delivery))
                is None
            )
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(OutboxMessage)
                    .where(OutboxMessage.delivery_id == expired_delivery)
                )
                == 0
            )
            assert (
                await connection.scalar(
                    select(func.count())
                    .select_from(ReplayAudit)
                    .where(ReplayAudit.delivery_id == expired_delivery)
                )
                == 0
            )
            assert (
                await connection.scalar(select(Event.id).where(Event.id == pending_event))
                is not None
            )
            reopened = (
                await connection.execute(select(Event).where(Event.id == replay_event))
            ).scalar_one()
            assert reopened.terminal_at is None
    finally:
        await clean_organizations(async_engine, [tenant])
        await async_engine.dispose()
        engine.dispose()
