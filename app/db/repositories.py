from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HistoricalBar, MinuteBar, ProviderSnapshot, RealtimeTrade
from app.schemas import HistoricalPoint, Trade


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


async def upsert_historical_bars(
    session: AsyncSession,
    symbol: str,
    interval: str,
    points: list[HistoricalPoint],
) -> None:
    if not points:
        return
    values = [
        {
            "symbol": symbol,
            "interval": interval,
            "timestamp": point.timestamp,
            "open": _decimal(point.open),
            "high": _decimal(point.high),
            "low": _decimal(point.low),
            "close": _decimal(point.close),
            "volume": point.volume,
            "source": "yfinance",
        }
        for point in points
    ]
    statement = insert(HistoricalBar).values(values)
    statement = statement.on_conflict_do_update(
        constraint="uq_historical_bar",
        set_={
            "open": statement.excluded.open,
            "high": statement.excluded.high,
            "low": statement.excluded.low,
            "close": statement.excluded.close,
            "volume": statement.excluded.volume,
            "updated_at": datetime.now(UTC),
        },
    )
    await session.execute(statement)
    await session.commit()


async def get_historical_bars(
    session: AsyncSession,
    symbol: str,
    interval: str,
    since: datetime,
) -> list[HistoricalPoint]:
    result = await session.scalars(
        select(HistoricalBar)
        .where(
            HistoricalBar.symbol == symbol,
            HistoricalBar.interval == interval,
            HistoricalBar.timestamp >= since,
        )
        .order_by(HistoricalBar.timestamp)
    )
    return [
        HistoricalPoint(
            timestamp=bar.timestamp,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=bar.volume,
        )
        for bar in result
    ]


async def upsert_snapshot(
    session: AsyncSession,
    resource_key: str,
    payload: dict[str, Any] | list[Any],
    expires_at: datetime | None,
) -> None:
    statement = insert(ProviderSnapshot).values(
        provider="finnhub",
        resource_key=resource_key,
        payload=payload,
        expires_at=expires_at,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_provider_resource",
        set_={
            "payload": statement.excluded.payload,
            "expires_at": statement.excluded.expires_at,
            "updated_at": datetime.now(UTC),
        },
    )
    await session.execute(statement)
    await session.commit()


async def get_snapshot(
    session: AsyncSession, resource_key: str, *, allow_expired: bool = False
) -> tuple[dict[str, Any] | list[Any], bool] | None:
    snapshot = await session.scalar(
        select(ProviderSnapshot).where(
            ProviderSnapshot.provider == "finnhub",
            ProviderSnapshot.resource_key == resource_key,
        )
    )
    if snapshot is None:
        return None
    stale = snapshot.expires_at is not None and snapshot.expires_at < datetime.now(UTC)
    if stale and not allow_expired:
        return None
    return snapshot.payload, stale


async def persist_trades_and_minutes(session: AsyncSession, trades: list[Trade]) -> None:
    if not trades:
        return
    await session.execute(
        insert(RealtimeTrade),
        [
            {
                "symbol": trade.symbol,
                "timestamp": trade.timestamp,
                "price": _decimal(trade.price),
                "volume": _decimal(trade.volume),
                "conditions": trade.conditions,
            }
            for trade in trades
        ],
    )

    grouped: dict[tuple[str, datetime], list[Trade]] = defaultdict(list)
    for trade in trades:
        minute = trade.timestamp.astimezone(UTC).replace(second=0, microsecond=0)
        grouped[(trade.symbol, minute)].append(trade)
    for (symbol, minute), minute_trades in grouped.items():
        values = {
            "symbol": symbol,
            "timestamp": minute,
            "open": _decimal(minute_trades[0].price),
            "high": _decimal(max(item.price for item in minute_trades)),
            "low": _decimal(min(item.price for item in minute_trades)),
            "close": _decimal(minute_trades[-1].price),
            "volume": _decimal(sum(item.volume for item in minute_trades)),
            "trade_count": len(minute_trades),
        }
        statement = insert(MinuteBar).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_minute_bar",
            set_={
                "high": func.greatest(MinuteBar.high, statement.excluded.high),
                "low": func.least(MinuteBar.low, statement.excluded.low),
                "close": statement.excluded.close,
                "volume": MinuteBar.volume + statement.excluded.volume,
                "trade_count": MinuteBar.trade_count + statement.excluded.trade_count,
                "updated_at": datetime.now(UTC),
            },
        )
        await session.execute(statement)
    await session.commit()


async def delete_old_trades(session: AsyncSession, retention_days: int) -> int:
    result = await session.execute(
        delete(RealtimeTrade).where(
            RealtimeTrade.timestamp < datetime.now(UTC) - timedelta(days=retention_days)
        )
    )
    await session.commit()
    return int(result.rowcount or 0)
