import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.symbols import CURATED_SYMBOLS, SymbolSpec
from app.providers.finnhub import FinnhubError
from app.schemas import SymbolOverview, SymbolsOverviewResponse
from app.services.cache import Cache
from app.services.market import MarketDataService

logger = logging.getLogger(__name__)


class OverviewService:
    def __init__(
        self,
        cache: Cache,
        market: MarketDataService,
        sessions: async_sessionmaker[AsyncSession],
        ttl: int = 30,
    ) -> None:
        self.cache = cache
        self.market = market
        self.sessions = sessions
        self.ttl = ttl

    async def list_symbols(self) -> SymbolsOverviewResponse:
        key = "overview:symbols"
        cached = await self.cache.get_json(key)
        if cached is not None:
            return SymbolsOverviewResponse.model_validate(cached)

        async with self.cache.lock(key):
            cached = await self.cache.get_json(key)
            if cached is not None:
                return SymbolsOverviewResponse.model_validate(cached)

            cards = await asyncio.gather(
                *(self._build_card(spec) for spec in CURATED_SYMBOLS),
                return_exceptions=True,
            )
            symbols: list[SymbolOverview] = []
            for card in cards:
                if isinstance(card, SymbolOverview):
                    symbols.append(card)
                else:
                    logger.warning("Overview card failed: %s", card)

            response = SymbolsOverviewResponse(symbols=symbols)
            await self.cache.set_json(key, response.model_dump(mode="json"), self.ttl)
            return response

    async def _build_card(self, spec: SymbolSpec) -> SymbolOverview:
        profile: dict[str, Any] = {}
        quote: dict[str, Any] = {}
        try:
            profile_payload = await self.market.get(
                "company-profile", "/stock/profile2", {"symbol": spec.symbol}, 86400
            )
            if isinstance(profile_payload, dict):
                profile = profile_payload
        except FinnhubError:
            logger.debug("Profile unavailable for %s", spec.symbol)

        try:
            quote_payload = await self.market.get(
                "quote", "/quote", {"symbol": spec.symbol}, 15
            )
            if isinstance(quote_payload, dict):
                quote = quote_payload
        except FinnhubError:
            logger.debug("Quote unavailable for %s", spec.symbol)

        latest = await self.cache.get_json(f"latest:{spec.symbol}")
        price = _float(quote.get("c"))
        previous_close = _float(quote.get("pc"))
        change = _float(quote.get("d"))
        change_percent = _float(quote.get("dp"))
        timestamp: datetime | None = None
        if isinstance(latest, dict) and latest.get("price") is not None:
            price = float(latest["price"])
            if previous_close and previous_close > 0:
                change = price - previous_close
                change_percent = (change / previous_close) * 100
            if latest.get("timestamp"):
                timestamp = datetime.fromisoformat(str(latest["timestamp"]).replace("Z", "+00:00"))
        elif quote.get("t"):
            timestamp = datetime.fromtimestamp(float(quote["t"]), tz=UTC)

        return SymbolOverview(
            symbol=spec.symbol,
            name=str(profile.get("name") or spec.name),
            asset_class=spec.asset_class,
            exchange=str(profile.get("exchange")) if profile.get("exchange") else None,
            currency=str(profile.get("currency")) if profile.get("currency") else None,
            country=str(profile.get("country")) if profile.get("country") else None,
            industry=(
                str(profile.get("finnhubIndustry") or profile.get("industry") or "") or None
            ),
            logo=str(profile.get("logo")) if profile.get("logo") else None,
            weburl=str(profile.get("weburl")) if profile.get("weburl") else None,
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
