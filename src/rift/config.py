from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/rift"


class RiftSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    openrouter_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None

    max_attempts: int = 4
    token_budget: int = 250_000
    sandbox_seconds_budget: int = 900
    wall_clock_budget_s: int = 900

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str | None) -> str:
        if not v or not v.strip():
            return DEFAULT_DATABASE_URL
        url = v.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> RiftSettings:
    return RiftSettings()

