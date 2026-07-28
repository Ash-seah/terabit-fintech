import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.symbols import yfinance_symbol_for
from app.db.repositories import get_historical_bars, upsert_historical_bars
from app.providers.yahoo import (
    HistoricalDataNotFoundError,
    HistoricalProviderError,
    YahooFinanceProvider,
)
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

# Prefer useful depth without multi-minute cold Yahoo pulls for intraday.
DEFAULT_PERIOD_FOR_INTERVAL: dict[str, str] = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "60d",
    "90m": "60d",
    "1h": "60d",
    "1d": "max",
    "5d": "max",
    "1wk": "max",
    "1mo": "max",
    "3mo": "max",
}

PERIOD_ALIASES: dict[str, str] = {
    "7d": "5d",
    "60d": "3mo",
    "730d": "2y",
}

_FRESH_MARKER = "1"
_YAHOO_TIMEOUT_SECONDS = 20.0
_PEER_WAIT_SECONDS = 25.0


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
        self._soft_ttl = max(ttl * 24, 86_400)
        self._refresh_tasks: set[asyncio.Task[None]] = set()

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
        soft = await self.cache.get_json(key)
        if soft is not None:
            if await self.cache.get_json(f"{key}:fresh") is None:
                self._schedule_refresh(symbol, yahoo_period, interval, db_period, key)
            return self._as_cached(soft)

        return await self._load_cold(symbol, yahoo_period, interval, db_period, key)

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

    def _schedule_refresh(
        self,
        symbol: str,
        yahoo_period: str,
        interval: str,
        db_period: str,
        key: str,
    ) -> None:
        task = asyncio.create_task(
            self._refresh(symbol, yahoo_period, interval, db_period, key),
            name=f"chart-refresh:{key}",
        )
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    async def _refresh(
        self,
        symbol: str,
        yahoo_period: str,
        interval: str,
        db_period: str,
        key: str,
    ) -> None:
        async with self.cache.lock(key, lock_ttl=120, blocking_timeout=0.05) as acquired:
            if not acquired:
                return
            if await self.cache.get_json(f"{key}:fresh") is not None:
                return
            try:
                await self._fetch_and_store(symbol, yahoo_period, interval, db_period, key)
            except Exception:
                logger.exception("Background chart refresh failed for %s", symbol)

    async def _load_cold(
        self,
        symbol: str,
        yahoo_period: str,
        interval: str,
        db_period: str,
        key: str,
    ) -> HistoricalResponse:
        async with self.cache.lock(key, lock_ttl=120, blocking_timeout=0.05) as acquired:
            soft = await self.cache.get_json(key)
            if soft is not None:
                return self._as_cached(soft)

            if not acquired:
                waited = await self._wait_for_cache(key, _PEER_WAIT_SECONDS)
                if waited is not None:
                    return self._as_cached(waited)
                # Peer may have failed — try DB stale before erroring.
                stale = await self._read_db(symbol, interval, db_period, require_fresh=False)
                if stale is not None:
                    self._schedule_refresh(symbol, yahoo_period, interval, db_period, key)
                    return stale
                raise HistoricalProviderError(
                    "Chart data is still loading for this symbol; retry in a moment"
                )

            # Single-flight Yahoo/DB load under the lock.
            soft = await self.cache.get_json(key)
            if soft is not None:
                return self._as_cached(soft)

            fresh_db = await self._read_db(symbol, interval, db_period, require_fresh=True)
            if fresh_db is not None:
                await self._store_cache(key, fresh_db)
                return fresh_db

            try:
                return await self._fetch_and_store(
                    symbol, yahoo_period, interval, db_period, key
                )
            except (TimeoutError, HistoricalProviderError, HistoricalDataNotFoundError):
                stale = await self._read_db(symbol, interval, db_period, require_fresh=False)
                if stale is not None:
                    # Serve whatever we have; keep trying in background.
                    await self._store_cache(key, stale, mark_fresh=False)
                    self._schedule_refresh(symbol, yahoo_period, interval, db_period, key)
                    return stale
                raise

    async def _fetch_and_store(
        self,
        symbol: str,
        yahoo_period: str,
        interval: str,
        db_period: str,
        key: str,
    ) -> HistoricalResponse:
        yahoo_symbol = yfinance_symbol_for(symbol)
        try:
            points = await asyncio.wait_for(
                self.provider.history(yahoo_symbol, yahoo_period, interval),
                timeout=_YAHOO_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise HistoricalProviderError(
                f"Chart provider timed out for {symbol}"
            ) from exc

        response = HistoricalResponse(
            symbol=symbol,
            interval=interval,
            period=yahoo_period,
            points=points,
        )
        try:
            async with self.sessions() as session:
                await upsert_historical_bars(session, symbol, interval, points)
        except Exception:
            logger.exception("Historical database write failed")
        await self._store_cache(key, response)
        return response

    async def _store_cache(
        self,
        key: str,
        response: HistoricalResponse,
        *,
        mark_fresh: bool = True,
    ) -> None:
        payload = response.model_dump(mode="json")
        payload["cached"] = False
        await self.cache.set_json(key, payload, self._soft_ttl)
        if mark_fresh:
            await self.cache.set_json(f"{key}:fresh", _FRESH_MARKER, self.ttl)

    async def _wait_for_cache(self, key: str, timeout: float) -> dict | None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            soft = await self.cache.get_json(key)
            if soft is not None:
                return soft
            await asyncio.sleep(0.4)
        return None

    async def _read_db(
        self,
        symbol: str,
        interval: str,
        db_period: str,
        *,
        require_fresh: bool,
    ) -> HistoricalResponse | None:
        since = datetime.now(UTC) - PERIODS[db_period]
        try:
            async with self.sessions() as session:
                points = await get_historical_bars(session, symbol, interval, since)
        except SQLAlchemyError:
            logger.exception("Historical database read failed")
            return None
        if not points:
            return None
        if require_fresh and not self._database_is_fresh(points[-1].timestamp, interval):
            return None
        if require_fresh and not self._database_covers_period(
            points[0].timestamp, since, db_period
        ):
            return None
        if not require_fresh and not points:
            return None
        return HistoricalResponse(
            symbol=symbol,
            interval=interval,
            period=db_period if db_period in PERIODS else "max",
            cached=True,
            points=points,
        )

    @staticmethod
    def _as_cached(payload: dict) -> HistoricalResponse:
        payload = dict(payload)
        payload["cached"] = True
        payload.pop("source", None)
        return HistoricalResponse.model_validate(payload)

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
        if period == "max":
            return True
        tolerance = min(PERIODS[period] / 10, timedelta(days=7))
        return earliest <= since + tolerance
