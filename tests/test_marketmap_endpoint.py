from app.core.marketmap_stocks import marketmap_stocks
from app.schemas import MarketMapItem
from app.services.marketmap import _sort_items


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
        assert stock.symbol.replace("-", ".") in stock.logo or stock.symbol in stock.logo


def test_marketmap_sort_by_change_percent() -> None:
    items = [
        MarketMapItem(
            symbol="A",
            name="A",
            description="a",
            logo="https://example.com/a",
            sector="Tech",
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
            sector="Tech",
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
