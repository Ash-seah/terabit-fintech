import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.symbols import yfinance_symbol_for
from app.db.repositories import (
    get_historical_bars,
    get_recent_historical_bars,
    upsert_historical_bars,
)
from app.providers.yahoo import (
    HistoricalDataNotFoundError,
    HistoricalProviderError,
    YahooFinanceProvider,
)
from app.schemas import HistoricalPoint, HistoricalResponse, TradingViewBar, TradingViewHistoryResponse
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

_INTRADAY = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
_FRESH_MARKER = "1"
# Hard client SLA: always answer inside this window.
_REQUEST_BUDGET_SECONDS = 1.8
_QUICK_PROVIDER_TIMEOUT = 1.2


class HistoricalService:
    """Charts with a hard ~2s request budget. Full history fills in the background."""

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
        self._soft_ttl = max(ttl * 48, 172_800)
        self._refresh_tasks: set[asyncio.Task[None]] = set()

    async def get(
        self,
        symbol: str,
        period: str | None = None,
        interval: str = "1d",
    ) -> HistoricalResponse:
        started = time.monotonic()
        resolved_period = period or DEFAULT_PERIOD_FOR_INTERVAL.get(interval, "max")
        yahoo_period = resolved_period
        db_period = PERIOD_ALIASES.get(resolved_period, resolved_period)
        if db_period not in PERIODS:
            db_period = "max"
        key = f"chart:{symbol}:{yahoo_period}:{interval}"

        soft = await self.cache.get_json(key)
        if soft is not None:
            if await self.cache.get_json(f"{key}:fresh") is None:
                self.enqueue_full_refresh(symbol, yahoo_period, interval, db_period, key)
            return self._as_response(soft, cached=True)

        # Fast path: any DB bars we already own.
        db_fast = await self._read_db_any(symbol, interval, yahoo_period)
        if db_fast is not None and db_fast.points:
            await self._store_cache(key, db_fast, mark_fresh=False)
            self.enqueue_full_refresh(symbol, yahoo_period, interval, db_period, key)
            partial = not self._looks_complete(db_fast.points, db_period, interval)
            return db_fast.model_copy(update={"cached": True, "partial": partial})

        remaining = _REQUEST_BUDGET_SECONDS - (time.monotonic() - started)
        quick_period = _quick_period(yahoo_period, interval)
        if remaining > 0.25:
            painted = await self._quick_paint(
                symbol,
                yahoo_period=yahoo_period,
                quick_period=quick_period,
                interval=interval,
                db_period=db_period,
                key=key,
                timeout=min(_QUICK_PROVIDER_TIMEOUT, remaining),
            )
            if painted is not None:
                return painted

        # Guaranteed response: empty shell while background job loads data.
        self.enqueue_full_refresh(symbol, yahoo_period, interval, db_period, key)
        return HistoricalResponse(
            symbol=symbol,
            interval=interval,
            period=yahoo_period,
            cached=False,
            partial=True,
            loading=True,
            points=[],
        )

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
            partial=history.partial,
            loading=history.loading,
            bars=bars,
        )

    def enqueue_full_refresh(
        self,
        symbol: str,
        yahoo_period: str,
        interval: str,
        db_period: str,
        key: str | None = None,
    ) -> None:
        cache_key = key or f"chart:{symbol}:{yahoo_period}:{interval}"
        task = asyncio.create_task(
            self._refresh(symbol, yahoo_period, interval, db_period, cache_key),
            name=f"chart-refresh:{cache_key}",
        )
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    async def prefetch(
        self,
        symbol: str,
        period: str,
        interval: str,
    ) -> None:
        """Background warm for a symbol/period/interval combo."""
        db_period = PERIOD_ALIASES.get(period, period)
        if db_period not in PERIODS:
            db_period = "max"
        key = f"chart:{symbol}:{period}:{interval}"
        if await self.cache.get_json(f"{key}:fresh") is not None:
            return
        await self._refresh(symbol, period, interval, db_period, key)

    async def _quick_paint(
        self,
        symbol: str,
        *,
        yahoo_period: str,
        quick_period: str,
        interval: str,
        db_period: str,
        key: str,
        timeout: float,
    ) -> HistoricalResponse | None:
        """Try a shallow provider pull inside the remaining budget."""
        async with self.cache.lock(key, lock_ttl=90, blocking_timeout=0.01) as acquired:
            soft = await self.cache.get_json(key)
            if soft is not None:
                return self._as_response(soft, cached=True)
            if not acquired:
                waited = await self._wait_for_cache(key, min(0.6, timeout))
                if waited is not None:
                    return self._as_response(waited, cached=True)
                return None
            try:
                points = await asyncio.wait_for(
                    self.provider.history(
                        yfinance_symbol_for(symbol), quick_period, interval
                    ),
                    timeout=timeout,
                )
            except (TimeoutError, HistoricalProviderError, HistoricalDataNotFoundError):
                logger.info("Quick chart paint missed for %s %s/%s", symbol, quick_period, interval)
                self.enqueue_full_refresh(symbol, yahoo_period, interval, db_period, key)
                return None
            except Exception:
                logger.exception("Quick chart paint failed for %s", symbol)
                self.enqueue_full_refresh(symbol, yahoo_period, interval, db_period, key)
                return None

            partial = quick_period != yahoo_period
            response = HistoricalResponse(
                symbol=symbol,
                interval=interval,
                period=yahoo_period,
                cached=False,
                partial=partial,
                loading=False,
                points=points,
            )
            try:
                async with self.sessions() as session:
                    await upsert_historical_bars(session, symbol, interval, points)
            except Exception:
                logger.exception("Historical database write failed")
            # Mark fresh only when we already satisfied the requested depth.
            await self._store_cache(key, response, mark_fresh=not partial)
            if partial:
                self.enqueue_full_refresh(symbol, yahoo_period, interval, db_period, key)
            return response

    async def _refresh(
        self,
        symbol: str,
        yahoo_period: str,
        interval: str,
        db_period: str,
        key: str,
    ) -> None:
        async with self.cache.lock(key, lock_ttl=180, blocking_timeout=0.05) as acquired:
            if not acquired:
                return
            if await self.cache.get_json(f"{key}:fresh") is not None:
                return
            try:
                await self._fetch_and_store(symbol, yahoo_period, interval, key)
            except Exception:
                logger.exception("Background chart refresh failed for %s", symbol)

    async def _fetch_and_store(
        self,
        symbol: str,
        yahoo_period: str,
        interval: str,
        key: str,
    ) -> HistoricalResponse:
        yahoo_symbol = yfinance_symbol_for(symbol)
        points = await asyncio.wait_for(
            self.provider.history(yahoo_symbol, yahoo_period, interval),
            timeout=45.0,
        )
        response = HistoricalResponse(
            symbol=symbol,
            interval=interval,
            period=yahoo_period,
            points=points,
            partial=False,
            loading=False,
        )
        try:
            async with self.sessions() as session:
                await upsert_historical_bars(session, symbol, interval, points)
        except Exception:
            logger.exception("Historical database write failed")
        await self._store_cache(key, response, mark_fresh=True)
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
            await asyncio.sleep(0.1)
        return None

    async def _read_db_any(
        self,
        symbol: str,
        interval: str,
        yahoo_period: str,
    ) -> HistoricalResponse | None:
        try:
            async with self.sessions() as session:
                points = await get_recent_historical_bars(session, symbol, interval)
        except SQLAlchemyError:
            logger.exception("Historical database read failed")
            return None
        if not points:
            return None
        return HistoricalResponse(
            symbol=symbol,
            interval=interval,
            period=yahoo_period,
            cached=True,
            points=points,
        )

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
        return HistoricalResponse(
            symbol=symbol,
            interval=interval,
            period=db_period if db_period in PERIODS else "max",
            cached=True,
            points=points,
        )

    @staticmethod
    def _as_response(payload: dict, *, cached: bool) -> HistoricalResponse:
        data = dict(payload)
        data["cached"] = cached
        data.setdefault("partial", False)
        data.setdefault("loading", False)
        data.pop("source", None)
        return HistoricalResponse.model_validate(data)

    @staticmethod
    def _looks_complete(points: list[HistoricalPoint], db_period: str, interval: str) -> bool:
        if not points:
            return False
        since = datetime.now(UTC) - PERIODS.get(db_period, timedelta(days=30))
        if not HistoricalService._database_covers_period(points[0].timestamp, since, db_period):
            return False
        return HistoricalService._database_is_fresh(points[-1].timestamp, interval)

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


def _quick_period(requested: str, interval: str) -> str:
    """Shallow window for first paint inside the 2s budget."""
    if interval in _INTRADAY:
        if requested in {"1d", "5d"}:
            return requested
        return "5d"
    if requested in {"1d", "5d", "1mo", "3mo"}:
        return requested
    return "1mo"
