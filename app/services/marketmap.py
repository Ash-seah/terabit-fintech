import logging
from datetime import UTC, datetime
from typing import Any

from app.core.symbols import AssetClassQuery, MarketMapEntry, marketmap_universe
from app.providers.yahoo import HistoricalProviderError, YahooFinanceProvider
from app.schemas import MarketMapItem, MarketMapResponse
from app.services.cache import Cache

logger = logging.getLogger(__name__)


class MarketMapService:
    """Bulk market-map cards: name, ticker, price, day change. Yahoo + live overlay."""

    def __init__(
        self,
        cache: Cache,
        yahoo: YahooFinanceProvider,
        ttl: int = 180,
    ) -> None:
        self.cache = cache
        self.yahoo = yahoo
        self.ttl = ttl

    async def get(self, asset_class: AssetClassQuery) -> MarketMapResponse:
        key = f"marketmap:{asset_class}:v1"
        cached = await self.cache.get_json(key)
        if cached is not None:
            return await self._with_live_prices(MarketMapResponse.model_validate(cached))

        async with self.cache.lock(key):
            cached = await self.cache.get_json(key)
            if cached is not None:
                return await self._with_live_prices(MarketMapResponse.model_validate(cached))

            universe = marketmap_universe(asset_class)
            quotes: dict[str, dict[str, Any]] = {}
            try:
                quotes = await self.yahoo.quotes(tuple(item.symbol for item in universe))
            except HistoricalProviderError:
                logger.warning("Market map quotes unavailable for %s", asset_class)

            items = [self._build_item(entry, quotes.get(entry.symbol, {})) for entry in universe]
            response = MarketMapResponse(asset_class=asset_class, count=len(items), items=items)
            await self.cache.set_json(key, response.model_dump(mode="json"), self.ttl)
            return await self._with_live_prices(response)

    async def _with_live_prices(self, response: MarketMapResponse) -> MarketMapResponse:
        updated: list[MarketMapItem] = []
        for item in response.items:
            latest = await self.cache.get_json(f"latest:{item.symbol}")
            if not isinstance(latest, dict) or latest.get("price") is None:
                updated.append(item)
                continue
            price = float(latest["price"])
            previous = item.previous_close
            change = price - previous if previous else item.change
            change_percent = (
                ((price - previous) / previous) * 100 if previous else item.change_percent
            )
            timestamp = item.timestamp
            if latest.get("timestamp"):
                timestamp = datetime.fromisoformat(str(latest["timestamp"]).replace("Z", "+00:00"))
            updated.append(
                item.model_copy(
                    update={
                        "price": price,
                        "change": change,
                        "change_percent": change_percent,
                        "timestamp": timestamp,
                    }
                )
            )
        return response.model_copy(update={"items": updated})

    def _build_item(self, entry: MarketMapEntry, quote: dict[str, Any]) -> MarketMapItem:
        price = _float(quote.get("c"))
        previous_close = _float(quote.get("pc"))
        change = _float(quote.get("d"))
        change_percent = _float(quote.get("dp"))
        timestamp: datetime | None = None
        if quote.get("t"):
            timestamp = datetime.fromtimestamp(float(quote["t"]), tz=UTC)
        return MarketMapItem(
            symbol=entry.symbol,
            name=entry.name,
            asset_class=entry.asset_class,
            price=price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            timestamp=timestamp,
        )


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
