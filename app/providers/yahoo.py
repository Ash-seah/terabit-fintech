import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import yfinance as yf  # type: ignore[import-untyped]
from yfinance.exceptions import YFPricesMissingError  # type: ignore[import-untyped]

from app.core.symbols import yfinance_symbol_for
from app.schemas import HistoricalPoint


class HistoricalDataNotFoundError(Exception):
    pass


class HistoricalProviderError(Exception):
    pass


class YahooFinanceProvider:
    async def history(self, symbol: str, period: str, interval: str) -> list[HistoricalPoint]:
        return await asyncio.to_thread(self._history_sync, symbol, period, interval)

    async def quote(self, symbol: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._quote_sync, symbol)

    async def quotes(self, symbols: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        chunk_size = 25
        chunks = [
            symbols[offset : offset + chunk_size]
            for offset in range(0, len(symbols), chunk_size)
        ]
        semaphore = asyncio.Semaphore(2)

        async def _one(chunk: tuple[str, ...]) -> dict[str, dict[str, Any]]:
            async with semaphore:
                return await asyncio.to_thread(self._quotes_chunk_sync, chunk)

        parts = await asyncio.gather(*[_one(chunk) for chunk in chunks])
        merged: dict[str, dict[str, Any]] = {}
        for part in parts:
            merged.update(part)
        return merged

    @staticmethod
    def _history_sync(symbol: str, period: str, interval: str) -> list[HistoricalPoint]:
        try:
            frame = yf.Ticker(symbol).history(
                period=period,
                interval=interval,
                auto_adjust=False,
                actions=False,
                raise_errors=True,
            )
        except YFPricesMissingError as exc:
            raise HistoricalDataNotFoundError(f"No historical data found for {symbol}") from exc
        except Exception as exc:
            raise HistoricalProviderError(f"Historical provider failed for {symbol}") from exc
        if frame.empty:
            raise HistoricalDataNotFoundError(f"No historical data found for {symbol}")

        points: list[HistoricalPoint] = []
        for timestamp, row in frame.iterrows():
            values = [row["Open"], row["High"], row["Low"], row["Close"]]
            if any(math.isnan(float(value)) for value in values):
                continue
            dt = timestamp.to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            volume = float(row.get("Volume", 0) or 0)
            points.append(
                HistoricalPoint(
                    timestamp=dt,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=0 if math.isnan(volume) else int(volume),
                )
            )
        if not points:
            raise HistoricalDataNotFoundError(f"No usable historical data found for {symbol}")
        return points

    @classmethod
    def _quote_sync(cls, symbol: str) -> dict[str, Any]:
        quotes = cls._quotes_sync((symbol,))
        if symbol not in quotes:
            raise HistoricalProviderError(f"Quote unavailable for {symbol}")
        return quotes[symbol]

    @classmethod
    def _quotes_sync(cls, symbols: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        """Batch-fetch last/previous close via chunked Yahoo downloads."""
        if not symbols:
            return {}
        results: dict[str, dict[str, Any]] = {}
        chunk_size = 25
        for offset in range(0, len(symbols), chunk_size):
            results.update(cls._quotes_chunk_sync(symbols[offset : offset + chunk_size]))
        return results

    @staticmethod
    def _quotes_chunk_sync(symbols: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        yahoo_to_api = {yfinance_symbol_for(symbol): symbol for symbol in symbols}
        yahoo_symbols = list(dict.fromkeys(yahoo_to_api.keys()))
        try:
            frame = yf.download(
                tickers=yahoo_symbols,
                period="2d",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
        except Exception:
            # Chunk failures should not kill the whole universe fetch.
            return {}

        if frame is None or getattr(frame, "empty", False):
            return {}

        results: dict[str, dict[str, Any]] = {}
        now_ts = int(datetime.now(UTC).timestamp())
        for yahoo_symbol, api_symbol in yahoo_to_api.items():
            try:
                if len(yahoo_symbols) == 1:
                    series = frame
                else:
                    levels = frame.columns.get_level_values(0)
                    if yahoo_symbol not in levels:
                        continue
                    series = frame[yahoo_symbol]
                closes = series["Close"].dropna()
                if closes.empty:
                    continue
                last = float(closes.iloc[-1])
                previous = float(closes.iloc[-2]) if len(closes) > 1 else last
                change = last - previous
                change_percent = (change / previous) * 100 if previous else 0.0
                opens = series["Open"].dropna()
                highs = series["High"].dropna()
                lows = series["Low"].dropna()
                results[api_symbol] = {
                    "c": last,
                    "pc": previous,
                    "d": change,
                    "dp": change_percent,
                    "o": float(opens.iloc[-1]) if not opens.empty else last,
                    "h": float(highs.iloc[-1]) if not highs.empty else last,
                    "l": float(lows.iloc[-1]) if not lows.empty else last,
                    "t": now_ts,
                }
            except Exception:
                continue
        return results
