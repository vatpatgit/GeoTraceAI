from typing import Optional
from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "terratrack"
    POSTGRES_USER: str = "terratrack"
    POSTGRES_PASSWORD: str = ""

    JWT_SECRET_KEY: str = Field(
        ...,
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
        min_length=32,
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    SENTINEL_HUB_CLIENT_ID: Optional[str] = None
    SENTINEL_HUB_CLIENT_SECRET: Optional[str] = None
    SENTINEL_HUB_PROCESS_API_KEY: Optional[str] = None
    SENTINEL_HUB_CATALOG_API_KEY: Optional[str] = None
    SENTINEL_HUB_STATISTICS_API_KEY: Optional[str] = None
    SENTINEL_HUB_BASE_URL: str = "https://services.sentinel-hub.com"

    API_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @computed_field
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def JWT_SECRET(self) -> str:
        """Compatibility accessor for existing JWT service code."""
        return self.JWT_SECRET_KEY

settings = Settings()
