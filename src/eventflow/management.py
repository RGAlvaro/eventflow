"""Tenant-scoped management API; publication credentials have no access here."""

import base64
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from anyio import to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.api import ApiError
from eventflow.ingest import hash_api_key
from eventflow.models import (
    ApiKey,
    Delivery,
    Endpoint,
    EndpointSecretVersion,
    Event,
    ManagementAudit,
    Organization,
    OutboxMessage,
    ReplayAudit,
    Subscription,
)
from eventflow.operator_session import authenticated_session
from eventflow.secrets import SecretUnavailable, encrypt_secret, generate_signing_secret
from eventflow.webhook import UnsafeDestination, validated_destination

router = APIRouter(prefix="/api/v1/management")
MAX_KEYS = 10
MAX_ENDPOINTS = 20
MAX_SUBSCRIPTIONS = 100
EVENT_TYPE = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"


@dataclass(frozen=True)
class ManagementPrincipal:
    id: uuid.UUID
    organization_id: uuid.UUID
    source: Literal["key", "operator"]


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["publish", "manage"]


class EndpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)


class EndpointUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    active: bool | None = None


class SubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = Field(min_length=1, max_length=100, pattern=EVENT_TYPE)


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    immediate: bool = False


def bearer_key(request: Request) -> str:
    scheme, separator, key = request.headers.get("authorization", "").partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not key:
        raise ApiError(401, "unauthorized", "A management API key is required")
    return key


async def management_actor(
    session: AsyncSession, request: Request, lock: bool = False
) -> ManagementPrincipal:
    if "authorization" in request.headers:
        query = select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(bearer_key(request)),
            ApiKey.scope == "manage",
            ApiKey.revoked_at.is_(None),
        )
        if lock:
            query = query.with_for_update()
        actor = await session.scalar(query)
        if actor is None:
            raise ApiError(401, "unauthorized", "A valid management API key is required")
        return ManagementPrincipal(actor.id, actor.organization_id, "key")
    identity, _ = await authenticated_session(
        session, request, csrf=request.method not in ("GET", "HEAD", "OPTIONS"), lock=lock
    )
    return ManagementPrincipal(identity.id, identity.organization_id, "operator")


async def lock_organization(session: AsyncSession, organization_id: uuid.UUID) -> None:
    value = await session.scalar(
        select(Organization.id).where(Organization.id == organization_id).with_for_update()
    )
    if value is None:
        raise ApiError(401, "unauthorized", "Organization is unavailable")


def audit(actor: ManagementPrincipal, action: str, subject_id: uuid.UUID) -> ManagementAudit:
    return ManagementAudit(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        actor_key_id=actor.id if actor.source == "key" else None,
        actor_operator_id=actor.id if actor.source == "operator" else None,
        action=action,
        subject_id=subject_id,
    )


async def safe_url(url: str) -> None:
    try:
        await to_thread.run_sync(validated_destination, url)
    except UnsafeDestination:
        raise ApiError(422, "unsafe_destination", "Destination violates the URL policy") from None


async def authorize_before_url(request: Request) -> None:
    # DNS validation must not be reachable without a valid management credential.
    async with AsyncSession(request.app.state.engine) as session:
        await management_actor(session, request)


@router.post("/api-keys", status_code=201)
async def create_key(request: Request, data: KeyRequest) -> dict[str, str]:
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session:
        async with session.begin():
            actor = await management_actor(session, request, lock=True)
            await lock_organization(session, actor.organization_id)
            count = await session.scalar(
                select(func.count())
                .select_from(ApiKey)
                .where(ApiKey.organization_id == actor.organization_id, ApiKey.revoked_at.is_(None))
            )
            if (count or 0) >= MAX_KEYS:
                raise ApiError(409, "resource_quota_exceeded", "Active API key quota exceeded")
            raw_key = secrets.token_urlsafe(32)
            key_id = uuid.uuid4()
            session.add(
                ApiKey(
                    id=key_id,
                    organization_id=actor.organization_id,
                    key_prefix=raw_key[:12],
                    key_hash=hash_api_key(raw_key),
                    scope=data.scope,
                )
            )
            session.add(audit(actor, "api_key_created", key_id))
    return {"id": str(key_id), "scope": data.scope, "key": raw_key}


@router.get("/api-keys")
async def list_keys(request: Request) -> list[dict[str, str | None]]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        rows = (
            await session.scalars(
                select(ApiKey)
                .where(ApiKey.organization_id == actor.organization_id)
                .order_by(ApiKey.created_at, ApiKey.id)
            )
        ).all()
        return [
            {
                "id": str(item.id),
                "prefix": item.key_prefix,
                "scope": item.scope,
                "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
            }
            for item in rows
        ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_key(request: Request, key_id: uuid.UUID) -> None:
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        actor = await management_actor(session, request, lock=True)
        await lock_organization(session, actor.organization_id)
        target = await session.scalar(
            select(ApiKey)
            .where(ApiKey.id == key_id, ApiKey.organization_id == actor.organization_id)
            .with_for_update()
        )
        if target is None:
            raise ApiError(404, "not_found", "API key not found")
        if target.revoked_at is None:
            target.revoked_at = await session.scalar(select(func.clock_timestamp()))
            session.add(audit(actor, "api_key_revoked", key_id))


@router.post("/endpoints", status_code=201)
async def create_endpoint(request: Request, data: EndpointRequest) -> dict[str, str | int]:
    await authorize_before_url(request)
    await safe_url(data.url)
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session:
        async with session.begin():
            actor = await management_actor(session, request, lock=True)
            await lock_organization(session, actor.organization_id)
            count = await session.scalar(
                select(func.count())
                .select_from(Endpoint)
                .where(Endpoint.organization_id == actor.organization_id)
            )
            if (count or 0) >= MAX_ENDPOINTS:
                raise ApiError(409, "resource_quota_exceeded", "Endpoint quota exceeded")
            endpoint_id = uuid.uuid4()
            secret = generate_signing_secret()
            try:
                encryption_key_id, ciphertext = encrypt_secret(
                    secret, actor.organization_id, endpoint_id, 1
                )
            except SecretUnavailable:
                raise ApiError(
                    503, "secret_store_unavailable", "Secret storage is unavailable"
                ) from None
            session.add(
                Endpoint(
                    id=endpoint_id,
                    organization_id=actor.organization_id,
                    url=data.url,
                    signing_secret_ciphertext=ciphertext,
                    signing_secret_key_id=encryption_key_id,
                    signing_secret_version=1,
                    active=True,
                )
            )
            session.add(
                EndpointSecretVersion(
                    id=uuid.uuid4(),
                    organization_id=actor.organization_id,
                    endpoint_id=endpoint_id,
                    version=1,
                    encryption_key_id=encryption_key_id,
                    ciphertext=ciphertext,
                    status="active",
                    activated_at=await session.scalar(select(func.clock_timestamp())),
                )
            )
            session.add(audit(actor, "endpoint_created", endpoint_id))
    return {
        "id": str(endpoint_id),
        "url": data.url,
        "key_id": 1,
        "signing_secret": base64.urlsafe_b64encode(secret).decode("ascii"),
    }


@router.get("/endpoints")
async def list_endpoints(request: Request) -> list[dict[str, str | int | bool]]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        rows = (
            await session.scalars(
                select(Endpoint)
                .where(Endpoint.organization_id == actor.organization_id)
                .order_by(Endpoint.created_at, Endpoint.id)
            )
        ).all()
        return [
            {
                "id": str(item.id),
                "url": item.url,
                "active": item.active,
                "key_id": item.signing_secret_version,
            }
            for item in rows
        ]


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_endpoint(request: Request, endpoint_id: uuid.UUID) -> None:
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        actor = await management_actor(session, request, lock=True)
        await lock_organization(session, actor.organization_id)
        endpoint = await session.scalar(
            select(Endpoint)
            .where(Endpoint.id == endpoint_id, Endpoint.organization_id == actor.organization_id)
            .with_for_update()
        )
        if endpoint is None:
            raise ApiError(404, "not_found", "Endpoint not found")
        has_delivery = await session.scalar(
            select(Delivery.id)
            .where(
                Delivery.organization_id == actor.organization_id,
                Delivery.endpoint_id == endpoint_id,
            )
            .limit(1)
        )
        if has_delivery is not None:
            raise ApiError(409, "endpoint_in_use", "Endpoint still has delivery history")
        await session.execute(
            delete(Subscription).where(
                Subscription.organization_id == actor.organization_id,
                Subscription.endpoint_id == endpoint_id,
            )
        )
        await session.execute(
            delete(EndpointSecretVersion).where(
                EndpointSecretVersion.organization_id == actor.organization_id,
                EndpointSecretVersion.endpoint_id == endpoint_id,
            )
        )
        await session.delete(endpoint)
        session.add(audit(actor, "endpoint_deleted", endpoint_id))


@router.patch("/endpoints/{endpoint_id}")
async def update_endpoint(
    request: Request, endpoint_id: uuid.UUID, data: EndpointUpdate
) -> dict[str, str | bool]:
    if data.url is not None:
        await authorize_before_url(request)
        await safe_url(data.url)
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        actor = await management_actor(session, request, lock=True)
        endpoint = await session.scalar(
            select(Endpoint)
            .where(Endpoint.id == endpoint_id, Endpoint.organization_id == actor.organization_id)
            .with_for_update()
        )
        if endpoint is None:
            raise ApiError(404, "not_found", "Endpoint not found")
        if data.url is not None:
            endpoint.url = data.url
        if data.active is not None:
            endpoint.active = data.active
        session.add(audit(actor, "endpoint_updated", endpoint_id))
        result: dict[str, str | bool] = {
            "id": str(endpoint_id),
            "url": endpoint.url,
            "active": endpoint.active,
        }
    return result


@router.post("/endpoints/{endpoint_id}/subscriptions", status_code=201)
async def create_subscription(
    request: Request, endpoint_id: uuid.UUID, data: SubscriptionRequest
) -> dict[str, str]:
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        actor = await management_actor(session, request, lock=True)
        await lock_organization(session, actor.organization_id)
        endpoint = await session.scalar(
            select(Endpoint.id).where(
                Endpoint.id == endpoint_id, Endpoint.organization_id == actor.organization_id
            )
        )
        if endpoint is None:
            raise ApiError(404, "not_found", "Endpoint not found")
        existing = await session.scalar(
            select(Subscription.id).where(
                Subscription.organization_id == actor.organization_id,
                Subscription.endpoint_id == endpoint_id,
                Subscription.event_type == data.event_type,
            )
        )
        if existing is not None:
            raise ApiError(409, "subscription_exists", "Subscription already exists")
        count = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.organization_id == actor.organization_id)
        )
        if (count or 0) >= MAX_SUBSCRIPTIONS:
            raise ApiError(409, "resource_quota_exceeded", "Subscription quota exceeded")
        subscription_id = uuid.uuid4()
        session.add(
            Subscription(
                id=subscription_id,
                organization_id=actor.organization_id,
                endpoint_id=endpoint_id,
                event_type=data.event_type,
            )
        )
        session.add(audit(actor, "subscription_created", subscription_id))
    return {
        "id": str(subscription_id),
        "endpoint_id": str(endpoint_id),
        "event_type": data.event_type,
    }


@router.get("/subscriptions")
async def list_subscriptions(request: Request) -> list[dict[str, str]]:
    async with AsyncSession(request.app.state.engine) as session:
        actor = await management_actor(session, request)
        rows = (
            await session.scalars(
                select(Subscription)
                .where(Subscription.organization_id == actor.organization_id)
                .order_by(Subscription.endpoint_id, Subscription.event_type)
            )
        ).all()
        return [
            {
                "id": str(item.id),
                "endpoint_id": str(item.endpoint_id),
                "event_type": item.event_type,
            }
            for item in rows
        ]


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def delete_subscription(request: Request, subscription_id: uuid.UUID) -> None:
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        actor = await management_actor(session, request, lock=True)
        await lock_organization(session, actor.organization_id)
        target = await session.scalar(
            select(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.organization_id == actor.organization_id,
            )
            .with_for_update()
        )
        if target is None:
            raise ApiError(404, "not_found", "Subscription not found")
        await session.delete(target)
        session.add(audit(actor, "subscription_deleted", subscription_id))


@router.post("/endpoints/{endpoint_id}/secrets", status_code=201)
async def prepare_secret_rotation(request: Request, endpoint_id: uuid.UUID) -> dict[str, str | int]:
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session:
        async with session.begin():
            actor = await management_actor(session, request, lock=True)
            endpoint = await session.scalar(
                select(Endpoint)
                .where(
                    Endpoint.id == endpoint_id, Endpoint.organization_id == actor.organization_id
                )
                .with_for_update()
            )
            if endpoint is None:
                raise ApiError(404, "not_found", "Endpoint not found")
            pending = await session.scalar(
                select(EndpointSecretVersion.id).where(
                    EndpointSecretVersion.organization_id == actor.organization_id,
                    EndpointSecretVersion.endpoint_id == endpoint_id,
                    EndpointSecretVersion.status == "pending",
                )
            )
            if pending is not None:
                raise ApiError(409, "rotation_pending", "A secret rotation is already pending")
            highest = await session.scalar(
                select(func.max(EndpointSecretVersion.version)).where(
                    EndpointSecretVersion.organization_id == actor.organization_id,
                    EndpointSecretVersion.endpoint_id == endpoint_id,
                )
            )
            version = (highest or endpoint.signing_secret_version) + 1
            secret = generate_signing_secret()
            try:
                encryption_key_id, ciphertext = encrypt_secret(
                    secret, actor.organization_id, endpoint_id, version
                )
            except SecretUnavailable:
                raise ApiError(
                    503, "secret_store_unavailable", "Secret storage is unavailable"
                ) from None
            session.add(
                EndpointSecretVersion(
                    id=uuid.uuid4(),
                    organization_id=actor.organization_id,
                    endpoint_id=endpoint_id,
                    version=version,
                    encryption_key_id=encryption_key_id,
                    ciphertext=ciphertext,
                    status="pending",
                )
            )
            session.add(audit(actor, "secret_prepared", endpoint_id))
    return {
        "endpoint_id": str(endpoint_id),
        "key_id": version,
        "signing_secret": base64.urlsafe_b64encode(secret).decode("ascii"),
    }


@router.post("/endpoints/{endpoint_id}/secrets/{version}/activate")
async def activate_secret_rotation(
    request: Request, endpoint_id: uuid.UUID, version: int, data: ActivationRequest
) -> dict[str, int | str]:
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        actor = await management_actor(session, request, lock=True)
        endpoint = await session.scalar(
            select(Endpoint)
            .where(Endpoint.id == endpoint_id, Endpoint.organization_id == actor.organization_id)
            .with_for_update()
        )
        if endpoint is None:
            raise ApiError(404, "not_found", "Endpoint not found")
        pending = await session.scalar(
            select(EndpointSecretVersion)
            .where(
                EndpointSecretVersion.organization_id == actor.organization_id,
                EndpointSecretVersion.endpoint_id == endpoint_id,
                EndpointSecretVersion.version == version,
                EndpointSecretVersion.status == "pending",
            )
            .with_for_update()
        )
        if pending is None:
            raise ApiError(409, "rotation_not_pending", "Secret version is not pending")
        previous = await session.scalar(
            select(EndpointSecretVersion)
            .where(
                EndpointSecretVersion.organization_id == actor.organization_id,
                EndpointSecretVersion.endpoint_id == endpoint_id,
                EndpointSecretVersion.version == endpoint.signing_secret_version,
                EndpointSecretVersion.status == "active",
            )
            .with_for_update()
        )
        if previous is None:
            raise RuntimeError("Active endpoint secret version disappeared")
        now = await session.scalar(select(func.clock_timestamp()))
        assert now is not None
        previous.status = "retiring"
        previous.expires_at = now if data.immediate else now + timedelta(hours=24)
        pending.status = "active"
        pending.activated_at = now
        endpoint.signing_secret_version = version
        endpoint.signing_secret_key_id = pending.encryption_key_id
        endpoint.signing_secret_ciphertext = pending.ciphertext
        session.add(audit(actor, "secret_activated", endpoint_id))
    return {"endpoint_id": str(endpoint_id), "key_id": version}


@router.post("/deliveries/{delivery_id}/replay")
async def replay(request: Request, delivery_id: uuid.UUID) -> dict[str, int | str]:
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        actor = await management_actor(session, request, lock=True)
        delivery = await session.scalar(
            select(Delivery)
            .where(Delivery.id == delivery_id, Delivery.organization_id == actor.organization_id)
            .with_for_update()
        )
        if delivery is None:
            raise ApiError(404, "not_found", "Delivery not found")
        if delivery.status != "dead_lettered":
            raise ApiError(409, "replay_unavailable", "Delivery is not dead lettered")
        event = await session.scalar(
            select(Event)
            .where(Event.id == delivery.event_id, Event.organization_id == actor.organization_id)
            .with_for_update()
        )
        if event is None:
            raise RuntimeError("Delivery event disappeared")
        delivery.generation += 1
        delivery.status = "pending"
        delivery.next_attempt_at = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        event.terminal_at = None
        session.add(
            ReplayAudit(
                id=uuid.uuid4(),
                organization_id=actor.organization_id,
                delivery_id=delivery.id,
                actor_key_id=actor.id if actor.source == "key" else None,
                actor_operator_id=actor.id if actor.source == "operator" else None,
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
        session.add(audit(actor, "delivery_replayed", delivery_id))
        generation = delivery.generation
    return {"delivery_id": str(delivery_id), "generation": generation}
