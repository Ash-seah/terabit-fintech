from app.core.symbols import (
    forex_catalog_payload,
    normalize_symbol,
    sanitize_forex_upstream_list,
    yfinance_symbol_for,
)


def test_forex_catalog_is_comprehensive() -> None:
    catalog = forex_catalog_payload()
    symbols = {item["symbol"] for item in catalog}
    assert len(catalog) >= 40
    assert "EUR-USD" in symbols
    assert "EUR-GBP" in symbols
    assert "XAU-USD" in symbols
    assert all("OANDA" not in item["symbol"] for item in catalog)
    assert all("Oanda" not in item["name"] for item in catalog)


def test_sanitize_forex_upstream_strips_vendor_labels() -> None:
    cleaned = sanitize_forex_upstream_list(
        [
            {
                "description": "Oanda EUR/GBP",
                "displaySymbol": "EUR/GBP",
                "symbol": "OANDA:EUR_GBP",
            },
            {
                "description": "Oanda Gold/USD",
                "displaySymbol": "XAU/USD",
                "symbol": "OANDA:XAU_USD",
            },
        ]
    )
    assert cleaned[0]["symbol"] == "EUR-GBP"
    assert cleaned[0]["name"] == "EUR/GBP"
    assert cleaned[1]["symbol"] == "XAU-USD"
    assert all("OANDA" not in item["symbol"] for item in cleaned)


def test_usd_pln_maps_to_yahoo_fx() -> None:
    assert yfinance_symbol_for("USD-PLN") == "PLN=X"
    assert yfinance_symbol_for("USD/PLN") == "PLN=X"
    assert normalize_symbol("USD/PLN") == "USD-PLN"
