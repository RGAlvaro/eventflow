from unittest.mock import AsyncMock, patch

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
