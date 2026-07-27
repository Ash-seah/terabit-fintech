import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.symbols import yfinance_symbol_for
from app.db.repositories import get_historical_bars, upsert_historical_bars
from app.providers.yahoo import YahooFinanceProvider
from app.schemas import HistoricalResponse, TradingViewBar, TradingViewHistoryResponse
from app.services.cache import Cache

logger = logging.getLogger(__name__)

PERIODS: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "5d": timedelta(days=5),
    "1mo": timedelta(days=31),
    "3mo": timedelta(days=93),
    "6mo": timedelta(days=186),
    "1y": timedelta(days=366),
    "2y": timedelta(days=732),
    "5y": timedelta(days=1830),
    "10y": timedelta(days=3660),
    "ytd": timedelta(days=366),
    "max": timedelta(days=36500),
}

# Prefer the deepest history Yahoo allows for each resolution.
DEFAULT_PERIOD_FOR_INTERVAL: dict[str, str] = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "60d",
    "1h": "730d",
    "1d": "max",
    "5d": "max",
    "1wk": "max",
    "1mo": "max",
    "3mo": "max",
}

# Map short Yahoo periods used above that are not in PERIODS keys for DB window.
PERIOD_ALIASES: dict[str, str] = {
    "7d": "5d",
    "60d": "3mo",
    "730d": "2y",
}


class HistoricalService:
    def __init__(
        self,
        cache: Cache,
        sessions: async_sessionmaker[AsyncSession],
        provider: YahooFinanceProvider,
        ttl: int,
    ) -> None:
        self.cache = cache
        self.sessions = sessions
        self.provider = provider
        self.ttl = ttl

    async def get(
        self,
        symbol: str,
        period: str | None = None,
        interval: str = "1d",
    ) -> HistoricalResponse:
        resolved_period = period or DEFAULT_PERIOD_FOR_INTERVAL.get(interval, "max")
        yahoo_period = resolved_period
        db_period = PERIOD_ALIASES.get(resolved_period, resolved_period)
        if db_period not in PERIODS:
            db_period = "max"

        key = f"chart:{symbol}:{yahoo_period}:{interval}"
        cached = await self.cache.get_json(key)
        if cached is not None:
            cached["cached"] = True
            cached.pop("source", None)
            return HistoricalResponse.model_validate(cached)

        async with self.cache.lock(key):
            cached = await self.cache.get_json(key)
            if cached is not None:
                cached["cached"] = True
                cached.pop("source", None)
                return HistoricalResponse.model_validate(cached)

            since = datetime.now(UTC) - PERIODS[db_period]
            try:
                async with self.sessions() as session:
                    points = await get_historical_bars(session, symbol, interval, since)
                if (
                    points
                    and self._database_is_fresh(points[-1].timestamp, interval)
                    and self._database_covers_period(points[0].timestamp, since, db_period)
                ):
                    response = HistoricalResponse(
                        symbol=symbol,
                        interval=interval,
                        period=yahoo_period,
                        points=points,
                    )
                    await self.cache.set_json(
                        key, response.model_dump(mode="json"), self.ttl
                    )
                    return response
            except SQLAlchemyError:
                logger.exception("Historical database read failed; falling back to provider")

            yahoo_symbol = yfinance_symbol_for(symbol)
            points = await self.provider.history(yahoo_symbol, yahoo_period, interval)
            response = HistoricalResponse(
                symbol=symbol,
                interval=interval,
                period=yahoo_period,
                points=points,
            )
            try:
                async with self.sessions() as session:
                    await upsert_historical_bars(session, symbol, interval, points)
            except SQLAlchemyError:
                logger.exception("Historical database write failed")
            await self.cache.set_json(key, response.model_dump(mode="json"), self.ttl)
            return response

    async def tradingview(
        self,
        symbol: str,
        interval: str = "1d",
        period: str | None = None,
    ) -> TradingViewHistoryResponse:
        history = await self.get(symbol, period=period, interval=interval)
        bars = [
            TradingViewBar(
                time=int(point.timestamp.astimezone(UTC).timestamp()),
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=float(point.volume),
            )
            for point in history.points
        ]
        return TradingViewHistoryResponse(
            symbol=symbol,
            interval=interval,
            cached=history.cached,
            bars=bars,
        )

    @staticmethod
    def _database_is_fresh(latest: datetime, interval: str) -> bool:
        threshold = (
            timedelta(days=4)
            if interval in {"1d", "5d", "1wk", "1mo", "3mo"}
            else timedelta(hours=2)
        )
        return latest >= datetime.now(UTC) - threshold

    @staticmethod
    def _database_covers_period(earliest: datetime, since: datetime, period: str) -> bool:
        # For max history, accept whatever the DB already has and still refresh when stale.
        if period == "max":
            return True
        tolerance = min(PERIODS[period] / 10, timedelta(days=7))
        return earliest <= since + tolerance
