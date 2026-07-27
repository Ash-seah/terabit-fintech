from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.services.quotes import QuoteService


@pytest.mark.asyncio
async def test_quote_service_prefers_websocket_latest() -> None:
    class FakeCache:
        async def get_json(self, key: str) -> Any:
            if key.startswith("latest:"):
                return {"price": 201.5, "timestamp": "2026-07-27T12:00:00+00:00"}
            if key.startswith("quote:yahoo:"):
                return {"c": 200.0, "pc": 198.0, "d": 2.0, "dp": 1.01, "o": 199, "h": 202, "l": 197}
            return None

        @asynccontextmanager
        async def lock(self, key: str, lock_ttl: int = 20) -> AsyncIterator[None]:
            yield

    class NeverYahoo:
        async def quote(self, symbol: str) -> Any:
            raise AssertionError("yahoo should not be called")

    service = QuoteService(FakeCache(), NeverYahoo(), ttl=120)  # type: ignore[arg-type]
    quote = await service.get("AAPL")
    assert quote["c"] == 201.5
    assert quote["pc"] == 198.0
