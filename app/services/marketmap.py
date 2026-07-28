import asyncio
import logging
from typing import Any, Literal

from app.core.marketmap_stocks import MarketMapStock, marketmap_stocks
from app.providers.yahoo import HistoricalProviderError, YahooFinanceProvider
from app.schemas import MarketMapItem, MarketMapResponse
from app.services.cache import Cache

logger = logging.getLogger(__name__)

_SOFT_TTL = 86_400
_FRESH_MARKER = "1"
_CACHE_KEY = "marketmap:stocks:v1"

SortField = Literal[
    "change",
    "change_percent",
    "volatility",
    "market_cap",
    "price",
    "name",
    "symbol",
]
SortOrder = Literal["asc", "desc"]


class MarketMapService:
    """Lightweight stocks heatmap: static meta + cached Yahoo day change."""

    def __init__(
        self,
        cache: Cache,
        yahoo: YahooFinanceProvider,
        ttl: int = 180,
    ) -> None:
        self.cache = cache
        self.yahoo = yahoo
        self.ttl = ttl
        self._refresh_tasks: set[asyncio.Task[None]] = set()

    async def get(
        self,
        *,
        sorted_by: SortField = "change_percent",
        order: SortOrder | None = None,
        limit: int | None = None,
    ) -> MarketMapResponse:
        resolved_order = order or (
            "desc"
            if sorted_by in {"change", "change_percent", "volatility", "market_cap", "price"}
            else "asc"
        )
        prices = await self._price_map()
        universe = marketmap_stocks()
        latest = await self._latest_prices([stock.symbol for stock in universe])

        items = [
            self._build_item(stock, prices.get(stock.symbol), latest.get(stock.symbol))
            for stock in universe
        ]
        items = _sort_items(items, sorted_by, resolved_order)
        if limit is not None:
            items = items[: max(1, min(limit, 500))]

        return MarketMapResponse(
            count=len(items),
            sorted_by=sorted_by,
            order=resolved_order,
            items=items,
        )

    async def _price_map(self) -> dict[str, dict[str, Any]]:
        soft = await self.cache.get_json(_CACHE_KEY)
        if soft is None:
            # Fall back to symbols list cache so tiles still light up.
            soft = await self.cache.get_json("symbols:stocks:v2")
        if await self.cache.get_json(f"{_CACHE_KEY}:fresh") is None:
            self._schedule_refresh()
        return _index_prices(soft)

    def _schedule_refresh(self) -> None:
        task = asyncio.create_task(self._refresh(), name="marketmap-refresh")
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    def warm(self) -> None:
        self._schedule_refresh()

    async def _refresh(self) -> None:
        async with self.cache.lock(_CACHE_KEY, lock_ttl=120):
            if await self.cache.get_json(f"{_CACHE_KEY}:fresh") is not None:
                return
            symbols = tuple(stock.symbol for stock in marketmap_stocks())
            quotes: dict[str, dict[str, Any]] = {}
            try:
                quotes = await self.yahoo.quotes(symbols)
            except HistoricalProviderError:
                logger.warning("Market map Yahoo quotes unavailable")
            payload = {
                "items": [
                    {
                        "symbol": symbol,
                        "price": _float((quotes.get(symbol) or {}).get("c")),
                        "change": _float((quotes.get(symbol) or {}).get("d")),
                        "change_percent": _float((quotes.get(symbol) or {}).get("dp")),
                        "previous_close": _float((quotes.get(symbol) or {}).get("pc")),
                    }
                    for symbol in symbols
                ]
            }
            await self.cache.set_json(_CACHE_KEY, payload, _SOFT_TTL)
            if quotes:
                await self.cache.set_json(f"{_CACHE_KEY}:fresh", _FRESH_MARKER, self.ttl)

    async def _latest_prices(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        values = await self.cache.mget_json([f"latest:{symbol}" for symbol in symbols])
        out: dict[str, dict[str, Any]] = {}
        for symbol, value in zip(symbols, values, strict=True):
            if isinstance(value, dict) and value.get("price") is not None:
                out[symbol] = value
        return out

    def _build_item(
        self,
        stock: MarketMapStock,
        cached: dict[str, Any] | None,
        live: dict[str, Any] | None,
    ) -> MarketMapItem:
        price = _float((cached or {}).get("price"))
        change = _float((cached or {}).get("change"))
        change_percent = _float((cached or {}).get("change_percent"))
        previous = _float((cached or {}).get("previous_close"))

        if live is not None:
            live_price = float(live["price"])
            price = live_price
            if previous is not None:
                change = live_price - previous
                change_percent = (change / previous) * 100 if previous else change_percent

        return MarketMapItem(
            symbol=stock.symbol,
            name=stock.name,
            description=stock.description,
            logo=stock.logo,
            sector=stock.sector,
            market_cap=stock.market_cap,
            price=price,
            change=change,
            change_percent=change_percent,
        )


def _index_prices(soft: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(soft, dict):
        return {}
    items = soft.get("items")
    if not isinstance(items, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("symbol"):
            out[str(item["symbol"])] = item
    return out


def _sort_key(item: MarketMapItem, field: SortField) -> float | str | None:
    if field == "symbol":
        return item.symbol
    if field == "name":
        return item.name.lower()
    if field == "price":
        return item.price
    if field == "change":
        return item.change
    if field == "change_percent":
        return item.change_percent
    if field == "market_cap":
        return item.market_cap
    return abs(item.change_percent) if item.change_percent is not None else None


def _sort_items(
    items: list[MarketMapItem], sorted_by: SortField, order: SortOrder
) -> list[MarketMapItem]:
    reverse = order == "desc"
    keyed = [(_sort_key(item, sorted_by), item) for item in items]
    present = [(key, item) for key, item in keyed if key is not None]
    missing = [item for key, item in keyed if key is None]
    present.sort(key=lambda row: row[0], reverse=reverse)  # type: ignore[arg-type]
    return [item for _, item in present] + missing


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
