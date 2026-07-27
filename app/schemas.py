from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HistoricalPoint(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class HistoricalResponse(BaseModel):
    symbol: str
    interval: str
    period: str
    cached: bool = False
    points: list[HistoricalPoint]


class TradingViewBar(BaseModel):
    """TradingView Lightweight Charts candlestick bar."""

    time: int = Field(description="Unix timestamp in seconds (UTC)")
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class TradingViewHistoryResponse(BaseModel):
    symbol: str
    interval: str
    cached: bool = False
    bars: list[TradingViewBar]


class SymbolOverview(BaseModel):
    symbol: str
    name: str
    asset_class: str
    exchange: str | None = None
    currency: str | None = None
    country: str | None = None
    industry: str | None = None
    logo: str | None = None
    weburl: str | None = None
    price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    timestamp: datetime | None = None


class SymbolsOverviewResponse(BaseModel):
    symbols: list[SymbolOverview]


class Trade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    price: float = Field(gt=0)
    volume: float = Field(ge=0)
    timestamp: datetime
    conditions: list[str] = Field(default_factory=list)


class TradeEvent(BaseModel):
    type: Literal["trade"] = "trade"
    data: list[Trade]


class HeartbeatEvent(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: datetime


class ErrorResponse(BaseModel):
    detail: str
    code: str


# Passthrough market payloads are returned unwrapped (dict or list).
MarketPayload = dict[str, Any] | list[Any]
