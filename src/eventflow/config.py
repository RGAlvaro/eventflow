from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVENTFLOW_", env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://eventflow:eventflow@localhost:5432/eventflow",
        pattern=r"^postgresql\+asyncpg://",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", pattern=r"^rediss?://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
