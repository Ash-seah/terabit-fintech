import asyncio
import math
from datetime import UTC

import yfinance as yf  # type: ignore[import-untyped]
from yfinance.exceptions import YFPricesMissingError  # type: ignore[import-untyped]

from app.schemas import HistoricalPoint


class HistoricalDataNotFoundError(Exception):
    pass


class HistoricalProviderError(Exception):
    pass


class YahooFinanceProvider:
    async def history(self, symbol: str, period: str, interval: str) -> list[HistoricalPoint]:
        return await asyncio.to_thread(self._history_sync, symbol, period, interval)

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
