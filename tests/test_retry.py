from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from eventflow.retry import backoff_seconds, classify_result, retry_after_seconds


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        (200, None, "success"),
        (204, None, "success"),
        (301, None, "permanent"),
        (400, None, "permanent"),
        (408, None, "retry"),
        (429, None, "retry"),
        (503, None, "retry"),
        (None, "transport_error", "retry"),
        (None, "unsafe_destination", "permanent"),
    ],
)
def test_response_classification(status: int | None, error: str | None, expected: str) -> None:
    assert classify_result(status, error) == expected


def test_backoff_grows_and_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("eventflow.retry.random.random", lambda: 0.5)
    assert [backoff_seconds(number) for number in range(1, 5)] == [2, 4, 8, 16]
    assert backoff_seconds(20) == 900


def test_retry_after_seconds_dates_invalid_and_maximum() -> None:
    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    assert retry_after_seconds("17", now) == 17
    assert retry_after_seconds("99999", now) == 3600
    assert retry_after_seconds(format_datetime(now + timedelta(seconds=90)), now) == 90
    assert retry_after_seconds(format_datetime(now - timedelta(seconds=5)), now) == 0
    assert retry_after_seconds("nonsense", now) is None
    assert retry_after_seconds("-3", now) is None
