"""Server-side operator sessions for the browser, independent of API keys."""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from anyio import to_thread
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eventflow.api import ApiError
from eventflow.config import get_settings
from eventflow.ingest_limits import admit_login
from eventflow.models import ManagementAudit, Operator, OperatorSession
from eventflow.operator_password import DUMMY_PASSWORD_HASH, normalize_username, verify_password

router = APIRouter(prefix="/api/v1/session")
SESSION_SECONDS = 8 * 60 * 60
CSRF_COOKIE = "eventflow_csrf"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


@dataclass(frozen=True)
class OperatorIdentity:
    id: uuid.UUID
    organization_id: uuid.UUID
    username: str
    session_id: uuid.UUID
    expires_at: datetime


def session_cookie_name() -> str:
    return (
        "__Host-eventflow_session"
        if get_settings().environment == "production"
        else "eventflow_session"
    )


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def set_session_cookies(response: Response, token: str, csrf: str) -> None:
    secure = get_settings().environment == "production"
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=SESSION_SECONDS,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=SESSION_SECONDS,
        path="/",
        secure=secure,
        httponly=False,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_session_cookies(response: Response) -> None:
    secure = get_settings().environment == "production"
    response.delete_cookie(session_cookie_name(), path="/", secure=secure, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="strict")
    response.headers["Cache-Control"] = "no-store"


async def authenticated_session(
    session: AsyncSession, request: Request, *, csrf: bool = False, lock: bool = False
) -> tuple[OperatorIdentity, OperatorSession]:
    raw_token = request.cookies.get(session_cookie_name())
    if not raw_token or len(raw_token) > 256:
        raise ApiError(401, "unauthorized", "A valid operator session is required")
    hashed = token_hash(raw_token)
    if lock:
        # Login/rotation take the operator lock before touching sessions.
        # Keep that order for mutations and logout to avoid a database deadlock.
        candidate = (
            await session.execute(
                select(
                    OperatorSession.id,
                    OperatorSession.operator_id,
                    OperatorSession.organization_id,
                ).where(OperatorSession.token_hash == hashed)
            )
        ).one_or_none()
        if candidate is None:
            raise ApiError(401, "unauthorized", "A valid operator session is required")
        operator = await session.scalar(
            select(Operator)
            .where(
                Operator.id == candidate.operator_id,
                Operator.organization_id == candidate.organization_id,
            )
            .with_for_update()
        )
        operator_session = await session.scalar(
            select(OperatorSession)
            .where(
                OperatorSession.id == candidate.id,
                OperatorSession.token_hash == hashed,
                OperatorSession.revoked_at.is_(None),
                OperatorSession.expires_at > func.clock_timestamp(),
            )
            .with_for_update()
        )
        if operator is None or operator.disabled_at is not None or operator_session is None:
            raise ApiError(401, "unauthorized", "A valid operator session is required")
    else:
        query = (
            select(OperatorSession, Operator)
            .join(
                Operator,
                and_(
                    Operator.id == OperatorSession.operator_id,
                    Operator.organization_id == OperatorSession.organization_id,
                ),
            )
            .where(
                OperatorSession.token_hash == hashed,
                OperatorSession.revoked_at.is_(None),
                OperatorSession.expires_at > func.clock_timestamp(),
                Operator.disabled_at.is_(None),
            )
        )
        row = (await session.execute(query)).one_or_none()
        if row is None:
            raise ApiError(401, "unauthorized", "A valid operator session is required")
        operator_session, operator = row
    if csrf:
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get("x-csrf-token", "")
        if (
            not cookie
            or len(cookie) > 256
            or not hmac.compare_digest(cookie, header)
            or not hmac.compare_digest(token_hash(cookie), operator_session.csrf_hash)
        ):
            raise ApiError(403, "csrf_required", "A valid CSRF token is required")
    identity = OperatorIdentity(
        id=operator.id,
        organization_id=operator.organization_id,
        username=operator.username,
        session_id=operator_session.id,
        expires_at=operator_session.expires_at,
    )
    return identity, operator_session


@router.post("/login")
async def login(request: Request, response: Response, data: LoginRequest) -> dict[str, object]:
    try:
        username = normalize_username(data.username)
    except ValueError:
        raise ApiError(401, "invalid_credentials", "Invalid username or password") from None
    try:
        retry_after = await admit_login(request.app.state.redis, token_hash(username))
    except RedisError:
        raise ApiError(
            503, "login_limit_unavailable", "Login is temporarily unavailable", {"Retry-After": "5"}
        ) from None
    if retry_after is not None:
        raise ApiError(
            429, "login_rate_limited", "Too many login attempts", {"Retry-After": str(retry_after)}
        )
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session:
        async with session.begin():
            operator = await session.scalar(
                select(Operator).where(Operator.username == username).with_for_update()
            )
            stored = (
                operator.password_hash
                if operator is not None and operator.disabled_at is None
                else DUMMY_PASSWORD_HASH
            )
            valid = await to_thread.run_sync(verify_password, data.password, stored)
            if operator is None or operator.disabled_at is not None or not valid:
                raise ApiError(401, "invalid_credentials", "Invalid username or password")
            now = await session.scalar(select(func.clock_timestamp()))
            assert now is not None
            await session.execute(
                delete(OperatorSession).where(OperatorSession.operator_id == operator.id)
            )
            active = OperatorSession(
                id=uuid.uuid4(),
                organization_id=operator.organization_id,
                operator_id=operator.id,
                token_hash=token_hash(token),
                csrf_hash=token_hash(csrf),
                expires_at=now + timedelta(seconds=SESSION_SECONDS),
            )
            session.add(active)
            session.add(
                ManagementAudit(
                    id=uuid.uuid4(),
                    organization_id=operator.organization_id,
                    actor_operator_id=operator.id,
                    action="operator_login",
                    subject_id=active.id,
                )
            )
        result = {
            "operator_id": str(operator.id),
            "organization_id": str(operator.organization_id),
            "username": operator.username,
            "expires_at": active.expires_at,
        }
    set_session_cookies(response, token, csrf)
    return result


@router.get("")
async def current_session(request: Request, response: Response) -> dict[str, object]:
    async with AsyncSession(request.app.state.engine) as session:
        identity, _ = await authenticated_session(session, request)
    response.headers["Cache-Control"] = "no-store"
    return {
        "operator_id": str(identity.id),
        "organization_id": str(identity.organization_id),
        "username": identity.username,
        "expires_at": identity.expires_at,
    }


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    async with AsyncSession(request.app.state.engine) as session, session.begin():
        identity, active = await authenticated_session(session, request, csrf=True, lock=True)
        active.revoked_at = await session.scalar(select(func.clock_timestamp()))
        session.add(
            ManagementAudit(
                id=uuid.uuid4(),
                organization_id=identity.organization_id,
                actor_operator_id=identity.id,
                action="operator_logout",
                subject_id=identity.session_id,
            )
        )
    clear_session_cookies(response)
