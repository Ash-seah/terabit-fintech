import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from app.providers.yahoo import HistoricalProviderError
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


class MemoryCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.held = False

    async def get_json(self, key: str) -> Any | None:
        return self.store.get(key)

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        self.store[key] = value

    @asynccontextmanager
    async def lock(
        self, key: str, lock_ttl: int = 20, blocking_timeout: float = 5
    ) -> AsyncIterator[bool]:
        if self.held:
            yield False
            return
        self.held = True
        try:
            yield True
        finally:
            self.held = False


class SlowProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def history(self, symbol: str, period: str, interval: str) -> list[HistoricalPoint]:
        self.calls += 1
        await asyncio.sleep(0.2)
        return [point()]


class FakeSessions:
    def __call__(self) -> Any:
        return self

    async def __aenter__(self) -> Any:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_cold_chart_single_flight_waits_for_peer() -> None:
    cache = MemoryCache()
    provider = SlowProvider()

    async def fake_db(*args: Any, **kwargs: Any) -> None:
        return None

    service = HistoricalService(cache, FakeSessions(), provider, ttl=60)  # type: ignore[arg-type]
    service._read_db = fake_db  # type: ignore[method-assign]

    async def holder() -> Any:
        return await service.get("USD-PLN", "5d", "1h")

    async def waiter() -> Any:
        await asyncio.sleep(0.05)
        return await service.get("USD-PLN", "5d", "1h")

    first, second = await asyncio.gather(holder(), waiter())
    assert first.points
    assert second.points
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_soft_cache_avoids_provider_on_hit() -> None:
    cache = MemoryCache()
    key = "chart:USD-PLN:5d:1h"
    cache.store[key] = {
        "symbol": "USD-PLN",
        "interval": "1h",
        "period": "5d",
        "cached": False,
        "points": [point().model_dump(mode="json")],
    }

    class BoomProvider:
        async def history(self, *args: Any, **kwargs: Any) -> list[HistoricalPoint]:
            raise HistoricalProviderError("should not run")

    service = HistoricalService(cache, FakeSessions(), BoomProvider(), ttl=60)  # type: ignore[arg-type]
    response = await service.get("USD-PLN", "5d", "1h")
    assert response.cached is True
    assert response.symbol == "USD-PLN"
