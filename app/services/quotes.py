import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.providers.yahoo import HistoricalProviderError, YahooFinanceProvider
from app.schemas import MarketPayload
from app.services.cache import Cache

logger = logging.getLogger(__name__)


class QuoteService:
    """Quotes prefer live WebSocket cache, then Yahoo. Finnhub is unused here."""

    def __init__(self, cache: Cache, yahoo: YahooFinanceProvider, ttl: int = 120) -> None:
        self.cache = cache
        self.yahoo = yahoo
        self.ttl = ttl

    async def get(self, symbol: str) -> MarketPayload:
        key = f"quote:yahoo:{symbol}"
        latest = await self.cache.get_json(f"latest:{symbol}")
        cached = await self.cache.get_json(key)
        base: dict[str, Any] = cached if isinstance(cached, dict) else {}

        if isinstance(latest, dict) and latest.get("price") is not None:
            price = float(latest["price"])
            previous = float(base["pc"]) if base.get("pc") is not None else price
            change = price - previous
            change_percent = (change / previous) * 100 if previous else 0.0
            timestamp = latest.get("timestamp")
            unix_ts = (
                int(datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp())
                if timestamp
                else int(datetime.now(UTC).timestamp())
            )
            return {
                "c": price,
                "pc": previous,
                "d": change,
                "dp": change_percent,
                "o": base.get("o", price),
                "h": max(float(base.get("h", price)), price),
                "l": min(float(base.get("l", price)), price),
                "t": unix_ts,
            }

        if base:
            return base

        async with self.cache.lock(key, lock_ttl=60, blocking_timeout=0.05) as acquired:
            cached = await self.cache.get_json(key)
            if isinstance(cached, dict):
                return cached
            if not acquired:
                for _ in range(40):
                    await asyncio.sleep(0.25)
                    cached = await self.cache.get_json(key)
                    if isinstance(cached, dict):
                        return cached
                raise HistoricalProviderError(f"Quote still loading for {symbol}")
            try:
                quote = await self.yahoo.quote(symbol)
            except HistoricalProviderError:
                logger.warning("Yahoo quote failed for %s", symbol)
                raise
            await self.cache.set_json(key, quote, self.ttl)
            return quote
