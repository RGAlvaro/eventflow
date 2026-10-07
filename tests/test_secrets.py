import base64
import hashlib
import hmac
import json
import os
import uuid

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, insert, select, text
from sqlalchemy.engine import make_url

from alembic import command
from eventflow.config import get_settings
from eventflow.delivery import ClaimedDelivery, claim_delivery, make_sync_engine
from eventflow.models import (
    Delivery,
    DeliveryAttempt,
    Endpoint,
    EndpointSecretVersion,
    Event,
    Organization,
)
from eventflow.rotate_master import rotate_master_key
from eventflow.secrets import SecretUnavailable, decrypt_secret, encrypt_secret
from eventflow.webhook import signed_request
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


def test_receiver_can_verify_versions_during_signing_secret_rotation() -> None:
    receiver_keys = {1: b"first-secret", 2: b"second-secret"}
    for version, secret in receiver_keys.items():
        claim = ClaimedDelivery(
            delivery_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            attempt_id=uuid.uuid4(),
            token=uuid.uuid4(),
            event_id=uuid.uuid4(),
            generation=1,
            event_type="order.created",
            payload={"number": 7},
            url="https://example.com/hook",
            secret=secret,
            key_id=version,
        )
        body, headers = signed_request(claim)
        selected = receiver_keys[int(headers["X-EventFlow-Key-Id"])]
        expected = hmac.new(
            selected,
            headers["X-EventFlow-Timestamp"].encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(headers["X-EventFlow-Signature"], f"v1={expected}")


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_master_rotation_reencrypts_active_and_retained_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = make_sync_engine()
    tenant, endpoint_id = uuid.uuid4(), uuid.uuid4()
    old_keys = json.loads(os.environ["EVENTFLOW_ENCRYPTION_KEYS"])
    old_active = os.environ["EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID"]
    old_id, active_ciphertext = encrypt_secret(b"active-secret", tenant, endpoint_id, 2)
    _, retained_ciphertext = encrypt_secret(b"retained-secret", tenant, endpoint_id, 1)
    try:
        with engine.begin() as connection:
            connection.execute(insert(Organization).values(id=tenant, name="master-rotation"))
            connection.execute(
                insert(Endpoint).values(
                    id=endpoint_id,
                    organization_id=tenant,
                    url="https://example.com/hook",
                    signing_secret_key_id=old_id,
                    signing_secret_ciphertext=active_ciphertext,
                    signing_secret_version=2,
                    active=True,
                )
            )
            connection.execute(
                insert(EndpointSecretVersion),
                [
                    dict(
                        id=uuid.uuid4(),
                        organization_id=tenant,
                        endpoint_id=endpoint_id,
                        version=version,
                        encryption_key_id=old_id,
                        ciphertext=ciphertext,
                        status=status,
                    )
                    for version, ciphertext, status in (
                        (1, retained_ciphertext, "retiring"),
                        (2, active_ciphertext, "active"),
                    )
                ],
            )
        new_key = base64.b64encode(b"N" * 32).decode("ascii")
        monkeypatch.setenv("EVENTFLOW_ENCRYPTION_KEYS", json.dumps({**old_keys, "new": new_key}))
        monkeypatch.setenv("EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID", "new")
        assert rotate_master_key(engine) == 1
        assert rotate_master_key(engine) == 0
        monkeypatch.setenv("EVENTFLOW_ENCRYPTION_KEYS", json.dumps({"new": new_key}))
        with engine.connect() as connection:
            current = connection.execute(
                select(Endpoint.signing_secret_key_id, Endpoint.signing_secret_ciphertext).where(
                    Endpoint.id == endpoint_id
                )
            ).one()
            versions = connection.execute(
                select(
                    EndpointSecretVersion.version,
                    EndpointSecretVersion.encryption_key_id,
                    EndpointSecretVersion.ciphertext,
                ).where(EndpointSecretVersion.endpoint_id == endpoint_id)
            ).all()
        assert current.signing_secret_key_id == "new"
        assert (
            decrypt_secret("new", current.signing_secret_ciphertext, tenant, endpoint_id, 2)
            == b"active-secret"
        )
        assert {
            item.version: decrypt_secret(
                item.encryption_key_id, item.ciphertext, tenant, endpoint_id, item.version
            )
            for item in versions
        } == {1: b"retained-secret", 2: b"active-secret"}
    finally:
        monkeypatch.setenv("EVENTFLOW_ENCRYPTION_KEYS", json.dumps(old_keys))
        monkeypatch.setenv("EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID", old_active)
        with engine.begin() as connection:
            connection.execute(
                delete(EndpointSecretVersion).where(
                    EndpointSecretVersion.endpoint_id == endpoint_id
                )
            )
            connection.execute(delete(Endpoint).where(Endpoint.id == endpoint_id))
            connection.execute(delete(Organization).where(Organization.id == tenant))
        engine.dispose()


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


@pytest.mark.skipif(
    not os.getenv("EVENTFLOW_TEST_DATABASE_URL"), reason="PostgreSQL integration DSN unset"
)
def test_migration_encrypts_existing_endpoint_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    async_base_url = make_url(os.environ["EVENTFLOW_TEST_DATABASE_URL"])
    base_url = async_base_url.set(drivername="postgresql+psycopg")
    database_name = "eventflow_migration_" + uuid.uuid4().hex
    migration_url = base_url.set(database=database_name)
    migration_settings_url = async_base_url.set(database=database_name)
    admin_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    tenant_id, endpoint_id = uuid.uuid4(), uuid.uuid4()
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {database_name}"))
        with monkeypatch.context() as context:
            context.setenv(
                "EVENTFLOW_DATABASE_URL",
                migration_settings_url.render_as_string(hide_password=False),
            )
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "0003_failure_concurrency")
            migration_engine = create_engine(migration_url)
            try:
                with migration_engine.begin() as connection:
                    connection.execute(insert(Organization).values(id=tenant_id, name="legacy"))
                    connection.execute(
                        text(
                            "INSERT INTO endpoints "
                            "(id, organization_id, url, signing_secret_ciphertext, active) "
                            "VALUES (:id, :organization_id, :url, :secret, true)"
                        ),
                        {
                            "id": endpoint_id,
                            "organization_id": tenant_id,
                            "url": "https://example.com/hook",
                            "secret": b"legacy-secret",
                        },
                    )
                command.upgrade(Config("alembic.ini"), "head")
                with migration_engine.connect() as connection:
                    row = connection.execute(
                        select(
                            Endpoint.signing_secret_key_id,
                            Endpoint.signing_secret_ciphertext,
                            Endpoint.signing_secret_version,
                        ).where(Endpoint.id == endpoint_id)
                    ).one()
                    assert row.signing_secret_ciphertext != b"legacy-secret"
                    assert (
                        decrypt_secret(
                            row.signing_secret_key_id,
                            row.signing_secret_ciphertext,
                            tenant_id,
                            endpoint_id,
                            row.signing_secret_version,
                        )
                        == b"legacy-secret"
                    )
            finally:
                migration_engine.dispose()
    finally:
        get_settings.cache_clear()
        with admin_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {database_name}"))
        admin_engine.dispose()
