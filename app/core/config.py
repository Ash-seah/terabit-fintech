from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Financial Data API"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    finnhub_api_key: SecretStr
    finnhub_rest_url: str = "https://finnhub.io/api/v1"
    finnhub_ws_url: str = "wss://ws.finnhub.io"
    redis_url: str
    database_url: str
    stream_symbols: str = "AAPL,BINANCE:BTCUSDT"
    cors_origins: str = "*"
    finnhub_rest_calls_per_minute: int = Field(default=55, ge=2, le=60)
    historical_cache_ttl_seconds: int = Field(default=900, ge=1)
    raw_trade_retention_days: int = Field(default=30, ge=1)
    frontend_rate_limit_per_minute: int = Field(default=120, ge=2)
    trade_batch_size: int = Field(default=500, ge=1)
    trade_flush_seconds: float = Field(default=2.0, gt=0)

    @property
    def configured_stream_symbols(self) -> tuple[str, ...]:
        return tuple(
            symbol.strip().upper() for symbol in self.stream_symbols.split(",") if symbol.strip()
        )

    @property
    def configured_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
