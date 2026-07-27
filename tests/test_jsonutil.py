from app.core.jsonutil import dumps_plain


def test_dumps_plain_avoids_scientific_notation() -> None:
    payload = {
        "type": "trade",
        "data": [{"symbol": "BTC-USD", "price": 64931.29, "volume": 0.00008}],
    }
    encoded = dumps_plain(payload)
    assert "e-" not in encoded.lower()
    assert "0.00008" in encoded
    assert "64931.29" in encoded
