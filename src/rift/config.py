from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/rift"


class RiftSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    daytona_api_url: str = "https://app.daytona.io/api"
    openrouter_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    daytona_api_key: SecretStr | None = None
    daytona_snapshot: str | None = None  # prebuilt snapshot (node/pnpm/playwright); None = Daytona default
    r2_access_key: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_account_id: str | None = None
    r2_bucket: str = "rift-storage"
    r2_public_base_url: str = ""  # custom domain bound to the bucket, e.g. https://play.example.com
    account_token: SecretStr | None = None

    max_attempts: int = 4
    token_budget: int = 250_000
    sandbox_seconds_budget: int = 900
    wall_clock_budget_s: int = 900

    @property
    def r2_endpoint_url(self) -> str | None:
        if not self.r2_account_id:
            return None
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, v: str | None) -> str:
        return (v or "development").strip().lower()

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
