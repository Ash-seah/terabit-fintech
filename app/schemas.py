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
    source: str
    cached: bool = False
    points: list[HistoricalPoint]


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


class ProviderResponse(BaseModel):
    provider: Literal["finnhub"] = "finnhub"
    resource: str
    cached: bool = False
    stale: bool = False
    data: dict[str, Any] | list[Any]
