"""Background chart warm-up so cold FX/equity requests hit DB/Redis."""

from __future__ import annotations

import asyncio
import logging

from app.core.symbols import CURATED_SYMBOLS, FOREX_CATALOG
from app.services.historical import HistoricalService

logger = logging.getLogger(__name__)

# High-traffic chart shapes first (matches frontend forex/stock viewers).
_PREFETCH_SHAPES: tuple[tuple[str, str], ...] = (
    ("1h", "5d"),
    ("1h", "1mo"),
    ("1d", "1y"),
    ("1d", "5d"),
    ("15m", "5d"),
)


def _prefetch_symbols() -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for symbol, _ in FOREX_CATALOG:
        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    for spec in CURATED_SYMBOLS:
        if spec.symbol not in seen:
            seen.add(spec.symbol)
            symbols.append(spec.symbol)
    return symbols


async def chart_prefetch_worker(
    historical: HistoricalService,
    *,
    cycle_seconds: float = 900.0,
    concurrency: int = 2,
) -> None:
    """Continuously warm popular chart keys into Postgres + Redis."""
    symbols = _prefetch_symbols()
    semaphore = asyncio.Semaphore(concurrency)
    logger.info(
        "Chart prefetch worker started (%d symbols × %d shapes)",
        len(symbols),
        len(_PREFETCH_SHAPES),
    )

    async def _one(symbol: str, interval: str, period: str) -> None:
        async with semaphore:
            try:
                await historical.prefetch(symbol, period, interval)
            except Exception:
                logger.exception("Prefetch failed for %s %s/%s", symbol, period, interval)
            await asyncio.sleep(0.35)

    while True:
        jobs = [
            _one(symbol, interval, period)
            for symbol in symbols
            for interval, period in _PREFETCH_SHAPES
        ]
        # Chunk to avoid creating thousands of tasks at once.
        chunk_size = 40
        for offset in range(0, len(jobs), chunk_size):
            await asyncio.gather(*jobs[offset : offset + chunk_size])
        logger.info("Chart prefetch cycle complete; sleeping %.0fs", cycle_seconds)
        await asyncio.sleep(cycle_seconds)
