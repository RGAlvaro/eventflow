from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from eventflow.config import get_settings


def make_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)
