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
    def __init__(self, delay: float = 0.2) -> None:
        self.calls = 0
        self.delay = delay

    async def history(self, symbol: str, period: str, interval: str) -> list[HistoricalPoint]:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return [point()]


class FakeSessions:
    def __call__(self) -> Any:
        return self

    async def __aenter__(self) -> Any:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_cold_chart_returns_within_two_seconds() -> None:
    cache = MemoryCache()
    provider = SlowProvider(delay=5.0)  # slower than quick-paint budget

    async def fake_db(*args: Any, **kwargs: Any) -> None:
        return None

    service = HistoricalService(cache, FakeSessions(), provider, ttl=60)  # type: ignore[arg-type]
    service._read_db_any = fake_db  # type: ignore[method-assign]

    started = asyncio.get_running_loop().time()
    response = await service.get("USD-PLN", "5d", "1h")
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 2.0
    assert response.loading is True or response.points
    # Provider may still be running in background; request itself must be fast.


@pytest.mark.asyncio
async def test_cold_chart_quick_paint_when_provider_fast() -> None:
    cache = MemoryCache()
    provider = SlowProvider(delay=0.05)

    async def fake_db(*args: Any, **kwargs: Any) -> None:
        return None

    service = HistoricalService(cache, FakeSessions(), provider, ttl=60)  # type: ignore[arg-type]
    service._read_db_any = fake_db  # type: ignore[method-assign]

    response = await service.get("USD-PLN", "5d", "1h")
    assert response.points
    assert response.loading is False
    assert provider.calls >= 1


@pytest.mark.asyncio
async def test_soft_cache_avoids_provider_on_hit() -> None:
    cache = MemoryCache()
    key = "chart:USD-PLN:5d:1h"
    cache.store[key] = {
        "symbol": "USD-PLN",
        "interval": "1h",
        "period": "5d",
        "cached": False,
        "partial": False,
        "loading": False,
        "points": [point().model_dump(mode="json")],
    }
    cache.store[f"{key}:fresh"] = "1"

    class BoomProvider:
        async def history(self, *args: Any, **kwargs: Any) -> list[HistoricalPoint]:
            raise HistoricalProviderError("should not run")

    service = HistoricalService(cache, FakeSessions(), BoomProvider(), ttl=60)  # type: ignore[arg-type]
    response = await service.get("USD-PLN", "5d", "1h")
    assert response.cached is True
    assert response.symbol == "USD-PLN"


@pytest.mark.asyncio
async def test_db_bars_served_without_waiting_on_provider() -> None:
    cache = MemoryCache()

    class BoomProvider:
        async def history(self, *args: Any, **kwargs: Any) -> list[HistoricalPoint]:
            await asyncio.sleep(5)
            raise HistoricalProviderError("too slow")

    service = HistoricalService(cache, FakeSessions(), BoomProvider(), ttl=60)  # type: ignore[arg-type]

    async def fake_db(*args: Any, **kwargs: Any) -> Any:
        from app.schemas import HistoricalResponse

        return HistoricalResponse(
            symbol="USD-PLN",
            interval="1h",
            period="5d",
            points=[point()],
        )

    service._read_db_any = fake_db  # type: ignore[method-assign]
    started = asyncio.get_running_loop().time()
    response = await service.get("USD-PLN", "5d", "1h")
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 1.0
    assert response.points
    assert response.cached is True
