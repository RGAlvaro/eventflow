import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast

import httpx
import pytest
import uvicorn
from sqlalchemy import delete, func, insert, select, update

from eventflow.config import get_settings
from eventflow.delivery import ClaimedDelivery, claim_delivery, finish_delivery, make_sync_engine
from eventflow.demo_receiver import Mode, ReceiverConfig, Route, SigningKey, create_app, load_config
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
from eventflow.webhook import send_webhook, signed_request
from tests.support import sealed_secret

SECRET = bytes(range(32))
TOKEN = "t" * 40


def config(path: Path, mode: Mode = "success") -> ReceiverConfig:
    return ReceiverConfig({"demo": Route(mode, {1: SigningKey(SECRET)})}, TOKEN, path)


def claim(url: str = "https://receiver.example.org/hooks/demo") -> ClaimedDelivery:
    return ClaimedDelivery(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        1,
        "order.created",
        {"number": 7},
        url,
        SECRET,
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("success", [200, 200, 200]),
        ("transient", [503, 503, 200]),
        ("rate_limit", [429, 200, 200]),
        ("fail_until_replay", [503, 503, 503]),
    ],
)
async def test_signed_modes_durable_dedup_and_private_observation(
    tmp_path: Path, mode: str, expected: list[int]
) -> None:
    receiver_config = config(tmp_path / "receiver.sqlite", cast(Mode, mode))
    app = create_app(receiver_config)
    delivery = claim()
    body, headers = signed_request(delivery)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://receiver"
    ) as client:
        responses = [
            await client.post("/hooks/demo", content=body, headers=headers) for _ in range(3)
        ]
        assert [response.status_code for response in responses] == expected
        if mode == "rate_limit":
            assert responses[0].headers["Retry-After"] == "2"
        assert responses[-1].headers["X-EventFlow-Duplicate"] == (
            "true" if mode in ("success", "rate_limit") else "false"
        )
        address = f"/observations/demo/{delivery.delivery_id}"
        assert (await client.get(address)).status_code == 401
        observed = await client.get(address, headers={"Authorization": f"Bearer {TOKEN}"})
        assert observed.status_code == 200
        assert observed.json() == {
            "delivery_id": str(delivery.delivery_id),
            "generations": [
                {
                    "event_id": str(delivery.event_id),
                    "generation": 1,
                    "request_count": 3,
                    "signature_verified": True,
                    "processed": expected[-1] == 200,
                    "last_status": expected[-1],
                    "last_received_at": observed.json()["generations"][0]["last_received_at"],
                }
            ],
        }
        assert "payload" not in observed.text
        assert SECRET.hex() not in observed.text
    # A new application process uses the same durable deduplication record.
    restarted = create_app(receiver_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://receiver"
    ) as client:
        repeated = await client.post("/hooks/demo", content=body, headers=headers)
        assert repeated.status_code == (200 if expected[-1] == 200 else 503)
        if mode == "fail_until_replay":
            replay = replace(delivery, generation=2)
            replay_body, replay_headers = signed_request(replay)
            assert (
                await client.post("/hooks/demo", content=replay_body, headers=replay_headers)
            ).status_code == 200
            observed = await client.get(
                f"/observations/demo/{delivery.delivery_id}",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert [item["generation"] for item in observed.json()["generations"]] == [1, 2]


async def test_rejects_tamper_wrong_route_stale_timestamp_and_expired_key(tmp_path: Path) -> None:
    receiver_config = config(tmp_path / "receiver.sqlite")
    app = create_app(receiver_config)
    delivery = claim()
    body, headers = signed_request(delivery)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://receiver"
    ) as client:
        assert (
            await client.post("/hooks/unknown", content=body, headers=headers)
        ).status_code == 404
        assert (
            await client.post("/hooks/demo", content=body + b" ", headers=headers)
        ).status_code == 401
        assert (
            await client.post(
                "/hooks/demo", content=body, headers={**headers, "X-EventFlow-Generation": "2"}
            )
        ).status_code == 401
        assert (
            await client.post(
                "/hooks/demo", content=body, headers={**headers, "X-EventFlow-Timestamp": "1"}
            )
        ).status_code == 401
        mismatch = json.dumps({**json.loads(body), "generation": 2}).encode()
        mismatched_signature = hmac.new(
            SECRET,
            headers["X-EventFlow-Timestamp"].encode() + b"." + mismatch,
            hashlib.sha256,
        ).hexdigest()
        assert (
            await client.post(
                "/hooks/demo",
                content=mismatch,
                headers={**headers, "X-EventFlow-Signature": f"v1={mismatched_signature}"},
            )
        ).status_code == 401
        assert (
            await client.post("/hooks/demo", content=b"x" * (256 * 1024 + 1), headers=headers)
        ).status_code == 413
        assert (await client.post("/hooks/demo", content=body, headers=headers)).status_code == 200
    expired = ReceiverConfig(
        {"demo": Route("success", {1: SigningKey(SECRET, int(time.time()) - 1)})},
        TOKEN,
        receiver_config.database_path,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(expired)), base_url="http://receiver"
    ) as client:
        assert (await client.post("/hooks/demo", content=body, headers=headers)).status_code == 401


async def test_route_keys_are_isolated(tmp_path: Path) -> None:
    receiver_config = ReceiverConfig(
        {
            "one": Route("success", {1: SigningKey(SECRET)}),
            "two": Route("success", {1: SigningKey(bytes(reversed(SECRET)))}),
        },
        TOKEN,
        tmp_path / "receiver.sqlite",
    )
    app = create_app(receiver_config)
    body, headers = signed_request(claim())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://receiver"
    ) as client:
        assert (await client.post("/hooks/one", content=body, headers=headers)).status_code == 200
        assert (await client.post("/hooks/two", content=body, headers=headers)).status_code == 401


async def test_secret_rotation_overlap_and_expiration(tmp_path: Path) -> None:
    new_secret = bytes(reversed(SECRET))
    database = tmp_path / "receiver.sqlite"
    receiver_config = ReceiverConfig(
        {"demo": Route("success", {1: SigningKey(SECRET), 2: SigningKey(new_secret)})},
        TOKEN,
        database,
    )
    app = create_app(receiver_config)
    old_delivery = claim()
    new_delivery = replace(claim(), secret=new_secret, key_id=2)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://receiver"
    ) as client:
        for delivery in (old_delivery, new_delivery):
            body, headers = signed_request(delivery)
            assert (
                await client.post("/hooks/demo", content=body, headers=headers)
            ).status_code == 200
    expired_config = ReceiverConfig(
        {
            "demo": Route(
                "success",
                {
                    1: SigningKey(SECRET, int(time.time()) - 1),
                    2: SigningKey(new_secret),
                },
            )
        },
        TOKEN,
        database,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(expired_config)),
        base_url="http://receiver",
    ) as client:
        body, headers = signed_request(old_delivery)
        assert (await client.post("/hooks/demo", content=body, headers=headers)).status_code == 401
        body, headers = signed_request(new_delivery)
        assert (await client.post("/hooks/demo", content=body, headers=headers)).status_code == 200


async def test_concurrent_duplicates_process_once(tmp_path: Path) -> None:
    app = create_app(config(tmp_path / "receiver.sqlite"))
    delivery = claim()
    body, headers = signed_request(delivery)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://receiver"
    ) as client:
        responses = await asyncio.gather(
            *(client.post("/hooks/demo", content=body, headers=headers) for _ in range(12))
        )
        assert all(response.status_code == 200 for response in responses)
        assert (
            sum(response.headers["X-EventFlow-Duplicate"] == "false" for response in responses) == 1
        )


def test_config_requires_owner_only_and_multiple_key_versions(tmp_path: Path) -> None:
    path = tmp_path / "receiver.json"
    path.write_text(
        json.dumps(
            {
                "routes": {
                    "demo": {
                        "mode": "success",
                        "keys": {
                            "1": {"secret_base64": base64.urlsafe_b64encode(SECRET).decode()},
                            "2": {
                                "secret_base64": base64.urlsafe_b64encode(
                                    bytes(reversed(SECRET))
                                ).decode(),
                                "not_after": int(time.time()) + 60,
                            },
                        },
                    }
                },
                "observation_token": TOKEN,
                "database_path": str(tmp_path / "receiver.sqlite"),
            }
        )
    )
    path.chmod(0o644)
    with pytest.raises(ValueError, match="owner"):
        load_config(path)
    path.chmod(0o600)
    assert set(load_config(path).routes["demo"].keys) == {1, 2}


def test_receiver_database_stays_private(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)
    database = data_dir / "receiver.sqlite"
    create_app(config(database))
    assert database.stat().st_mode & 0o077 == 0
    database.chmod(0o644)
    with pytest.raises(ValueError, match="database"):
        create_app(config(database))
    database.chmod(0o600)
    data_dir.chmod(0o755)
    with pytest.raises(ValueError, match="directory"):
        create_app(config(database))


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
@pytest.mark.parametrize(
    ("mode", "statuses"),
    [("transient", [503, 503, 200]), ("fail_until_replay", [503] * 7)],
)
def test_worker_claim_sends_to_actual_demo_receiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: Mode, statuses: list[int]
) -> None:
    receiver_app = create_app(config(tmp_path / "receiver.sqlite", mode))
    server = uvicorn.Server(
        uvicorn.Config(receiver_app, host="127.0.0.1", port=0, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    socket = server.servers[0].sockets[0]
    url = f"http://127.0.0.1:{socket.getsockname()[1]}/hooks/demo"
    monkeypatch.setenv("EVENTFLOW_ENVIRONMENT", "test")
    monkeypatch.setenv("EVENTFLOW_LOCAL_TEST_RECEIVER_URL", url)
    get_settings.cache_clear()
    engine = make_sync_engine()
    tenant_id, endpoint_id, event_id, delivery_id = [uuid.uuid4() for _ in range(4)]
    management_key = secrets.token_urlsafe(32)
    try:
        with engine.begin() as connection:
            connection.execute(insert(Organization).values(id=tenant_id, name="demo-receiver-test"))
            connection.execute(
                insert(ApiKey).values(
                    id=uuid.uuid4(),
                    organization_id=tenant_id,
                    key_prefix=management_key[:12],
                    key_hash=hash_api_key(management_key),
                    scope="manage",
                )
            )
            connection.execute(
                insert(Endpoint).values(
                    id=endpoint_id,
                    organization_id=tenant_id,
                    url=url,
                    **sealed_secret(SECRET, tenant_id, endpoint_id),
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
        for number in range(len(statuses)):
            delivery = claim_delivery(engine, delivery_id)
            assert delivery is not None
            result = send_webhook(delivery)
            assert result.status_code == statuses[number]
            finish_delivery(engine, delivery, result.status_code, None, result.retry_after)
            if number < len(statuses) - 1:
                with engine.begin() as connection:
                    connection.execute(
                        update(Delivery)
                        .where(Delivery.id == delivery_id)
                        .values(
                            next_attempt_at=func.clock_timestamp() - timedelta(seconds=1),
                        )
                    )
                    connection.execute(
                        update(DeliveryAttempt)
                        .where(DeliveryAttempt.id == delivery.attempt_id)
                        .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
                    )
        with engine.connect() as connection:
            assert connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id)) == (
                "succeeded" if mode == "transient" else "dead_lettered"
            )
            assert (
                connection.execute(
                    select(DeliveryAttempt.response_status)
                    .where(DeliveryAttempt.delivery_id == delivery_id)
                    .order_by(DeliveryAttempt.number)
                )
                .scalars()
                .all()
                == statuses
            )
        if mode == "fail_until_replay":
            assert replay_delivery(engine, delivery_id, management_key) == 2
            with engine.begin() as connection:
                connection.execute(
                    update(DeliveryAttempt)
                    .where(DeliveryAttempt.delivery_id == delivery_id)
                    .values(started_at=func.clock_timestamp() - timedelta(seconds=2))
                )
            replay_claim = claim_delivery(engine, delivery_id)
            assert replay_claim is not None
            replay_result = send_webhook(replay_claim)
            assert replay_result.status_code == 200
            finish_delivery(engine, replay_claim, replay_result.status_code, None)
            with engine.connect() as connection:
                assert (
                    connection.scalar(select(Delivery.status).where(Delivery.id == delivery_id))
                    == "succeeded"
                )

        async def read_observation() -> dict[str, object]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=receiver_app), base_url="http://receiver"
            ) as client:
                response = await client.get(
                    f"/observations/demo/{delivery_id}",
                    headers={"Authorization": f"Bearer {TOKEN}"},
                )
                return cast(dict[str, object], response.json())

        observation = asyncio.run(read_observation())
        assert observation["generations"][0]["request_count"] == len(statuses)  # type: ignore[index]
        if mode == "fail_until_replay":
            assert observation["generations"][1]["processed"] is True  # type: ignore[index]
    finally:
        with engine.begin() as connection:
            for model in (
                OutboxMessage,
                ReplayAudit,
                DeliveryAttempt,
                Delivery,
                Event,
                Endpoint,
                ApiKey,
            ):
                connection.execute(delete(model).where(model.organization_id == tenant_id))
            connection.execute(delete(Organization).where(Organization.id == tenant_id))
        engine.dispose()
        server.should_exit = True
        thread.join(timeout=5)
        get_settings.cache_clear()
