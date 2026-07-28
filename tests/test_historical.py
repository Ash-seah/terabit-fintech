import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from app.providers.yahoo import YahooFinanceProvider
from app.schemas import HistoricalPoint
from app.services.historical import HistoricalService


def point() -> HistoricalPoint:
    return HistoricalPoint(
        timestamp=datetime.now(UTC),
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        volume=100,
    )


@pytest.mark.asyncio
async def test_yahoo_provider_offloads_sync_fetch() -> None:
    provider = YahooFinanceProvider()
    main_thread = threading.get_ident()
    called_from = 0

    def fake_fetch(symbol: str, period: str, interval: str) -> list[HistoricalPoint]:
        nonlocal called_from
        called_from = threading.get_ident()
        return [point()]

    provider._history_sync = fake_fetch  # type: ignore[method-assign]
    result = await provider.history("AAPL", "1d", "1m")
    assert result
    assert called_from != main_thread


@pytest.mark.asyncio
async def test_historical_cache_hit_skips_provider() -> None:
    payload = {
        "symbol": "AAPL",
        "interval": "1d",
        "period": "1mo",
        "cached": False,
        "points": [point().model_dump(mode="json")],
    }

    class FakeCache:
        async def get_json(self, key: str) -> dict[str, Any]:
            return payload

        @asynccontextmanager
        async def lock(
            self, key: str, lock_ttl: int = 20, blocking_timeout: float = 5
        ) -> AsyncIterator[bool]:
            yield True

    class NeverProvider:
        async def history(self, symbol: str, period: str, interval: str) -> Any:
            raise AssertionError("provider should not run")

    service = HistoricalService(
        FakeCache(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        NeverProvider(),  # type: ignore[arg-type]
        900,
    )
    response = await service.get("AAPL", "1mo", "1d")
    assert response.cached is True
    assert response.symbol == "AAPL"
