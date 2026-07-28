from app.core.marketmap_crypto import marketmap_crypto
from app.core.marketmap_forex import marketmap_forex
from app.core.marketmap_stocks import marketmap_stocks
from app.schemas import MarketMapItem
from app.services.marketmap import _group_by_sector, _sort_items


def test_marketmap_catalog_has_logos_and_blurbs() -> None:
    stocks = marketmap_stocks()
    assert len(stocks) >= 80
    assert {s.symbol for s in stocks} >= {"AAPL", "NVDA", "JPM", "XOM"}
    for stock in stocks:
        assert stock.name
        assert stock.description
        assert stock.sector
        assert stock.market_cap > 0
        assert stock.logo.startswith("https://")


def test_forex_marketmap_catalog() -> None:
    pairs = marketmap_forex()
    symbols = {item.symbol for item in pairs}
    assert len(pairs) >= 40
    assert {"EUR-USD", "USD-PLN", "XAU-USD"} <= symbols
    assert {item.sector for item in pairs} >= {"Majors", "Metals", "Exotics"}
    for item in pairs:
        assert item.logo.startswith("https://")
        assert item.change_percent if False else item.name  # name present
        assert item.description


def test_crypto_marketmap_catalog() -> None:
    coins = marketmap_crypto()
    symbols = {item.symbol for item in coins}
    assert len(coins) >= 40
    assert {"BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"} <= symbols
    for item in coins:
        assert item.logo.startswith("https://")
        assert item.sector


def test_marketmap_sort_by_change_percent() -> None:
    items = [
        MarketMapItem(
            symbol="A",
            name="A",
            description="a",
            logo="https://example.com/a",
            sector="Technology",
            market_cap=1e11,
            price=10,
            change=1,
            change_percent=1.0,
        ),
        MarketMapItem(
            symbol="B",
            name="B",
            description="b",
            logo="https://example.com/b",
            sector="Technology",
            market_cap=2e11,
            price=20,
            change=-4,
            change_percent=-8.0,
        ),
        MarketMapItem(
            symbol="C",
            name="C",
            description="c",
            logo="https://example.com/c",
            sector="Energy",
            market_cap=3e11,
            price=None,
            change=None,
            change_percent=None,
        ),
    ]
    ranked = _sort_items(items, "change_percent", "desc")
    assert [item.symbol for item in ranked] == ["A", "B", "C"]
    movers = _sort_items(items, "volatility", "desc")
    assert movers[0].symbol == "B"


def test_marketmap_groups_sectors_by_importance_and_size() -> None:
    items = [
        MarketMapItem(
            symbol="XOM",
            name="Exxon",
            description="oil",
            logo="https://example.com/xom",
            sector="Energy",
            market_cap=5e11,
            price=100,
            change=1,
            change_percent=1.0,
        ),
        MarketMapItem(
            symbol="AAPL",
            name="Apple",
            description="tech",
            logo="https://example.com/aapl",
            sector="Technology",
            market_cap=3e12,
            price=190,
            change=2,
            change_percent=1.1,
        ),
        MarketMapItem(
            symbol="MSFT",
            name="Microsoft",
            description="tech",
            logo="https://example.com/msft",
            sector="Technology",
            market_cap=3e12,
            price=420,
            change=-3,
            change_percent=-0.7,
        ),
        MarketMapItem(
            symbol="JPM",
            name="JPMorgan",
            description="bank",
            logo="https://example.com/jpm",
            sector="Financials",
            market_cap=6e11,
            price=200,
            change=1,
            change_percent=0.5,
        ),
    ]
    sectors = _group_by_sector(items, "change_percent", "desc", limit=None, asset_class="stocks")
    assert [sector.sector for sector in sectors] == [
        "Technology",
        "Financials",
        "Energy",
    ]
    assert sectors[0].count == 2


def test_forex_sector_order_puts_majors_first() -> None:
    items = [
        MarketMapItem(
            symbol="USD-PLN",
            name="USD/PLN",
            description="pln",
            logo="https://example.com/pl",
            sector="Exotics",
            market_cap=1e10,
            change_percent=0.2,
        ),
        MarketMapItem(
            symbol="EUR-USD",
            name="EUR/USD",
            description="eur",
            logo="https://example.com/eu",
            sector="Majors",
            market_cap=1e12,
            change_percent=-0.1,
        ),
        MarketMapItem(
            symbol="XAU-USD",
            name="Gold",
            description="gold",
            logo="https://example.com/xau",
            sector="Metals",
            market_cap=4e11,
            change_percent=0.5,
        ),
    ]
    sectors = _group_by_sector(items, "change_percent", "desc", None, "forex")
    assert [s.sector for s in sectors] == ["Majors", "Metals", "Exotics"]
