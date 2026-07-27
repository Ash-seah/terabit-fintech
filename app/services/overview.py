import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.symbols import CURATED_SYMBOLS, SymbolSpec
from app.providers.yahoo import HistoricalProviderError, YahooFinanceProvider
from app.schemas import SymbolOverview, SymbolsOverviewResponse
from app.services.cache import Cache

logger = logging.getLogger(__name__)


class OverviewService:
    """Overview prefers Yahoo + WebSocket latest prices; avoids Finnhub on the hot path."""

    def __init__(
        self,
        cache: Cache,
        yahoo: YahooFinanceProvider,
        sessions: async_sessionmaker[AsyncSession],
        ttl: int = 180,
    ) -> None:
        self.cache = cache
        self.yahoo = yahoo
        self.sessions = sessions
        self.ttl = ttl

    async def list_symbols(self) -> SymbolsOverviewResponse:
        key = "overview:symbols:v3"
        cached = await self.cache.get_json(key)
        if cached is not None:
            # Overlay fresh WS prices without another upstream call.
            return await self._with_live_prices(SymbolsOverviewResponse.model_validate(cached))

        async with self.cache.lock(key):
            cached = await self.cache.get_json(key)
            if cached is not None:
                return await self._with_live_prices(SymbolsOverviewResponse.model_validate(cached))

            quotes: dict[str, dict[str, Any]] = {}
            try:
                quotes = await self.yahoo.quotes(tuple(item.symbol for item in CURATED_SYMBOLS))
            except HistoricalProviderError:
                logger.warning("Overview quotes unavailable; using live cache only")

            symbols = [
                self._build_card(spec, quotes.get(spec.symbol, {})) for spec in CURATED_SYMBOLS
            ]
            response = SymbolsOverviewResponse(symbols=symbols)
            await self.cache.set_json(key, response.model_dump(mode="json"), self.ttl)
            return await self._with_live_prices(response)

    async def _with_live_prices(
        self, response: SymbolsOverviewResponse
    ) -> SymbolsOverviewResponse:
        updated: list[SymbolOverview] = []
        for card in response.symbols:
            latest = await self.cache.get_json(f"latest:{card.symbol}")
            if not isinstance(latest, dict) or latest.get("price") is None:
                updated.append(card)
                continue
            price = float(latest["price"])
            previous = card.previous_close
            change = price - previous if previous else card.change
            change_percent = (
                ((price - previous) / previous) * 100 if previous else card.change_percent
            )
            timestamp = card.timestamp
            if latest.get("timestamp"):
                timestamp = datetime.fromisoformat(str(latest["timestamp"]).replace("Z", "+00:00"))
            updated.append(
                card.model_copy(
                    update={
                        "price": price,
                        "change": change,
                        "change_percent": change_percent,
                        "timestamp": timestamp,
                    }
                )
            )
        return SymbolsOverviewResponse(symbols=updated)

    def _build_card(self, spec: SymbolSpec, quote: dict[str, Any]) -> SymbolOverview:
        price = _float(quote.get("c"))
        previous_close = _float(quote.get("pc"))
        change = _float(quote.get("d"))
        change_percent = _float(quote.get("dp"))
        timestamp: datetime | None = None
        if quote.get("t"):
            timestamp = datetime.fromtimestamp(float(quote["t"]), tz=UTC)
        return SymbolOverview(
            symbol=spec.symbol,
            name=spec.name,
            asset_class=spec.asset_class,
            exchange=(
                "US"
                if spec.asset_class == "equity"
                else "CRYPTO"
                if spec.asset_class == "crypto"
                else "FX"
            ),
            currency="USD",
            country="US" if spec.asset_class == "equity" else None,
            industry=None,
            logo=None,
            weburl=None,
            price=price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            high=_float(quote.get("h")),
            low=_float(quote.get("l")),
            open=_float(quote.get("o")),
            timestamp=timestamp,
        )


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
