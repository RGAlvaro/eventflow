import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import replace
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import create_async_engine

from eventflow.app import app
from eventflow.config import get_settings
from eventflow.delivery import (
    claim_delivery,
    dispatch_outbox,
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
    Subscription,
)
from eventflow.webhook import (
    Address,
    Resolver,
    UnsafeDestination,
    send_webhook,
    validated_destination,
)
from eventflow.worker import deliver


def test_ssrf_rejects_private_dns_and_unsafe_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    def fixed_resolver(address: Address) -> Resolver:
        def resolve(_host: str) -> list[Address]:
            return [address]

        return resolve

    public = ipaddress.ip_address("8.8.8.8")
    private = ipaddress.ip_address("127.0.0.1")
    for url in (
        "http://example.com/hook",
        "https://127.0.0.1/hook",
        "https://example.com:8443/hook",
        "https://user@example.com/hook",
        "https://example.com%2f.evil.test/hook",
        "https://example.com/hook#fragment",
    ):
        with pytest.raises(UnsafeDestination):
            validated_destination(url, lambda _host: [public])
    with pytest.raises(UnsafeDestination):
        validated_destination("https://example.com/hook", lambda _host: [public, private])
    for address in ("::1", "::ffff:127.0.0.1", "::ffff:8.8.8.8"):
        with pytest.raises(UnsafeDestination):
            validated_destination(
                "https://example.com/hook", fixed_resolver(ipaddress.ip_address(address))
            )
    pinned, host = validated_destination("https://example.com/hook?q=1", lambda _host: [public])
    assert host == "example.com"
    assert str(pinned) == "https://8.8.8.8/hook?q=1"
    monkeypatch.setenv("EVENTFLOW_ENVIRONMENT", "production")
    monkeypatch.setenv("EVENTFLOW_LOCAL_TEST_RECEIVER_URL", "http://127.0.0.1:1234/hook")
    get_settings.cache_clear()
    try:
        with pytest.raises(UnsafeDestination):
            validated_destination("http://127.0.0.1:1234/hook")
    finally:
        get_settings.cache_clear()


def test_https_request_uses_pinned_ip_sni_and_disables_proxy_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eventflow.delivery import ClaimedDelivery

    captured: dict[str, object] = {}

    class Client:
        def __init__(self, **options: object) -> None:
            captured.update(options)

        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def build_request(
            self, method: str, url: httpx.URL, *, headers: dict[str, str], content: bytes
        ) -> httpx.Request:
            return httpx.Request(method, url, headers=headers, content=content)

        def send(self, request: httpx.Request, stream: bool) -> httpx.Response:
            captured["request"] = request
            captured["stream"] = stream
            return httpx.Response(302, request=request, headers={"Location": "http://127.0.0.1/"})

    monkeypatch.setattr(httpx, "Client", Client)
    claim = ClaimedDelivery(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        1,
        "order.created",
        {},
        "https://hook.example.com/deliver",
        b"test-key",
    )
    status = send_webhook(claim, lambda _host: [ipaddress.ip_address("8.8.8.8")])
    assert status.status_code == 302
    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert str(request.url) == "https://8.8.8.8/deliver"
    assert request.headers["Host"] == "hook.example.com"
    assert request.extensions["sni_hostname"] == "hook.example.com"
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    assert captured["stream"] is True


def test_https_pinned_connection_checks_original_hostname(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from eventflow.delivery import ClaimedDelivery

    key_path, cert_path = tmp_path / "key.pem", tmp_path / "cert.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-subj",
            "/CN=hook.example.com",
            "-addext",
            "subjectAltName=DNS:hook.example.com",
            "-days",
            "1",
        ],
        check=True,
        capture_output=True,
    )
    received_hosts: list[str] = []

    class TLSReceiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            received_hosts.append(self.headers["Host"])
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), TLSReceiver)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    real_connect = socket.socket.connect
    connected_to: list[tuple[str, int]] = []

    def redirected_connect(sock: socket.socket, address: tuple[str, int]) -> None:
        connected_to.append(address)
        if address == ("8.8.8.8", 443):
            real_connect(sock, ("127.0.0.1", server.server_port))
        else:
            real_connect(sock, address)

    real_client = httpx.Client

    def trusted_client(**options: Any) -> httpx.Client:
        return real_client(verify=ssl.create_default_context(cafile=cert_path), **options)

    monkeypatch.setattr(socket.socket, "connect", redirected_connect)
    monkeypatch.setattr(httpx, "Client", trusted_client)
    claim = ClaimedDelivery(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        1,
        "order.created",
        {},
        "https://hook.example.com/hook",
        b"test-key",
    )
    try:
        assert (
            send_webhook(claim, lambda _host: [ipaddress.ip_address("8.8.8.8")]).status_code == 200
        )
        assert connected_to == [("8.8.8.8", 443)]
        assert received_hosts == ["hook.example.com"]
        with pytest.raises(httpx.ConnectError):
            send_webhook(
                replace(claim, url="https://wrong.example.com/hook"),
                lambda _host: [ipaddress.ip_address("8.8.8.8")],
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_timeout_after_receiver_accepts_can_send_same_delivery_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eventflow.delivery import ClaimedDelivery

    received: list[bytes] = []

    class SlowThenFastReceiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(body)
            if len(received) == 1:
                time.sleep(0.2)
            try:
                self.send_response(200)
                self.end_headers()
            except BrokenPipeError:
                pass

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowThenFastReceiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/hook"
    monkeypatch.setenv("EVENTFLOW_ENVIRONMENT", "test")
    monkeypatch.setenv("EVENTFLOW_LOCAL_TEST_RECEIVER_URL", url)
    get_settings.cache_clear()
    claim = ClaimedDelivery(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        1,
        "order.created",
        {"id": 1},
        url,
        b"test-key",
    )
    try:
        with pytest.raises(httpx.ReadTimeout):
            send_webhook(claim, timeout=httpx.Timeout(connect=1, read=0.05, write=1, pool=1))
        assert send_webhook(claim).status_code == 200
        assert len(received) == 2 and received[0] == received[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        get_settings.cache_clear()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_recovery_duplicate_notice_expired_lease_and_signed_receiver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[tuple[bytes, dict[str, str]]] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((body, dict(self.headers)))
            payload = json.loads(body)
            expected = hmac.new(
                secret,
                self.headers["X-EventFlow-Timestamp"].encode() + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            valid = (
                hmac.compare_digest(self.headers["X-EventFlow-Signature"], f"v1={expected}")
                and payload["event_id"] == self.headers["X-EventFlow-Event-Id"]
                and payload["delivery_id"] == self.headers["X-EventFlow-Delivery-Id"]
                and str(payload["generation"]) == self.headers["X-EventFlow-Generation"]
            )
            self.send_response(200 if valid else 401)
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
    tenant_id, endpoint_id, event_id, delivery_id, outbox_id = [uuid.uuid4() for _ in range(5)]
    secret = b"test-signing-key"
    engine = make_sync_engine()
    try:
        with engine.begin() as connection:
            connection.execute(insert(Organization).values(id=tenant_id, name="delivery-test"))
            connection.execute(
                insert(Endpoint).values(
                    id=endpoint_id,
                    organization_id=tenant_id,
                    url=url,
                    signing_secret_ciphertext=secret,
                    active=True,
                )
            )
            connection.execute(
                insert(Event).values(
                    id=event_id,
                    organization_id=tenant_id,
                    event_type="order.created",
                    payload={"number": 1},
                )
            )
            connection.execute(
                insert(Delivery).values(
                    id=delivery_id,
                    organization_id=tenant_id,
                    event_id=event_id,
                    endpoint_id=endpoint_id,
                    status="pending",
                    generation=1,
                    attempt_count=0,
                )
            )
            connection.execute(
                insert(OutboxMessage).values(
                    id=outbox_id,
                    organization_id=tenant_id,
                    delivery_id=delivery_id,
                    generation=1,
                )
            )

        def broken_publish(_delivery_id: uuid.UUID) -> None:
            Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2).ping()

        with pytest.raises(RedisConnectionError):
            dispatch_outbox(engine, broken_publish)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(OutboxMessage.published_at).where(OutboxMessage.id == outbox_id)
                )
                is None
            )
        notices: list[uuid.UUID] = []
        dispatch_outbox(engine, notices.append)
        assert notices == [delivery_id]
        # Simulate a published notice lost before any worker receives it.
        reconcile_deliveries(engine, notices.append)
        assert notices == [delivery_id, delivery_id]
        first = claim_delivery(engine, delivery_id)
        assert first is not None
        assert claim_delivery(engine, delivery_id) is None
        with engine.begin() as connection:
            connection.execute(
                update(Delivery)
                .where(Delivery.id == delivery_id)
                .values(
                    lease_expires_at=select(DeliveryAttempt.started_at)
                    .where(DeliveryAttempt.id == first.attempt_id)
                    .scalar_subquery()
                    - timedelta(seconds=1)
                )
            )
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.id == first.attempt_id)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        reconcile_deliveries(engine, notices.append)
        assert notices[-1] == delivery_id
        second = claim_delivery(engine, delivery_id)
        assert second is not None and second.token != first.token
        finish_delivery(engine, first, 200, None)
        with engine.connect() as connection:
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                == "processing"
            )
        status = send_webhook(second)
        finish_delivery(engine, second, status.status_code, None)
        assert status.status_code == 200
        body, headers = received[0]
        payload = json.loads(body)
        assert payload["event_id"] == str(event_id)
        assert payload["delivery_id"] == str(delivery_id)
        assert headers["X-EventFlow-Event-Id"] == str(event_id)
        expected = hmac.new(
            secret, headers["X-EventFlow-Timestamp"].encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        assert headers["X-EventFlow-Signature"] == f"v1={expected}"
        with engine.connect() as connection:
            assert (
                connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                == "succeeded"
            )
            attempts = (
                connection.execute(
                    select(DeliveryAttempt.status)
                    .where(DeliveryAttempt.delivery_id == delivery_id)
                    .order_by(DeliveryAttempt.number)
                )
                .scalars()
                .all()
            )
            assert attempts == ["late_result", "succeeded"]

        # From API 202 through outbox, Redis, Celery, and a signature-checking receiver.
        raw_key = secrets.token_urlsafe(32)
        with engine.begin() as connection:
            connection.execute(
                insert(ApiKey).values(
                    id=uuid.uuid4(),
                    organization_id=tenant_id,
                    key_prefix=raw_key[:12],
                    key_hash=hash_api_key(raw_key),
                    scope="publish",
                )
            )
            connection.execute(
                insert(Subscription).values(
                    id=uuid.uuid4(),
                    organization_id=tenant_id,
                    endpoint_id=endpoint_id,
                    event_type="order.created",
                )
            )

        async def publish_via_api() -> uuid.UUID:
            async_engine = create_async_engine(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
            app.state.engine = async_engine
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/events",
                        headers={"Authorization": f"Bearer {raw_key}"},
                        json={"type": "order.created", "payload": {"number": 2}},
                    )
                    assert response.status_code == 202
                    return uuid.UUID(response.json()["event_id"])
            finally:
                await async_engine.dispose()

        event_two = asyncio.run(publish_via_api())
        with engine.connect() as connection:
            delivery_two = connection.scalar(
                select(Delivery.id).where(
                    Delivery.organization_id == tenant_id, Delivery.event_id == event_two
                )
            )
            assert delivery_two is not None
        queue = f"test-{uuid.uuid4()}"
        process = subprocess.Popen(
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
            ],
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            dispatch_outbox(engine, lambda item: deliver.apply_async(args=[str(item)], queue=queue))
            deadline = time.monotonic() + 15
            state = "pending"
            while time.monotonic() < deadline:
                with engine.connect() as connection:
                    state = (
                        connection.scalar(
                            select(Delivery.status).where(Delivery.id == delivery_two)
                        )
                        or "missing"
                    )
                if state == "succeeded":
                    break
                time.sleep(0.2)
            assert state == "succeeded"
            assert len(received) == 2
        finally:
            process.terminate()
            process.wait(timeout=5)
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(OutboxMessage).where(OutboxMessage.organization_id == tenant_id)
            )
            connection.execute(
                delete(DeliveryAttempt).where(DeliveryAttempt.organization_id == tenant_id)
            )
            connection.execute(delete(Delivery).where(Delivery.organization_id == tenant_id))
            connection.execute(delete(Event).where(Event.organization_id == tenant_id))
            connection.execute(
                delete(Subscription).where(Subscription.organization_id == tenant_id)
            )
            connection.execute(delete(Endpoint).where(Endpoint.organization_id == tenant_id))
            connection.execute(delete(ApiKey).where(ApiKey.organization_id == tenant_id))
            connection.execute(delete(Organization).where(Organization.id == tenant_id))
        engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        get_settings.cache_clear()


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_worker_death_recovers_from_postgresql(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    first_received = threading.Event()
    received_count = 0

    class SlowReceiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            nonlocal received_count
            self.rfile.read(int(self.headers["Content-Length"]))
            received_count += 1
            first_received.set()
            release.wait(timeout=10)
            try:
                self.send_response(200)
                self.end_headers()
            except BrokenPipeError:
                pass

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowReceiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/slow"
    monkeypatch.setenv("EVENTFLOW_ENVIRONMENT", "test")
    monkeypatch.setenv("EVENTFLOW_LOCAL_TEST_RECEIVER_URL", url)
    get_settings.cache_clear()
    tenant_id, endpoint_id, event_id, delivery_id, outbox_id = [uuid.uuid4() for _ in range(5)]
    engine = make_sync_engine()
    queue = f"test-{uuid.uuid4()}"

    def start_worker() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
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
            ],
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    process: subprocess.Popen[bytes] | None = None
    try:
        with engine.begin() as connection:
            connection.execute(insert(Organization).values(id=tenant_id, name="worker-death"))
            connection.execute(
                insert(Endpoint).values(
                    id=endpoint_id,
                    organization_id=tenant_id,
                    url=url,
                    signing_secret_ciphertext=b"death-test-key",
                    active=True,
                )
            )
            connection.execute(
                insert(Event).values(
                    id=event_id,
                    organization_id=tenant_id,
                    event_type="order.created",
                    payload={"number": 3},
                )
            )
            connection.execute(
                insert(Delivery).values(
                    id=delivery_id,
                    organization_id=tenant_id,
                    event_id=event_id,
                    endpoint_id=endpoint_id,
                    status="pending",
                    generation=1,
                    attempt_count=0,
                )
            )
            connection.execute(
                insert(OutboxMessage).values(
                    id=outbox_id,
                    organization_id=tenant_id,
                    delivery_id=delivery_id,
                    generation=1,
                )
            )
        process = start_worker()
        dispatch_outbox(engine, lambda item: deliver.apply_async(args=[str(item)], queue=queue))
        deadline = time.monotonic() + 15
        state = "pending"
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                state = (
                    connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                    or "missing"
                )
            if state == "processing":
                break
            time.sleep(0.2)
        assert state == "processing"
        assert first_received.wait(timeout=10)
        process.kill()
        process.wait(timeout=5)
        process = None
        release.set()
        with engine.begin() as connection:
            connection.execute(
                update(Delivery)
                .where(Delivery.id == delivery_id)
                .values(
                    lease_expires_at=select(DeliveryAttempt.started_at)
                    .where(DeliveryAttempt.delivery_id == delivery_id)
                    .scalar_subquery()
                    - timedelta(seconds=1)
                )
            )
            connection.execute(
                update(DeliveryAttempt)
                .where(DeliveryAttempt.delivery_id == delivery_id)
                .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
            )
        notices: list[uuid.UUID] = []
        assert reconcile_deliveries(engine, notices.append) == 1
        assert notices == [delivery_id]
        process = start_worker()
        deliver.apply_async(args=[str(delivery_id)], queue=queue)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                state = (
                    connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                    or "missing"
                )
            if state == "succeeded":
                break
            time.sleep(0.2)
        assert state == "succeeded"
        assert received_count == 2
        with engine.connect() as connection:
            assert connection.execute(
                select(DeliveryAttempt.number)
                .where(DeliveryAttempt.delivery_id == delivery_id)
                .order_by(DeliveryAttempt.number)
            ).scalars().all() == [1, 2]
    finally:
        release.set()
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
        with engine.begin() as connection:
            connection.execute(
                delete(OutboxMessage).where(OutboxMessage.organization_id == tenant_id)
            )
            connection.execute(
                delete(DeliveryAttempt).where(DeliveryAttempt.organization_id == tenant_id)
            )
            connection.execute(delete(Delivery).where(Delivery.organization_id == tenant_id))
            connection.execute(delete(Event).where(Event.organization_id == tenant_id))
            connection.execute(delete(Endpoint).where(Endpoint.organization_id == tenant_id))
            connection.execute(delete(Organization).where(Organization.id == tenant_id))
        engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        get_settings.cache_clear()
