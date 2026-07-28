from app.core.catalogs import CRYPTO_CATALOG, STOCK_CATALOG
from app.core.symbols import marketmap_universe, yfinance_symbol_for


def test_stock_catalog_is_comprehensive() -> None:
    universe = marketmap_universe("stocks")
    symbols = {item.symbol for item in universe}
    assert len(universe) >= 100
    assert "AAPL" in symbols
    assert "NVDA" in symbols
    assert "BRK-B" in symbols
    assert all(item.asset_class == "equity" for item in universe)
    assert len(STOCK_CATALOG) == len(universe)


def test_crypto_catalog_is_comprehensive() -> None:
    universe = marketmap_universe("crypto")
    symbols = {item.symbol for item in universe}
    assert len(universe) >= 50
    assert {"BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"} <= symbols
    assert all(item.asset_class == "crypto" for item in universe)
    assert len(CRYPTO_CATALOG) == len(universe)


def test_forex_marketmap_universe() -> None:
    universe = marketmap_universe("forex")
    symbols = {item.symbol for item in universe}
    assert len(universe) >= 40
    assert "EUR-USD" in symbols
    assert "XAU-USD" in symbols
    assert all(item.asset_class == "forex" for item in universe)


def test_yahoo_mapping_distinguishes_asset_classes() -> None:
    assert yfinance_symbol_for("BTC-USD") == "BTC-USD"
    assert yfinance_symbol_for("AAPL") == "AAPL"
    assert yfinance_symbol_for("BRK-B") == "BRK-B"
    assert yfinance_symbol_for("EUR-GBP") == "EURGBP=X"
    assert yfinance_symbol_for("USD-JPY") == "JPY=X"
