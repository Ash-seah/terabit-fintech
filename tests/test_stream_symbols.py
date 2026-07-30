from app.core.config import Settings
from app.core.symbols import all_platform_symbols, curated_stream_symbols, normalize_symbol


def test_stream_symbols_always_include_curated_universe() -> None:
    settings = Settings(
        finnhub_api_key="test",
        redis_url="redis://localhost:6379/0",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        stream_symbols="AAPL,BTCUSDT",
    )
    curated = set(curated_stream_symbols())
    configured = set(settings.configured_stream_symbols)
    assert curated.issubset(configured)
    assert "MSFT" in configured
    assert "NVDA" in configured
    assert "BTC-USD" in configured
    assert "EUR-USD" in configured


def test_normalize_symbol_aliases() -> None:
    assert normalize_symbol("binance:btcusdt") == "BTC-USD"
    assert normalize_symbol("NVDA") == "NVDA"
    assert normalize_symbol("eurusd") == "EUR-USD"


def test_all_platform_symbols_cover_full_universe() -> None:
    symbols = set(all_platform_symbols())
    assert len(symbols) >= 200
    assert "AAPL" in symbols
    assert "BTC-USD" in symbols
    assert "USD-PLN" in symbols
    assert "XAU-USD" in symbols
