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


class SymbolCard(BaseModel):
    """Category symbol card: name, description, price, change vs yesterday."""

    symbol: str
    name: str
    description: str
    asset_class: Literal["stocks", "crypto", "forex"]
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None


class SymbolsResponse(BaseModel):
    asset_class: Literal["stocks", "crypto", "forex", "all"]
    total: int
    page: int
    limit: int
    sorted_by: str | None = None
    order: Literal["asc", "desc"] | None = None
    items: list[SymbolCard]


class MarketMapItem(BaseModel):
    """Lean heatmap tile for US stocks."""

    symbol: str
    name: str
    description: str
    logo: str
    sector: str
    market_cap: float
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None


class MarketMapSector(BaseModel):
    sector: str
    count: int
    market_cap: float
    items: list[MarketMapItem]


class MarketMapResponse(BaseModel):
    count: int
    sorted_by: str
    order: Literal["asc", "desc"]
    sectors: list[MarketMapSector]


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


class QuoteTick(BaseModel):
    symbol: str
    price: float
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    timestamp: datetime


class QuoteEvent(BaseModel):
    type: Literal["quote"] = "quote"
    data: list[QuoteTick]


class SubscribedEvent(BaseModel):
    type: Literal["subscribed"] = "subscribed"
    symbols: list[str]


class HeartbeatEvent(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: datetime


class ErrorResponse(BaseModel):
    detail: str
    code: str


# Passthrough market payloads are returned unwrapped (dict or list).
MarketPayload = dict[str, Any] | list[Any]
