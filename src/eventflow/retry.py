"""Deterministic policy inputs for durable delivery scheduling."""

import random
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

MAX_RETRY_AFTER_SECONDS = 3600
MAX_BACKOFF_SECONDS = 900


def classify_result(response_status: int | None, error: str | None) -> str:
    if error == "unsafe_destination":
        return "permanent"
    if response_status is None:
        return "retry"
    if 200 <= response_status < 300:
        return "success"
    if response_status in (408, 429) or 500 <= response_status < 600:
        return "retry"
    return "permanent"


def backoff_seconds(attempt_in_generation: int) -> float:
    base = min(2.0 * 2 ** (attempt_in_generation - 1), MAX_BACKOFF_SECONDS)
    return float(min(MAX_BACKOFF_SECONDS, max(1.0, base * (0.5 + random.random()))))


def retry_after_seconds(value: str | None, now: datetime) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if re.fullmatch(r"[0-9]+", stripped):
        return min(int(stripped), MAX_RETRY_AFTER_SECONDS)
    try:
        moment = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is None:
        return None
    delta = (moment.astimezone(UTC) - now.astimezone(UTC)).total_seconds()
    return min(MAX_RETRY_AFTER_SECONDS, max(0, int(delta + 0.999)))
