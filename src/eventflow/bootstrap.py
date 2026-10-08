"""Trusted operator provisioning for the first organization and management key."""

import argparse
import secrets
import uuid

from sqlalchemy.orm import Session

from eventflow.delivery import make_sync_engine
from eventflow.ingest import hash_api_key
from eventflow.models import ApiKey, ManagementAudit, Organization


def create_organization(name: str) -> tuple[uuid.UUID, str]:
    if not name.strip() or len(name) > 200:
        raise ValueError("Organization name must contain 1 to 200 characters")
    organization_id, key_id = uuid.uuid4(), uuid.uuid4()
    raw_key = secrets.token_urlsafe(32)
    engine = make_sync_engine()
    try:
        with Session(engine) as session, session.begin():
            session.add(Organization(id=organization_id, name=name.strip()))
            session.flush()
            session.add(
                ApiKey(
                    id=key_id,
                    organization_id=organization_id,
                    key_prefix=raw_key[:12],
                    key_hash=hash_api_key(raw_key),
                    scope="manage",
                )
            )
            session.flush()
            session.add(
                ManagementAudit(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    actor_key_id=None,
                    action="organization_created",
                    subject_id=organization_id,
                )
            )
        return organization_id, raw_key
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision an EventFlow organization")
    parser.add_argument("name", help="Organization name")
    args = parser.parse_args()
    organization_id, raw_key = create_organization(args.name)
    print(f"organization_id={organization_id}")
    print(f"management_key={raw_key}")


if __name__ == "__main__":
    main()
