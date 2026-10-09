from pathlib import Path
from typing import Literal, Optional

from pydantic import AliasChoices, Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    # --- environment -------------------------------------------------------------------------------------------
    ENV: Literal["development", "test", "production"] = "development"
    DEMO_MODE: bool = False  # allows the demo seeder to run and the UI to offer the labelled demo dataset
    AUTO_MIGRATE: bool = True  # run Alembic upgrade at API start (disable in production and migrate as a deploy step)

    # --- database ----------------------------------------------------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "terratrack"
    POSTGRES_USER: str = "terratrack"
    POSTGRES_PASSWORD: str = ""
    DATABASE_URL_OVERRIDE: Optional[str] = Field(default=None, validation_alias=AliasChoices("DATABASE_URL", "DATABASE_URL_OVERRIDE"))

    # --- auth --------------------------------------------------------------------------------------------------
    JWT_SECRET_KEY: str = Field(
        ...,
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
        min_length=32,
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    # --- Sentinel providers (server-side only) -----------------------------------------------------------------
    SENTINEL_PROVIDER: Literal["auto", "cdse", "sentinel_hub", "none"] = "auto"
    SENTINEL_HUB_CLIENT_ID: Optional[str] = None
    SENTINEL_HUB_CLIENT_SECRET: Optional[str] = None
    SENTINEL_HUB_BASE_URL: str = "https://services.sentinel-hub.com"
    SENTINEL_HUB_TOKEN_URL: Optional[str] = None  # default derived from the provider
    # Legacy variables kept so existing .env files still load (they are not used by the OAuth client).
    SENTINEL_HUB_PROCESS_API_KEY: Optional[str] = None
    SENTINEL_HUB_CATALOG_API_KEY: Optional[str] = None
    SENTINEL_HUB_STATISTICS_API_KEY: Optional[str] = None
    CDSE_STAC_URL: str = "https://stac.dataspace.copernicus.eu/v1"
    CDSE_SH_BASE_URL: str = "https://sh.dataspace.copernicus.eu"
    CDSE_TOKEN_URL: str = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    PROVIDER_TIMEOUT_S: float = 60.0
    PROVIDER_MAX_RETRIES: int = 3

    # --- API ---------------------------------------------------------------------------------------------------
    API_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- storage / limits --------------------------------------------------------------------------------------
    STORAGE_DIR: Path = BACKEND_ROOT / "storage"
    MAX_UPLOAD_MB: int = 2048
    MAX_RASTER_PIXELS: int = 64_000_000
    MAX_AOI_KM2: float = 2500.0
    TEMP_RETENTION_HOURS: int = 24

    # --- jobs --------------------------------------------------------------------------------------------------
    JOB_RUNNER: Literal["embedded", "external", "off"] = "embedded"  # embedded = worker loop inside the API process
    JOB_CONCURRENCY: int = 1
    JOB_POLL_SECONDS: float = 1.0
    JOB_STALE_MINUTES: int = 30

    # --- ML ----------------------------------------------------------------------------------------------------
    ML_ROOT: Path = REPO_ROOT / "ML"
    MODEL_DIR: Path = BACKEND_ROOT / "models"
    ML_DEVICE: Literal["auto", "cpu", "cuda"] = "auto"

    # --- optional LLM narration (deterministic analytics work without it) --------------------------------------
    LLM_PROVIDER: Literal["none", "anthropic", "openai_compatible"] = "none"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None

    # --- environmental layers ----------------------------------------------------------------------------------
    FIRMS_MAP_KEY: Optional[str] = None
    # OpenWeather Alerts API (server-side key only; the Alerts product needs a suitable OpenWeather plan)
    OPENWEATHER_API_KEY: Optional[str] = None
    OPENWEATHER_ALERTS_URL: str = "https://api.openweathermap.org/alerts/1.0"
    OPENWEATHER_TIMEOUT_S: float = 20.0
    WEATHER_MAX_AOI_KM2: float = 100_000.0
    WEATHER_MAX_VERTICES: int = 500
    WEATHER_LOOKAHEAD_HOURS: int = 48  # forecast window requested per refresh (provider supports up to ~5 days)
    WEATHER_MIN_REFRESH_S: int = 300  # on-demand refreshes of one AOI closer together than this return the stored result
    WEATHER_REFRESH_MINUTES: int = 0  # >0: refresh AOIs that have monitoring enabled on this interval (embedded runner only); min 15

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @computed_field
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def JWT_SECRET(self) -> str:
        """Compatibility accessor for existing JWT service code."""
        return self.JWT_SECRET_KEY

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.ENV == "production":
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS must list explicit origins in production (no '*').")
            if self.DEMO_MODE:
                raise ValueError("DEMO_MODE must be disabled in production.")
            if self.AUTO_MIGRATE:
                raise ValueError("AUTO_MIGRATE must be false in production; run `python -m app.migrate` as a deploy step.")
            if self.JWT_SECRET_KEY.lower().startswith(("test", "change", "secret", "dev")):
                raise ValueError("JWT_SECRET_KEY looks like a placeholder; generate a random secret.")
        return self


settings = Settings()
