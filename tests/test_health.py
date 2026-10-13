import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import Response

from eventflow.app import app, live, ready


async def test_live_does_not_check_dependencies() -> None:
    with patch("eventflow.app.dependency_status") as check:
        assert await live() == {"status": "ok"}
    check.assert_not_called()


async def test_ready_reports_dependency_failure() -> None:
    response = Response()
    app.state.engine = object()
    app.state.redis = object()
    with (
        patch(
            "eventflow.app.dependency_status",
            new=AsyncMock(return_value={"postgresql": "ok", "redis": "unavailable"}),
        ),
    ):
        result = await ready(response)
    assert response.status_code == 503
    assert result == {
        "status": "unavailable",
        "dependencies": {"postgresql": "ok", "redis": "unavailable"},
    }


async def test_request_log_omits_credentials_and_query(caplog: pytest.LogCaptureFixture) -> None:
    secret = "private-bearer-key-123"
    with caplog.at_level(logging.INFO, logger="eventflow.api"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/health/live?token={secret}", headers={"Authorization": f"Bearer {secret}"}
            )
    assert response.status_code == 200
    assert "request_completed" in caplog.text
    assert "/health/live" in caplog.text
    assert secret not in caplog.text
