from app.core.config import Settings
from app.core.symbols import curated_stream_symbols


def test_stream_symbols_always_include_curated_universe() -> None:
    settings = Settings(
        finnhub_api_key="test",
        redis_url="redis://localhost:6379/0",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        stream_symbols="AAPL,BINANCE:BTCUSDT",
    )
    curated = set(curated_stream_symbols())
    configured = set(settings.configured_stream_symbols)
    assert curated.issubset(configured)
    assert "MSFT" in configured
    assert "NVDA" in configured
    assert "BINANCE:BTCUSDT" in configured
