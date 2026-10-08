"""Re-encrypt all endpoint secrets under the configured active master key."""

import uuid

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eventflow.delivery import make_sync_engine
from eventflow.models import Endpoint, EndpointSecretVersion, ManagementAudit
from eventflow.secrets import active_key_id, decrypt_secret, encrypt_secret


def rotate_master_key(engine: Engine) -> int:
    target_key_id = active_key_id()
    with Session(engine) as session:
        endpoint_ids = session.scalars(select(Endpoint.id).order_by(Endpoint.id)).all()
    rotated = 0
    for endpoint_id in endpoint_ids:
        with Session(engine) as session, session.begin():
            endpoint = session.scalar(
                select(Endpoint).where(Endpoint.id == endpoint_id).with_for_update()
            )
            if endpoint is None:
                continue
            versions = session.scalars(
                select(EndpointSecretVersion)
                .where(
                    EndpointSecretVersion.organization_id == endpoint.organization_id,
                    EndpointSecretVersion.endpoint_id == endpoint.id,
                )
                .order_by(EndpointSecretVersion.version)
                .with_for_update()
            ).all()
            changed = False
            for item in versions:
                if item.encryption_key_id == target_key_id:
                    continue
                raw = decrypt_secret(
                    item.encryption_key_id,
                    item.ciphertext,
                    endpoint.organization_id,
                    endpoint.id,
                    item.version,
                )
                item.encryption_key_id, item.ciphertext = encrypt_secret(
                    raw, endpoint.organization_id, endpoint.id, item.version
                )
                changed = True
            if endpoint.signing_secret_key_id != target_key_id:
                raw = decrypt_secret(
                    endpoint.signing_secret_key_id,
                    endpoint.signing_secret_ciphertext,
                    endpoint.organization_id,
                    endpoint.id,
                    endpoint.signing_secret_version,
                )
                endpoint.signing_secret_key_id, endpoint.signing_secret_ciphertext = encrypt_secret(
                    raw, endpoint.organization_id, endpoint.id, endpoint.signing_secret_version
                )
                changed = True
            if changed:
                session.add(
                    ManagementAudit(
                        id=uuid.uuid4(),
                        organization_id=endpoint.organization_id,
                        actor_key_id=None,
                        action="master_key_rotated",
                        subject_id=endpoint.id,
                    )
                )
                rotated += 1
    return rotated


def main() -> None:
    engine = make_sync_engine()
    try:
        count = rotate_master_key(engine)
        print(f"endpoints_reencrypted={count}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
