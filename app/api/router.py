import asyncio
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import StringConstraints
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.providers.yahoo import HistoricalDataNotFoundError, HistoricalProviderError
from app.schemas import (
    ErrorResponse,
    HeartbeatEvent,
    HistoricalResponse,
    ProviderResponse,
)
from app.services.historical import HistoricalService
from app.services.market import MarketDataService
from app.services.streaming import ConnectionManager

router = APIRouter()
historical_router = APIRouter(prefix="/api/v1/historical", tags=["historical"])
market_router = APIRouter(prefix="/api/v1", tags=["market data"])

Symbol = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z0-9:._-]{1,64}$"),
]
Period = Literal["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
Interval = Literal[
    "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"
]


def _historical_service(request: Request) -> HistoricalService:
    return request.app.state.historical_service  # type: ignore[no-any-return]


def _market_service(request: Request) -> MarketDataService:
    return request.app.state.market_service  # type: ignore[no-any-return]


async def _market(
    request: Request,
    resource: str,
    path: str,
    params: dict[str, Any],
    ttl: int,
) -> ProviderResponse:
    return await _market_service(request).get(
        resource, path, {key: value for key, value in params.items() if value is not None}, ttl
    )


@historical_router.get(
    "/{ticker}",
    response_model=HistoricalResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def historical(
    request: Request,
    ticker: Symbol,
    period: Period = "1mo",
    interval: Interval = "1d",
) -> HistoricalResponse:
    try:
        return await _historical_service(request).get(ticker, period, interval)
    except HistoricalDataNotFoundError as exc:
        return JSONResponse(  # type: ignore[return-value]
            status_code=404, content={"detail": str(exc), "code": "historical_not_found"}
        )
    except HistoricalProviderError as exc:
        return JSONResponse(  # type: ignore[return-value]
            status_code=503,
            content={"detail": str(exc), "code": "historical_provider_unavailable"},
        )


@market_router.get("/quotes/{symbol}", response_model=ProviderResponse)
async def quote(request: Request, symbol: Symbol) -> ProviderResponse:
    return await _market(request, "quote", "/quote", {"symbol": symbol}, 5)


@market_router.get("/symbols/search", response_model=ProviderResponse)
async def symbol_search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    exchange: str | None = None,
) -> ProviderResponse:
    return await _market(request, "symbol-search", "/search", {"q": q, "exchange": exchange}, 3600)


@market_router.get("/symbols/stocks/{exchange}", response_model=ProviderResponse)
async def stock_symbols(request: Request, exchange: str) -> ProviderResponse:
    return await _market(request, "stock-symbols", "/stock/symbol", {"exchange": exchange}, 86400)


@market_router.get("/market/status/{exchange}", response_model=ProviderResponse)
async def market_status(request: Request, exchange: str) -> ProviderResponse:
    return await _market(
        request, "market-status", "/stock/market-status", {"exchange": exchange}, 60
    )


@market_router.get("/companies/{symbol}/profile", response_model=ProviderResponse)
async def company_profile(request: Request, symbol: Symbol) -> ProviderResponse:
    return await _market(request, "company-profile", "/stock/profile2", {"symbol": symbol}, 86400)


@market_router.get("/companies/{symbol}/news", response_model=ProviderResponse)
async def company_news(
    request: Request, symbol: Symbol, from_date: date, to_date: date
) -> ProviderResponse:
    return await _market(
        request,
        "company-news",
        "/company-news",
        {"symbol": symbol, "from": from_date.isoformat(), "to": to_date.isoformat()},
        300,
    )


@market_router.get("/companies/{symbol}/peers", response_model=ProviderResponse)
async def company_peers(request: Request, symbol: Symbol) -> ProviderResponse:
    return await _market(request, "company-peers", "/stock/peers", {"symbol": symbol}, 86400)


@market_router.get("/companies/{symbol}/fundamentals", response_model=ProviderResponse)
async def company_fundamentals(
    request: Request, symbol: Symbol, metric: str = "all"
) -> ProviderResponse:
    return await _market(
        request,
        "company-fundamentals",
        "/stock/metric",
        {"symbol": symbol, "metric": metric},
        21600,
    )


@market_router.get("/companies/{symbol}/earnings", response_model=ProviderResponse)
async def company_earnings(
    request: Request, symbol: Symbol, limit: Annotated[int, Query(ge=1, le=100)] = 4
) -> ProviderResponse:
    return await _market(
        request, "company-earnings", "/stock/earnings", {"symbol": symbol, "limit": limit}, 21600
    )


@market_router.get("/companies/{symbol}/recommendations", response_model=ProviderResponse)
async def recommendations(request: Request, symbol: Symbol) -> ProviderResponse:
    return await _market(
        request, "recommendations", "/stock/recommendation", {"symbol": symbol}, 21600
    )


@market_router.get("/calendars/earnings", response_model=ProviderResponse)
async def earnings_calendar(
    request: Request,
    from_date: date,
    to_date: date,
    symbol: Symbol | None = None,
) -> ProviderResponse:
    return await _market(
        request,
        "earnings-calendar",
        "/calendar/earnings",
        {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "symbol": symbol,
            "international": False,
        },
        3600,
    )


@market_router.get("/forex/exchanges", response_model=ProviderResponse)
async def forex_exchanges(request: Request) -> ProviderResponse:
    return await _market(request, "forex-exchanges", "/forex/exchange", {}, 86400)


@market_router.get("/forex/symbols/{exchange}", response_model=ProviderResponse)
async def forex_symbols(request: Request, exchange: str) -> ProviderResponse:
    return await _market(request, "forex-symbols", "/forex/symbol", {"exchange": exchange}, 86400)


@market_router.get("/crypto/exchanges", response_model=ProviderResponse)
async def crypto_exchanges(request: Request) -> ProviderResponse:
    return await _market(request, "crypto-exchanges", "/crypto/exchange", {}, 86400)


@market_router.get("/crypto/symbols/{exchange}", response_model=ProviderResponse)
async def crypto_symbols(request: Request, exchange: str) -> ProviderResponse:
    return await _market(request, "crypto-symbols", "/crypto/symbol", {"exchange": exchange}, 86400)


@router.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
async def readiness(request: Request) -> JSONResponse:
    checks = {"redis": False, "postgres": False}
    try:
        checks["redis"] = bool(await request.app.state.redis.ping())
    except Exception:
        pass
    try:
        async with request.app.state.database.session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = True
    except SQLAlchemyError:
        pass
    healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )


@router.websocket("/ws/live")
async def live(websocket: WebSocket, symbols: str = "") -> None:
    configured = frozenset(websocket.app.state.settings.configured_stream_symbols)
    requested = frozenset(symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip())
    if requested and not requested.issubset(configured):
        await websocket.close(code=1008, reason="Only configured stream symbols are available")
        return
    manager: ConnectionManager = websocket.app.state.connection_manager
    connection = await manager.connect(websocket, requested)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except TimeoutError:
                connection.queue.put_nowait(
                    HeartbeatEvent(timestamp=datetime.now(UTC)).model_dump(mode="json")
                )
    except (WebSocketDisconnect, RuntimeError, asyncio.QueueFull):
        pass
    finally:
        await manager.disconnect(connection)


router.include_router(historical_router)
router.include_router(market_router)
