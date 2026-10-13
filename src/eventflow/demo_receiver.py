"""Standalone, preconfigured demo webhook receiver. Run behind an HTTPS proxy."""

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, Response

Mode = Literal["success", "transient", "rate_limit", "fail_until_replay"]
MAX_BODY = 256 * 1024
MAX_SKEW_SECONDS = 300


@dataclass(frozen=True)
class SigningKey:
    value: bytes
    not_after: int | None = None


@dataclass(frozen=True)
class Route:
    mode: Mode
    keys: dict[int, SigningKey]


@dataclass(frozen=True)
class ReceiverConfig:
    routes: dict[str, Route]
    observation_token: str
    database_path: Path


def load_config(path: Path) -> ReceiverConfig:
    if path.stat().st_mode & 0o077:
        raise ValueError("Receiver configuration must be readable only by its owner")
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("routes"), dict):
        raise ValueError("Receiver routes are required")
    routes: dict[str, Route] = {}
    for name, entry in raw["routes"].items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
            raise ValueError("Invalid route name")
        if not isinstance(entry, dict) or entry.get("mode") not in (
            "success",
            "transient",
            "rate_limit",
            "fail_until_replay",
        ):
            raise ValueError("Invalid receiver mode")
        keys: dict[int, SigningKey] = {}
        for key_id, key_data in entry.get("keys", {}).items():
            if not str(key_id).isdigit() or not isinstance(key_data, dict):
                raise ValueError("Invalid signing key version")
            try:
                value = base64.b64decode(key_data["secret_base64"], altchars=b"-_", validate=True)
            except (KeyError, TypeError, ValueError, binascii.Error) as exc:
                raise ValueError("Invalid signing secret encoding") from exc
            if len(value) != 32:
                raise ValueError("Signing secrets must be 32 bytes")
            not_after = key_data.get("not_after")
            if not_after is not None and (not isinstance(not_after, int) or not_after <= 0):
                raise ValueError("Invalid signing key expiration")
            keys[int(key_id)] = SigningKey(value, not_after)
        if not keys:
            raise ValueError("Every route needs a signing key")
        routes[name] = Route(entry["mode"], keys)
    token = raw.get("observation_token")
    database_path = raw.get("database_path")
    if not routes or not isinstance(token, str) or len(token) < 32:
        raise ValueError("Receiver routes and a strong observation token are required")
    if not isinstance(database_path, str) or not Path(database_path).is_absolute():
        raise ValueError("Receiver database_path must be absolute")
    return ReceiverConfig(routes, token, Path(database_path))


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute("PRAGMA busy_timeout=5000")
        yield db
    finally:
        db.close()


def initialize(path: Path) -> None:
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("Receiver data directory must be readable only by its owner")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(descriptor)
    if path.stat().st_mode & 0o077:
        raise ValueError("Receiver database must be readable only by its owner")
    with connection(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS observations (
                route TEXT NOT NULL, delivery_id TEXT NOT NULL, generation INTEGER NOT NULL,
                event_id TEXT NOT NULL, request_count INTEGER NOT NULL,
                processed INTEGER NOT NULL, last_status INTEGER NOT NULL,
                last_received_at INTEGER NOT NULL,
                PRIMARY KEY (route, delivery_id, generation)
            )"""
        )
        db.commit()


def verified_identity(request: Request, body: bytes, route: Route) -> tuple[str, str, int] | None:
    headers = request.headers
    try:
        timestamp = headers["x-eventflow-timestamp"]
        key_id = int(headers["x-eventflow-key-id"])
        generation = int(headers["x-eventflow-generation"])
        event_id = str(uuid.UUID(headers["x-eventflow-event-id"]))
        delivery_id = str(uuid.UUID(headers["x-eventflow-delivery-id"]))
        signature = headers["x-eventflow-signature"]
        now = int(time.time())
        key = route.keys.get(key_id)
        if (
            key is None
            or key.not_after is not None
            and now > key.not_after
            or not timestamp.isascii()
            or not timestamp.isdecimal()
            or abs(now - int(timestamp)) > MAX_SKEW_SECONDS
            or generation < 1
            or not re.fullmatch(r"v1=[0-9a-f]{64}", signature)
        ):
            return None
        expected = hmac.new(
            key.value, timestamp.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, "v1=" + expected):
            return None
        data = json.loads(body)
        if not isinstance(data, dict) or (
            data.get("event_id") != event_id
            or data.get("delivery_id") != delivery_id
            or data.get("generation") != generation
            or data.get("version") != 1
        ):
            return None
        return event_id, delivery_id, generation
    except (KeyError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None


def response_status(mode: Mode, generation: int, count: int) -> int:
    if mode == "transient" and count <= 2:
        return 503
    if mode == "rate_limit" and count == 1:
        return 429
    if mode == "fail_until_replay" and generation == 1:
        return 503
    return 200


def record_request(
    config: ReceiverConfig, route_name: str, event_id: str, delivery_id: str, generation: int
) -> tuple[int, bool]:
    with connection(config.database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT request_count, processed, event_id FROM observations
               WHERE route=? AND delivery_id=? AND generation=?""",
            (route_name, delivery_id, generation),
        ).fetchone()
        if row is not None and row[2] != event_id:
            db.rollback()
            return 409, False
        count = (row[0] if row else 0) + 1
        duplicate = bool(row and row[1])
        status = (
            200 if duplicate else response_status(config.routes[route_name].mode, generation, count)
        )
        db.execute(
            """INSERT INTO observations
               (route, delivery_id, generation, event_id, request_count, processed,
                last_status, last_received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(route, delivery_id, generation) DO UPDATE SET
               request_count=excluded.request_count, processed=excluded.processed,
               last_status=excluded.last_status, last_received_at=excluded.last_received_at""",
            (
                route_name,
                delivery_id,
                generation,
                event_id,
                count,
                int(status == 200),
                status,
                int(time.time()),
            ),
        )
        db.commit()
        return status, duplicate


def read_observations(
    config: ReceiverConfig, route_name: str, delivery_id: str
) -> list[tuple[str, int, int, int, int, int]]:
    with connection(config.database_path) as db:
        return db.execute(
            """SELECT event_id, generation, request_count, processed, last_status,
                      last_received_at FROM observations
               WHERE route=? AND delivery_id=? ORDER BY generation""",
            (route_name, delivery_id),
        ).fetchall()


def create_app(config: ReceiverConfig) -> FastAPI:
    initialize(config.database_path)
    app = FastAPI(title="EventFlow demo receiver", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/hooks/{route_name}")
    async def receive(route_name: str, request: Request) -> Response:
        route = config.routes.get(route_name)
        if route is None:
            return Response(status_code=404)
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            return Response(status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return Response(status_code=413)
        identity = verified_identity(request, bytes(body), route)
        if identity is None:
            return Response(status_code=401)
        status, duplicate = await asyncio.to_thread(record_request, config, route_name, *identity)
        headers = {"X-EventFlow-Duplicate": "true" if duplicate else "false"}
        if status == 429:
            headers["Retry-After"] = "2"
        return Response(status_code=status, headers=headers)

    @app.get("/observations/{route_name}/{delivery_id}")
    async def observations(route_name: str, delivery_id: str, request: Request) -> Response:
        bearer = request.headers.get("authorization", "")
        if not hmac.compare_digest(bearer, "Bearer " + config.observation_token):
            return Response(status_code=401)
        if route_name not in config.routes:
            return Response(status_code=404)
        try:
            delivery_id = str(uuid.UUID(delivery_id))
        except ValueError:
            return Response(status_code=404)
        rows = await asyncio.to_thread(read_observations, config, route_name, delivery_id)
        content = json.dumps(
            {
                "delivery_id": delivery_id,
                "generations": [
                    {
                        "event_id": row[0],
                        "generation": row[1],
                        "request_count": row[2],
                        "signature_verified": True,
                        "processed": bool(row[3]),
                        "last_status": row[4],
                        "last_received_at": row[5],
                    }
                    for row in rows
                ],
            }
        )
        return Response(
            content, media_type="application/json", headers={"Cache-Control": "no-store"}
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    return app


def app_from_environment() -> FastAPI:
    config_path = os.environ.get("EVENTFLOW_RECEIVER_CONFIG")
    if not config_path:
        raise RuntimeError("EVENTFLOW_RECEIVER_CONFIG is required")
    return create_app(load_config(Path(config_path)))
