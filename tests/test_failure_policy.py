import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine

from eventflow.delivery import claim_delivery, finish_delivery, make_sync_engine
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
from eventflow.replay import ReplayDenied, ReplayUnavailable, replay_delivery


def seed_deliveries(
    engine: Engine, counts: list[int]
) -> tuple[uuid.UUID, list[uuid.UUID], list[list[uuid.UUID]]]:
    tenant = uuid.uuid4()
    endpoints = [uuid.uuid4() for _ in counts]
    deliveries = [[uuid.uuid4() for _ in range(count)] for count in counts]
    with engine.begin() as connection:
        connection.execute(insert(Organization).values(id=tenant, name="policy-test"))
        for endpoint_id, delivery_ids in zip(endpoints, deliveries, strict=True):
            connection.execute(
                insert(Endpoint).values(
                    id=endpoint_id,
                    organization_id=tenant,
                    url="https://example.com/hook",
                    signing_secret_ciphertext=b"fixture",
                    active=True,
                )
            )
            for delivery_id in delivery_ids:
                event_id = uuid.uuid4()
                connection.execute(
                    insert(Event).values(
                        id=event_id,
                        organization_id=tenant,
                        event_type="order.created",
                        payload={"id": str(event_id)},
                    )
                )
                connection.execute(
                    insert(Delivery).values(
                        id=delivery_id,
                        organization_id=tenant,
                        event_id=event_id,
                        endpoint_id=endpoint_id,
                        status="pending",
                        generation=1,
                        attempt_count=0,
                    )
                )
    return tenant, endpoints, deliveries


def clean_tenant(engine: Engine, tenant: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(delete(ReplayAudit).where(ReplayAudit.organization_id == tenant))
        connection.execute(delete(OutboxMessage).where(OutboxMessage.organization_id == tenant))
        connection.execute(delete(DeliveryAttempt).where(DeliveryAttempt.organization_id == tenant))
        connection.execute(delete(Delivery).where(Delivery.organization_id == tenant))
        connection.execute(delete(Event).where(Event.organization_id == tenant))
        connection.execute(delete(Endpoint).where(Endpoint.organization_id == tenant))
        connection.execute(delete(ApiKey).where(ApiKey.organization_id == tenant))
        connection.execute(delete(Organization).where(Organization.id == tenant))


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_429_pauses_only_its_endpoint_and_endpoint_capacity() -> None:
    engine = make_sync_engine()
    tenant, endpoints, deliveries = seed_deliveries(engine, [2, 4])
    try:
        limited = claim_delivery(engine, deliveries[0][0])
        assert limited is not None
        finish_delivery(engine, limited, 429, None, "60")
        assert claim_delivery(engine, deliveries[0][1]) is None
        healthy = claim_delivery(engine, deliveries[1][0])
        assert healthy is not None
        assert claim_delivery(engine, deliveries[1][1]) is None  # one start per second
        with engine.begin() as connection:
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.id == healthy.attempt_id)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        second_healthy = claim_delivery(engine, deliveries[1][1])
        assert second_healthy is not None
        with engine.begin() as connection:
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.id == second_healthy.attempt_id)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        assert claim_delivery(engine, deliveries[1][2]) is None  # two active per endpoint
        finish_delivery(engine, healthy, 200, None)
        finish_delivery(engine, second_healthy, 200, None)
        with engine.connect() as connection:
            pause = connection.scalar(
                select(Endpoint.pause_until).where(Endpoint.id == endpoints[0])
            )
            due = connection.scalar(
                select(Delivery.next_attempt_at).where(Delivery.id == deliveries[0][0])
            )
            assert pause is not None and due is not None and due >= pause
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == deliveries[1][0]))
                == "succeeded"
            )
    finally:
        clean_tenant(engine, tenant)
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_global_concurrency_is_shared_between_endpoints() -> None:
    engine = make_sync_engine()
    tenant, _endpoints, deliveries = seed_deliveries(engine, [1, 1, 1, 1, 1])
    try:
        claims = []
        for delivery_ids in deliveries[:4]:
            claim = claim_delivery(engine, delivery_ids[0])
            assert claim is not None
            claims.append(claim)
        with engine.begin() as connection:
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.organization_id == tenant)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        assert claim_delivery(engine, deliveries[4][0]) is None
        for claim in claims:
            finish_delivery(engine, claim, 200, None)
    finally:
        clean_tenant(engine, tenant)
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_two_concurrent_claims_create_one_attempt() -> None:
    engine = make_sync_engine()
    tenant, _endpoints, deliveries = seed_deliveries(engine, [1])
    delivery_id = deliveries[0][0]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _index: claim_delivery(engine, delivery_id), range(2)))
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(DeliveryAttempt)
                    .where(DeliveryAttempt.delivery_id == delivery_id)
                )
                == 1
            )
        finish_delivery(engine, winners[0], 200, None)
    finally:
        clean_tenant(engine, tenant)
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_three_attempts_then_success_and_tenant_authorized_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("eventflow.retry.random.random", lambda: 0.5)
    engine = make_sync_engine()
    tenant, _endpoints, deliveries = seed_deliveries(engine, [1])
    other_tenant = uuid.uuid4()
    delivery_id = deliveries[0][0]
    manage_key, publish_key, other_key = [secrets.token_urlsafe(32) for _ in range(3)]
    actor_id = uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(insert(Organization).values(id=other_tenant, name="other"))
            connection.execute(
                insert(ApiKey),
                [
                    {
                        "id": actor_id,
                        "organization_id": tenant,
                        "key_prefix": manage_key[:12],
                        "key_hash": hash_api_key(manage_key),
                        "scope": "manage",
                    },
                    {
                        "id": uuid.uuid4(),
                        "organization_id": tenant,
                        "key_prefix": publish_key[:12],
                        "key_hash": hash_api_key(publish_key),
                        "scope": "publish",
                    },
                    {
                        "id": uuid.uuid4(),
                        "organization_id": other_tenant,
                        "key_prefix": other_key[:12],
                        "key_hash": hash_api_key(other_key),
                        "scope": "manage",
                    },
                ],
            )
        for number, status in enumerate((503, 503, 200), start=1):
            claim = claim_delivery(engine, delivery_id)
            assert claim is not None
            finish_delivery(engine, claim, status, None)
            if number < 3:
                with engine.begin() as connection:
                    connection.execute(
                        update(Delivery)
                        .where(Delivery.id == delivery_id)
                        .values(next_attempt_at=func.clock_timestamp() - timedelta(seconds=1))
                    )
                    connection.execute(
                        update(DeliveryAttempt)
                        .where(DeliveryAttempt.id == claim.attempt_id)
                        .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
                    )
        with engine.connect() as connection:
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                == "succeeded"
            )
            assert connection.execute(
                select(DeliveryAttempt.response_status)
                .where(DeliveryAttempt.delivery_id == delivery_id)
                .order_by(DeliveryAttempt.number)
            ).scalars().all() == [503, 503, 200]
        with pytest.raises(ReplayUnavailable):
            replay_delivery(engine, delivery_id, manage_key)
        with engine.begin() as connection:
            connection.execute(
                update(Delivery)
                .where(Delivery.id == delivery_id)
                .values(status="dead_lettered", attempt_count=7)
            )
        with pytest.raises(ReplayDenied):
            replay_delivery(engine, delivery_id, publish_key)
        with pytest.raises(ReplayDenied):
            replay_delivery(engine, delivery_id, other_key)
        assert replay_delivery(engine, delivery_id, manage_key) == 2
        with pytest.raises(ReplayUnavailable):
            replay_delivery(engine, delivery_id, manage_key)
        with engine.begin() as connection:
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.delivery_id == delivery_id)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        replay_claim = claim_delivery(engine, delivery_id)
        assert replay_claim is not None and replay_claim.generation == 2
        assert replay_claim.attempt_id is not None
        finish_delivery(engine, replay_claim, 200, None)
        with engine.connect() as connection:
            audit = connection.execute(
                select(ReplayAudit).where(ReplayAudit.delivery_id == delivery_id)
            ).scalar_one()
            assert audit.actor_key_id == actor_id and audit.generation == 2
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(OutboxMessage)
                    .where(
                        OutboxMessage.delivery_id == delivery_id,
                        OutboxMessage.generation == 2,
                    )
                )
                == 1
            )
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                == "succeeded"
            )
    finally:
        clean_tenant(engine, tenant)
        clean_tenant(engine, other_tenant)
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_seven_retryable_failures_dead_letter_the_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("eventflow.retry.random.random", lambda: 0.5)
    engine = make_sync_engine()
    tenant, _endpoints, deliveries = seed_deliveries(engine, [1])
    delivery_id = deliveries[0][0]
    try:
        for number in range(1, 8):
            claim = claim_delivery(engine, delivery_id)
            assert claim is not None
            finish_delivery(engine, claim, 503, None)
            if number < 7:
                with engine.begin() as connection:
                    connection.execute(
                        update(Delivery)
                        .where(Delivery.id == delivery_id)
                        .values(next_attempt_at=func.clock_timestamp() - timedelta(seconds=1))
                    )
                    connection.execute(
                        update(DeliveryAttempt)
                        .where(DeliveryAttempt.id == claim.attempt_id)
                        .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
                    )
        with engine.connect() as connection:
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                == "dead_lettered"
            )
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(DeliveryAttempt)
                    .where(
                        DeliveryAttempt.delivery_id == delivery_id,
                        DeliveryAttempt.generation == 1,
                    )
                )
                == 7
            )
        assert claim_delivery(engine, delivery_id) is None
    finally:
        clean_tenant(engine, tenant)
        engine.dispose()
