import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine

from eventflow.config import get_settings
from eventflow.delivery import (
    claim_delivery,
    finish_delivery,
    make_sync_engine,
    reconcile_deliveries,
)
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
from eventflow.webhook import send_webhook
from eventflow.worker import deliver
from tests.support import sealed_secret


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
                    **sealed_secret(b"fixture", tenant, endpoint_id),
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
def test_global_start_rate_is_shared_after_slots_are_freed() -> None:
    engine = make_sync_engine()
    tenant, _endpoints, deliveries = seed_deliveries(engine, [1, 1, 1, 1, 1])
    try:
        for delivery_ids in deliveries[:4]:
            claim = claim_delivery(engine, delivery_ids[0])
            assert claim is not None
            finish_delivery(engine, claim, 200, None)
        assert claim_delivery(engine, deliveries[4][0]) is None
        with engine.begin() as connection:
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.organization_id == tenant)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        final_claim = claim_delivery(engine, deliveries[4][0])
        assert final_claim is not None
        finish_delivery(engine, final_claim, 200, None)
    finally:
        clean_tenant(engine, tenant)
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_reconciler_reaches_healthy_delivery_after_many_paused_rows() -> None:
    engine = make_sync_engine()
    tenant, endpoints, deliveries = seed_deliveries(engine, [101, 1])
    try:
        with engine.begin() as connection:
            connection.execute(
                update(Endpoint)
                .where(Endpoint.id == endpoints[0])
                .values(pause_until=func.clock_timestamp() + timedelta(seconds=60))
            )
        notices: list[uuid.UUID] = []
        assert reconcile_deliveries(engine, notices.append, limit=25) == 102
        assert len(notices) == len(set(notices)) == 102
        assert deliveries[1][0] in notices
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
                select(ReplayAudit.actor_key_id, ReplayAudit.generation).where(
                    ReplayAudit.delivery_id == delivery_id
                )
            ).one()
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
    received: list[tuple[uuid.UUID, int]] = []
    effects: set[tuple[uuid.UUID, int]] = set()

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            delivery_id = uuid.UUID(self.headers["X-EventFlow-Delivery-Id"])
            generation = int(self.headers["X-EventFlow-Generation"])
            expected = hmac.new(
                b"fixture",
                self.headers["X-EventFlow-Timestamp"].encode() + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            valid = hmac.compare_digest(
                self.headers["X-EventFlow-Signature"], f"v1={expected}"
            ) and json.loads(body)["delivery_id"] == str(delivery_id)
            if valid:
                received.append((delivery_id, generation))
                effects.add((delivery_id, generation))
            self.send_response(401 if not valid else 503 if generation == 1 else 200)
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/hook"
    monkeypatch.setenv("EVENTFLOW_ENVIRONMENT", "test")
    monkeypatch.setenv("EVENTFLOW_LOCAL_TEST_RECEIVER_URL", url)
    get_settings.cache_clear()
    engine = make_sync_engine()
    tenant, endpoints, deliveries = seed_deliveries(engine, [1])
    delivery_id = deliveries[0][0]
    management_key = secrets.token_urlsafe(32)
    try:
        with engine.begin() as connection:
            connection.execute(update(Endpoint).where(Endpoint.id == endpoints[0]).values(url=url))
            connection.execute(
                insert(ApiKey).values(
                    id=uuid.uuid4(),
                    organization_id=tenant,
                    key_prefix=management_key[:12],
                    key_hash=hash_api_key(management_key),
                    scope="manage",
                )
            )
        for number in range(1, 8):
            claim = claim_delivery(engine, delivery_id)
            assert claim is not None
            result = send_webhook(claim)
            assert result.status_code == 503
            finish_delivery(engine, claim, result.status_code, None)
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
        assert received == [(delivery_id, 1)] * 7
        assert effects == {(delivery_id, 1)}
        assert replay_delivery(engine, delivery_id, management_key) == 2
        with engine.begin() as connection:
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.delivery_id == delivery_id)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        replay_claim = claim_delivery(engine, delivery_id)
        assert replay_claim is not None and replay_claim.generation == 2
        assert send_webhook(replay_claim).status_code == 200
        assert send_webhook(replay_claim).status_code == 200  # duplicate physical request
        finish_delivery(engine, replay_claim, 200, None)
        assert effects == {(delivery_id, 1), (delivery_id, 2)}
        with engine.connect() as connection:
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                == "succeeded"
            )
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(DeliveryAttempt)
                    .where(
                        DeliveryAttempt.delivery_id == delivery_id,
                        DeliveryAttempt.generation == 2,
                    )
                )
                == 1
            )
    finally:
        clean_tenant(engine, tenant)
        engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        get_settings.cache_clear()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_two_celery_workers_keep_429_pause_local_to_one_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[uuid.UUID] = []
    limited_id = uuid.uuid4()

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            delivery_id = uuid.UUID(self.headers["X-EventFlow-Delivery-Id"])
            received.append(delivery_id)
            self.send_response(429 if delivery_id == limited_id else 200)
            if delivery_id == limited_id:
                self.send_header("Retry-After", "60")
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/hook"
    monkeypatch.setenv("EVENTFLOW_ENVIRONMENT", "test")
    monkeypatch.setenv("EVENTFLOW_LOCAL_TEST_RECEIVER_URL", url)
    get_settings.cache_clear()
    engine = make_sync_engine()
    tenant, endpoints, deliveries = seed_deliveries(engine, [2, 1])
    limited_id = deliveries[0][0]
    healthy_id = deliveries[1][0]
    queue = f"test-{uuid.uuid4()}"
    processes: list[subprocess.Popen[bytes]] = []
    try:
        with engine.begin() as connection:
            connection.execute(update(Endpoint).where(Endpoint.id.in_(endpoints)).values(url=url))
        for index in range(2):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "celery",
                        "-A",
                        "eventflow.worker:celery_app",
                        "worker",
                        "--pool=solo",
                        "--concurrency=1",
                        "--loglevel=WARNING",
                        "-Q",
                        queue,
                        "-n",
                        f"limits-{index}@%h",
                    ],
                    env=os.environ.copy(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        deliver.apply_async(args=[str(limited_id)], queue=queue)
        deliver.apply_async(args=[str(healthy_id)], queue=queue)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                limited_status = connection.scalar(
                    select(Delivery.status).where(Delivery.id == limited_id)
                )
                healthy_status = connection.scalar(
                    select(Delivery.status).where(Delivery.id == healthy_id)
                )
            if limited_status == "retry_scheduled" and healthy_status == "succeeded":
                break
            time.sleep(0.2)
        assert limited_status == "retry_scheduled" and healthy_status == "succeeded"
        deliver.apply_async(args=[str(deliveries[0][1])], queue=queue)
        time.sleep(2)
        with engine.connect() as connection:
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == deliveries[0][1]))
                == "pending"
            )
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(DeliveryAttempt)
                    .where(DeliveryAttempt.delivery_id == deliveries[0][1])
                )
                == 0
            )
            pause = connection.scalar(
                select(Endpoint.pause_until).where(Endpoint.id == endpoints[0])
            )
            assert pause is not None
        assert limited_id in received and healthy_id in received
        assert deliveries[0][1] not in received
    finally:
        for process in processes:
            process.terminate()
            process.wait(timeout=5)
        clean_tenant(engine, tenant)
        engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        get_settings.cache_clear()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_real_receiver_503_twice_then_200_preserves_attempt_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[uuid.UUID] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            received.append(uuid.UUID(self.headers["X-EventFlow-Delivery-Id"]))
            self.send_response(503 if len(received) < 3 else 200)
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/hook"
    monkeypatch.setenv("EVENTFLOW_ENVIRONMENT", "test")
    monkeypatch.setenv("EVENTFLOW_LOCAL_TEST_RECEIVER_URL", url)
    get_settings.cache_clear()
    engine = make_sync_engine()
    tenant, endpoints, deliveries = seed_deliveries(engine, [1])
    delivery_id = deliveries[0][0]
    try:
        with engine.begin() as connection:
            connection.execute(update(Endpoint).where(Endpoint.id == endpoints[0]).values(url=url))
        for number in range(1, 4):
            claim = claim_delivery(engine, delivery_id)
            assert claim is not None
            response = send_webhook(claim)
            finish_delivery(engine, claim, response.status_code, None, response.retry_after)
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
        assert received == [delivery_id] * 3
    finally:
        clean_tenant(engine, tenant)
        engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        get_settings.cache_clear()
