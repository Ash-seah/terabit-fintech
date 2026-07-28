import asyncio
import logging
from typing import Any, Literal

from app.core.symbols import AssetClassQuery, CatalogEntry, symbols_universe
from app.providers.yahoo import HistoricalProviderError, YahooFinanceProvider
from app.schemas import SymbolCard, SymbolsResponse
from app.services.cache import Cache

logger = logging.getLogger(__name__)

_SOFT_TTL = 86_400
_FRESH_MARKER = "1"

SortField = Literal[
    "symbol",
    "name",
    "price",
    "change",
    "change_percent",
    "volatility",
]
SortOrder = Literal["asc", "desc"]

_ALL_CLASSES: tuple[AssetClassQuery, ...] = ("stocks", "crypto", "forex")
_QUERY_ASSET_CLASS = {
    "equity": "stocks",
    "crypto": "crypto",
    "forex": "forex",
}


class SymbolsService:
    """Fast category symbol list with background Yahoo price refresh."""

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
        asset_class: AssetClassQuery | None = None,
        *,
        sorted_by: SortField | None = None,
        order: SortOrder | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> SymbolsResponse:
        """Return catalog cards with optional sort + pagination."""
        classes: tuple[AssetClassQuery, ...] = (
            (asset_class,) if asset_class is not None else _ALL_CLASSES
        )
        items: list[SymbolCard] = []
        for cls in classes:
            items.extend(await self._load_class(cls))

        resolved_order = order or _default_order(sorted_by)
        if sorted_by is not None:
            items = _sort_items(items, sorted_by, resolved_order)

        total = len(items)
        page = max(1, page)
        limit = max(1, min(limit, 500))
        start = (page - 1) * limit
        page_items = items[start : start + limit]

        return SymbolsResponse(
            asset_class=asset_class or "all",
            total=total,
            page=page,
            limit=limit,
            sorted_by=sorted_by,
            order=resolved_order if sorted_by else None,
            items=page_items,
        )

    async def _load_class(self, asset_class: AssetClassQuery) -> list[SymbolCard]:
        universe = symbols_universe(asset_class)
        key = f"symbols:{asset_class}:v2"
        soft = await self.cache.get_json(key)
        prices = _price_index(soft)

        fresh = await self.cache.get_json(f"{key}:fresh")
        if fresh is None:
            self._schedule_refresh(asset_class, key)

        latest = await self._latest_prices([entry.symbol for entry in universe])
        return [
            self._build_card(entry, prices.get(entry.symbol), latest.get(entry.symbol))
            for entry in universe
        ]

    def _schedule_refresh(self, asset_class: AssetClassQuery, key: str) -> None:
        task = asyncio.create_task(
            self._refresh(asset_class, key), name=f"symbols-refresh-{asset_class}"
        )
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    async def _refresh(self, asset_class: AssetClassQuery, key: str) -> None:
        async with self.cache.lock(key, lock_ttl=120, blocking_timeout=0.05) as acquired:
            if not acquired:
                return
            if await self.cache.get_json(f"{key}:fresh") is not None:
                return
            universe = symbols_universe(asset_class)
            quotes: dict[str, dict[str, Any]] = {}
            try:
                quotes = await self.yahoo.quotes(tuple(item.symbol for item in universe))
            except HistoricalProviderError:
                logger.warning("Symbols quotes unavailable for %s", asset_class)

            items = [
                {
                    "symbol": entry.symbol,
                    "name": entry.name,
                    "description": entry.description,
                    "asset_class": _QUERY_ASSET_CLASS[entry.asset_class],
                    "price": _float(quotes.get(entry.symbol, {}).get("c")),
                    "change": _float(quotes.get(entry.symbol, {}).get("d")),
                    "change_percent": _float(quotes.get(entry.symbol, {}).get("dp")),
                    "previous_close": _float(quotes.get(entry.symbol, {}).get("pc")),
                }
                for entry in universe
            ]
            payload = {"asset_class": asset_class, "count": len(items), "items": items}
            await self.cache.set_json(key, payload, _SOFT_TTL)
            if quotes:
                await self.cache.set_json(f"{key}:fresh", _FRESH_MARKER, self.ttl)

    def warm(self) -> None:
        """Kick off background price loads for all categories (startup)."""
        for asset_class in _ALL_CLASSES:
            self._schedule_refresh(asset_class, f"symbols:{asset_class}:v2")

    async def _latest_prices(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        values = await self.cache.mget_json([f"latest:{symbol}" for symbol in symbols])
        out: dict[str, dict[str, Any]] = {}
        for symbol, value in zip(symbols, values, strict=True):
            if isinstance(value, dict) and value.get("price") is not None:
                out[symbol] = value
        return out

    def _build_card(
        self,
        entry: CatalogEntry,
        cached: dict[str, Any] | None,
        live: dict[str, Any] | None,
    ) -> SymbolCard:
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
            elif live.get("change") is not None:
                change = _float(live.get("change"))
                change_percent = _float(live.get("change_percent"))

        return SymbolCard(
            symbol=entry.symbol,
            name=entry.name,
            description=entry.description,
            asset_class=_QUERY_ASSET_CLASS[entry.asset_class],  # type: ignore[arg-type]
            price=price,
            change=change,
            change_percent=change_percent,
        )


def _default_order(sorted_by: SortField | None) -> SortOrder:
    if sorted_by in {"price", "change", "change_percent", "volatility"}:
        return "desc"
    return "asc"


def _sort_key(item: SymbolCard, field: SortField) -> float | str | None:
    """Return sortable value, or None when missing (nulls sorted last)."""
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
    # volatility
    return abs(item.change_percent) if item.change_percent is not None else None


def _sort_items(
    items: list[SymbolCard], sorted_by: SortField, order: SortOrder
) -> list[SymbolCard]:
    reverse = order == "desc"
    keyed = [(_sort_key(item, sorted_by), item) for item in items]
    present = [(key, item) for key, item in keyed if key is not None]
    missing = [item for key, item in keyed if key is None]
    present.sort(key=lambda row: row[0], reverse=reverse)  # type: ignore[arg-type]
    return [item for _, item in present] + missing


def _price_index(soft: Any) -> dict[str, dict[str, Any]]:
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


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
