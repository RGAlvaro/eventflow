import base64
import json
import os
import uuid

import pytest
from sqlalchemy import delete, func, insert, select

from eventflow.delivery import claim_delivery, make_sync_engine
from eventflow.models import Delivery, DeliveryAttempt, Endpoint, Event, Organization
from eventflow.secrets import SecretUnavailable, decrypt_secret, encrypt_secret
from tests.support import sealed_secret


def test_ciphertext_is_randomized_and_bound_to_tenant_endpoint_and_version() -> None:
    tenant, endpoint, other_endpoint = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key_id, first = encrypt_secret(b"fixture-secret", tenant, endpoint, 1)
    _, second = encrypt_secret(b"fixture-secret", tenant, endpoint, 1)
    assert first != second
    assert b"fixture-secret" not in first
    assert decrypt_secret(key_id, first, tenant, endpoint, 1) == b"fixture-secret"
    for wrong_tenant, wrong_endpoint, wrong_version in (
        (uuid.uuid4(), endpoint, 1),
        (tenant, other_endpoint, 1),
        (tenant, endpoint, 2),
    ):
        with pytest.raises(SecretUnavailable):
            decrypt_secret(key_id, first, wrong_tenant, wrong_endpoint, wrong_version)
    corrupted = first[:-1] + bytes([first[-1] ^ 1])
    with pytest.raises(SecretUnavailable):
        decrypt_secret(key_id, corrupted, tenant, endpoint, 1)


def test_missing_key_fails_closed_and_master_key_can_rotate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, endpoint = uuid.uuid4(), uuid.uuid4()
    old_id, old_ciphertext = encrypt_secret(b"old-secret", tenant, endpoint, 1)
    new_key = base64.b64encode(b"N" * 32).decode("ascii")
    old_keys = json.loads(os.environ["EVENTFLOW_ENCRYPTION_KEYS"])
    monkeypatch.setenv("EVENTFLOW_ENCRYPTION_KEYS", json.dumps({**old_keys, "new": new_key}))
    monkeypatch.setenv("EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID", "new")
    new_id, new_ciphertext = encrypt_secret(
        decrypt_secret(old_id, old_ciphertext, tenant, endpoint, 1), tenant, endpoint, 1
    )
    assert new_id == "new"
    monkeypatch.setenv("EVENTFLOW_ENCRYPTION_KEYS", json.dumps({"new": new_key}))
    assert decrypt_secret(new_id, new_ciphertext, tenant, endpoint, 1) == b"old-secret"
    with pytest.raises(SecretUnavailable):
        decrypt_secret(old_id, old_ciphertext, tenant, endpoint, 1)


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_missing_master_key_does_not_consume_delivery_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = make_sync_engine()
    tenant, endpoint_id, event_id, delivery_id = [uuid.uuid4() for _ in range(4)]
    original_keys = os.environ["EVENTFLOW_ENCRYPTION_KEYS"]
    try:
        with engine.begin() as connection:
            connection.execute(insert(Organization).values(id=tenant, name="missing-key"))
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
                insert(Event).values(
                    id=event_id,
                    organization_id=tenant,
                    event_type="order.created",
                    payload={},
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
        monkeypatch.setenv("EVENTFLOW_ENCRYPTION_KEYS", "{}")
        with pytest.raises(SecretUnavailable):
            claim_delivery(engine, delivery_id)
        with engine.connect() as connection:
            status, attempts = connection.execute(
                select(Delivery.status, Delivery.attempt_count).where(Delivery.id == delivery_id)
            ).one()
            count = connection.scalar(
                select(func.count())
                .select_from(DeliveryAttempt)
                .where(DeliveryAttempt.delivery_id == delivery_id)
            )
            assert (status, attempts, count) == ("pending", 0, 0)
        monkeypatch.setenv("EVENTFLOW_ENCRYPTION_KEYS", original_keys)
        claim = claim_delivery(engine, delivery_id)
        assert claim is not None and claim.secret == b"fixture"
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(DeliveryAttempt).where(DeliveryAttempt.delivery_id == delivery_id)
            )
            connection.execute(delete(Delivery).where(Delivery.id == delivery_id))
            connection.execute(delete(Event).where(Event.id == event_id))
            connection.execute(delete(Endpoint).where(Endpoint.id == endpoint_id))
            connection.execute(delete(Organization).where(Organization.id == tenant))
        engine.dispose()
