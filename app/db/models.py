from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class HistoricalBar(Base, TimestampMixin):
    __tablename__ = "historical_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "timestamp", name="uq_historical_bar"),
        Index("ix_historical_symbol_interval_time", "symbol", "interval", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    interval: Mapped[str] = mapped_column(String(16), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="yfinance")


class RealtimeTrade(Base):
    __tablename__ = "realtime_trades"
    __table_args__ = (Index("ix_trade_symbol_time", "symbol", "timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    conditions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class MinuteBar(Base, TimestampMixin):
    __tablename__ = "minute_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uq_minute_bar"),
        Index("ix_minute_symbol_time", "symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProviderSnapshot(Base, TimestampMixin):
    __tablename__ = "provider_snapshots"
    __table_args__ = (UniqueConstraint("provider", "resource_key", name="uq_provider_resource"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_key: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
