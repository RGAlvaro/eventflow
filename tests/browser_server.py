"""Isolated browser fixture: real API, PostgreSQL, Redis, signing and receiver logic."""

import asyncio
import base64
import ipaddress
import json
import logging
import os
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from sqlalchemy.orm import Session

import eventflow.delivery as delivery_module
import eventflow.demo_observations as bridge
from eventflow.app import app
from eventflow.config import get_settings
from eventflow.delivery import claim_delivery, dispatch_outbox, finish_delivery, make_sync_engine
from eventflow.demo_receiver import Mode, ReceiverConfig, Route, SigningKey, create_app
from eventflow.models import Endpoint, Operator, Organization, Subscription
from eventflow.operator_password import hash_password
from eventflow.secrets import encrypt_secret
from eventflow.webhook import signed_request

if os.environ.get("EVENTFLOW_ENVIRONMENT") != "test":
    raise RuntimeError("Browser fixture requires EVENTFLOW_ENVIRONMENT=test")

logger = logging.getLogger(__name__)
ORIGIN = "https://receiver.example.org"
TOKEN = "browser-fixture-observation-token-0123456789"
SCENARIOS: dict[str, tuple[str, Mode]] = {
    "success": ("demo.success", "success"),
    "transient": ("demo.transient", "transient"),
    "rate-limit": ("demo.rate_limit", "rate_limit"),
    "replay": ("demo.replay", "fail_until_replay"),
}
ROOT = tempfile.TemporaryDirectory(prefix="eventflow-browser-")
CONFIG_PATH = Path(ROOT.name) / "bridge.json"
os.environ["EVENTFLOW_DEMO_RECEIVER_BRIDGE_CONFIG_PATH"] = str(CONFIG_PATH)
os.environ.setdefault(
    "EVENTFLOW_ENCRYPTION_KEYS",
    json.dumps({"test": base64.b64encode(b"T" * 32).decode("ascii")}),
)
os.environ.setdefault("EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID", "test")
get_settings.cache_clear()


def seed() -> tuple[FastAPI, dict[uuid.UUID, str]]:
    organization_id = uuid.uuid4()
    endpoints: dict[uuid.UUID, str] = {}
    routes: dict[str, Route] = {}
    engine = make_sync_engine()
    try:
        with Session(engine) as session, session.begin():
            session.add(Organization(id=organization_id, name="Browser demo fixture"))
            session.flush()
            session.add(
                Operator(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    username="browser-operator",
                    password_hash=hash_password("browser-password"),
                )
            )
            for index, (name, (event_type, mode)) in enumerate(SCENARIOS.items(), start=1):
                endpoint_id = uuid.uuid4()
                secret = bytes([index]) * 32
                key_id, ciphertext = encrypt_secret(secret, organization_id, endpoint_id, 1)
                session.add(
                    Endpoint(
                        id=endpoint_id,
                        organization_id=organization_id,
                        url=f"{ORIGIN}/hooks/{name}",
                        active=True,
                        signing_secret_ciphertext=ciphertext,
                        signing_secret_key_id=key_id,
                        signing_secret_version=1,
                    )
                )
                session.flush()
                session.add(
                    Subscription(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        endpoint_id=endpoint_id,
                        event_type=event_type,
                    )
                )
                endpoints[endpoint_id] = name
                routes[name] = Route(mode, {1: SigningKey(secret)})
    finally:
        engine.dispose()
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "organization_id": str(organization_id),
                "origin": ORIGIN,
                "observation_token": TOKEN,
                "endpoints": {str(key): value for key, value in endpoints.items()},
            }
        )
    )
    CONFIG_PATH.chmod(0o600)
    receiver = create_app(ReceiverConfig(routes, TOKEN, Path(ROOT.name) / "receiver.sqlite"))
    return receiver, endpoints


def pump(receiver: FastAPI, stop: threading.Event) -> None:
    engine = make_sync_engine()

    async def send(route: str, body: bytes, headers: dict[str, str]) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=receiver), base_url=ORIGIN
        ) as client:
            return await client.post(f"/hooks/{route}", content=body, headers=headers)

    def publish(delivery_id: uuid.UUID) -> None:
        claim = claim_delivery(engine, delivery_id)
        if claim is None:
            return
        body, headers = signed_request(claim)
        headers["Host"] = "receiver.example.org"
        response = asyncio.run(send(claim.url.rsplit("/", 1)[-1], body, headers))
        finish_delivery(
            engine, claim, response.status_code, None, response.headers.get("Retry-After")
        )

    try:
        while not stop.wait(0.3):
            try:
                dispatch_outbox(engine, publish)
                delivery_module.reconcile_deliveries(engine, publish)
            except Exception:
                logger.exception("browser_fixture_pump_failed")
    finally:
        engine.dispose()


base_lifespan = app.router.lifespan_context


@asynccontextmanager
async def browser_lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with base_lifespan(application):
        receiver, _ = seed()
        bridge.resolve_public = lambda _host: [ipaddress.ip_address("8.8.8.8")]  # type: ignore[attr-defined,assignment]
        bridge.observation_transport = lambda: httpx.ASGITransport(app=receiver)
        delivery_module.backoff_seconds = lambda _attempt: 1.0  # type: ignore[attr-defined,assignment]
        stop = threading.Event()
        thread = threading.Thread(target=pump, args=(receiver, stop), daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)
            ROOT.cleanup()


app.router.lifespan_context = browser_lifespan
