import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import get_historical_bars, upsert_historical_bars
from app.providers.yahoo import YahooFinanceProvider
from app.schemas import HistoricalResponse
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
INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}


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

    async def get(self, symbol: str, period: str, interval: str) -> HistoricalResponse:
        key = f"chart:{symbol}:{period}:{interval}"
        cached = await self.cache.get_json(key)
        if cached is not None:
            cached["cached"] = True
            return HistoricalResponse.model_validate(cached)

        async with self.cache.lock(key):
            cached = await self.cache.get_json(key)
            if cached is not None:
                cached["cached"] = True
                return HistoricalResponse.model_validate(cached)

            since = datetime.now(UTC) - PERIODS[period]
            try:
                async with self.sessions() as session:
                    points = await get_historical_bars(session, symbol, interval, since)
                if (
                    points
                    and self._database_is_fresh(points[-1].timestamp, interval)
                    and self._database_covers_period(points[0].timestamp, since, period)
                ):
                    response = HistoricalResponse(
                        symbol=symbol,
                        interval=interval,
                        period=period,
                        source="database",
                        points=points,
                    )
                    await self.cache.set_json(key, response.model_dump(mode="json"), self.ttl)
                    return response
            except SQLAlchemyError:
                logger.exception("Historical database read failed; falling back to provider")

            points = await self.provider.history(symbol, period, interval)
            response = HistoricalResponse(
                symbol=symbol,
                interval=interval,
                period=period,
                source="yfinance",
                points=points,
            )
            try:
                async with self.sessions() as session:
                    await upsert_historical_bars(session, symbol, interval, points)
            except SQLAlchemyError:
                logger.exception("Historical database write failed")
            await self.cache.set_json(key, response.model_dump(mode="json"), self.ttl)
            return response

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
        tolerance = min(PERIODS[period] / 10, timedelta(days=7))
        return earliest <= since + tolerance
