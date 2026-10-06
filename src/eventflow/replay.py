"""Internal, tenant-authorized replay with an immutable audit row."""

import argparse
import getpass
import uuid

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eventflow.delivery import make_sync_engine
from eventflow.ingest import hash_api_key
from eventflow.models import ApiKey, Delivery, OutboxMessage, ReplayAudit


class ReplayDenied(Exception):
    pass


class ReplayUnavailable(Exception):
    pass


def replay_delivery(engine: Engine, delivery_id: uuid.UUID, management_key: str) -> int:
    with Session(engine) as session, session.begin():
        actor = session.scalar(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(management_key),
                ApiKey.scope == "manage",
                ApiKey.revoked_at.is_(None),
            )
        )
        if actor is None:
            raise ReplayDenied()
        delivery = session.scalar(
            select(Delivery)
            .where(
                Delivery.id == delivery_id,
                Delivery.organization_id == actor.organization_id,
            )
            .with_for_update()
        )
        if delivery is None:
            raise ReplayDenied()
        if delivery.status != "dead_lettered":
            raise ReplayUnavailable()
        delivery.generation += 1
        delivery.status = "pending"
        delivery.next_attempt_at = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        session.add(
            ReplayAudit(
                id=uuid.uuid4(),
                organization_id=actor.organization_id,
                delivery_id=delivery.id,
                actor_key_id=actor.id,
                generation=delivery.generation,
            )
        )
        session.add(
            OutboxMessage(
                id=uuid.uuid4(),
                organization_id=actor.organization_id,
                delivery_id=delivery.id,
                generation=delivery.generation,
            )
        )
        return delivery.generation


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a dead-lettered delivery")
    parser.add_argument("delivery_id", type=uuid.UUID)
    args = parser.parse_args()
    management_key = getpass.getpass("Management API key: ")
    engine = make_sync_engine()
    try:
        generation = replay_delivery(engine, args.delivery_id, management_key)
        print(f"delivery_id={args.delivery_id} generation={generation}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
