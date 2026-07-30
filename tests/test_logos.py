from app.core.logos import logo_url_for, peer_card


def test_equity_logo_url() -> None:
    assert logo_url_for("AAPL").endswith("/AAPL")
    assert logo_url_for("BRK-B").endswith("/BRK.B")


def test_crypto_and_forex_logo_urls() -> None:
    assert "btc" in logo_url_for("BTC-USD")
    assert "eu" in logo_url_for("EUR-USD")
    assert "pl" in logo_url_for("USD-PLN")


def test_peer_card_includes_logo_and_known_name() -> None:
    card = peer_card("AAPL")
    assert card["symbol"] == "AAPL"
    assert card["logo"].startswith("https://")
    assert card["name"] == "Apple Inc."
