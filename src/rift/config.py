from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RiftSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str
    openrouter_api_key: SecretStr
    groq_api_key: SecretStr
