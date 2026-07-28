from app.core.catalogs import CRYPTO_CATALOG, STOCK_CATALOG
from app.core.symbols import symbols_universe, yfinance_symbol_for
from app.schemas import SymbolCard
from app.services.symbols import _sort_items


def test_stock_catalog_is_comprehensive() -> None:
    universe = symbols_universe("stocks")
    symbols = {item.symbol for item in universe}
    assert len(universe) >= 100
    assert "AAPL" in symbols
    assert "NVDA" in symbols
    assert "BRK-B" in symbols
    assert all(item.asset_class == "equity" for item in universe)
    assert all(item.description for item in universe)
    assert len(STOCK_CATALOG) == len(universe)


def test_crypto_catalog_is_comprehensive() -> None:
    universe = symbols_universe("crypto")
    symbols = {item.symbol for item in universe}
    assert len(universe) >= 50
    assert {"BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"} <= symbols
    assert all(item.asset_class == "crypto" for item in universe)
    assert len(CRYPTO_CATALOG) == len(universe)


def test_forex_symbols_universe() -> None:
    universe = symbols_universe("forex")
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


def _card(
    symbol: str,
    change_percent: float | None,
    *,
    asset_class: str = "stocks",
) -> SymbolCard:
    return SymbolCard(
        symbol=symbol,
        name=symbol,
        description=symbol,
        asset_class=asset_class,  # type: ignore[arg-type]
        price=100.0,
        change=1.0 if change_percent is not None else None,
        change_percent=change_percent,
    )


def test_volatility_sort_puts_largest_moves_first() -> None:
    items = [
        _card("A", 1.0),
        _card("B", -9.0),
        _card("C", 3.0),
        _card("D", None),
    ]
    ranked = _sort_items(items, "volatility", "desc")
    assert [item.symbol for item in ranked] == ["B", "C", "A", "D"]


def test_change_percent_sort_and_nulls_last() -> None:
    items = [
        _card("A", 1.0),
        _card("B", -9.0),
        _card("C", None),
    ]
    ranked = _sort_items(items, "change_percent", "desc")
    assert [item.symbol for item in ranked] == ["A", "B", "C"]
