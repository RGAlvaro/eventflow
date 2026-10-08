from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from eventflow.api import ApiError, new_request_id, router
from eventflow.config import get_settings
from eventflow.db import make_engine
from eventflow.management import router as management_router


async def dependency_status(engine: AsyncEngine, redis: Redis) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        result["postgresql"] = "ok"
    except Exception:
        result["postgresql"] = "unavailable"
    try:
        await redis.ping()
        result["redis"] = "ok"
    except Exception:
        result["redis"] = "unavailable"
    return result


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.engine = make_engine()
    app.state.redis = Redis.from_url(get_settings().redis_url, socket_timeout=2)
    yield
    await app.state.redis.aclose()
    await app.state.engine.dispose()


app = FastAPI(title="EventFlow", lifespan=lifespan)
app.include_router(router)
app.include_router(management_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request.state.request_id = new_request_id()
    response = await call_next(request)
    response.headers["X-Request-Id"] = str(request.state.request_id)
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": str(request.state.request_id),
        },
    )


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(response: Response) -> dict[str, object]:
    checks = await dependency_status(app.state.engine, app.state.redis)
    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "unavailable", "dependencies": checks}
