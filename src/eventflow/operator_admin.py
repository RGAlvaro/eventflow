"""Trusted server-side provisioning, rotation and revocation of demo operators."""

import argparse
import secrets
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eventflow.delivery import make_sync_engine
from eventflow.models import ManagementAudit, Operator, OperatorSession, Organization
from eventflow.operator_password import hash_password, normalize_username


def create_operator(
    engine: Engine, organization_id: uuid.UUID, username: str
) -> tuple[uuid.UUID, str]:
    normalized = normalize_username(username)
    raw_password = secrets.token_urlsafe(24)
    operator_id = uuid.uuid4()
    with Session(engine) as session, session.begin():
        organization = session.scalar(
            select(Organization.id).where(Organization.id == organization_id).with_for_update()
        )
        if organization is None:
            raise ValueError("Organization does not exist")
        if session.scalar(select(Operator.id).where(Operator.username == normalized)) is not None:
            raise ValueError("Username already exists")
        session.add(
            Operator(
                id=operator_id,
                organization_id=organization_id,
                username=normalized,
                password_hash=hash_password(raw_password),
            )
        )
        session.flush()
        session.add(
            ManagementAudit(
                id=uuid.uuid4(),
                organization_id=organization_id,
                actor_key_id=None,
                action="operator_created",
                subject_id=operator_id,
            )
        )
    return operator_id, raw_password


def change_operator(engine: Engine, username: str, disable: bool = False) -> str | None:
    normalized = normalize_username(username)
    raw_password = None if disable else secrets.token_urlsafe(24)
    with Session(engine) as session, session.begin():
        operator = session.scalar(
            select(Operator).where(Operator.username == normalized).with_for_update()
        )
        if operator is None:
            raise ValueError("Operator does not exist")
        if operator.disabled_at is not None:
            raise ValueError("Operator is disabled")
        if disable:
            operator.disabled_at = session.scalar(select(func.clock_timestamp()))
            action = "operator_disabled"
        else:
            assert raw_password is not None
            operator.password_hash = hash_password(raw_password)
            action = "operator_password_rotated"
        session.execute(delete(OperatorSession).where(OperatorSession.operator_id == operator.id))
        session.add(
            ManagementAudit(
                id=uuid.uuid4(),
                organization_id=operator.organization_id,
                actor_key_id=None,
                action=action,
                subject_id=operator.id,
            )
        )
    return raw_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage EventFlow demo operators on the server")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("organization_id", type=uuid.UUID)
    create.add_argument("username")
    for name in ("rotate", "disable"):
        subcommand = commands.add_parser(name)
        subcommand.add_argument("username")
    args = parser.parse_args()
    engine = make_sync_engine()
    try:
        if args.command == "create":
            operator_id, password = create_operator(engine, args.organization_id, args.username)
            print(f"operator_id={operator_id}")
            print(f"password={password}")
        else:
            new_password = change_operator(engine, args.username, disable=args.command == "disable")
            if new_password is not None:
                print(f"password={new_password}")
            else:
                print("operator_disabled=true")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
