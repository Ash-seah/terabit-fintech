import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import StringConstraints
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.symbols import DEFAULT_CRYPTO_EXCHANGE, DEFAULT_STOCK_EXCHANGE
from app.providers.yahoo import HistoricalDataNotFoundError, HistoricalProviderError
from app.schemas import (
    ErrorResponse,
    HeartbeatEvent,
    HistoricalResponse,
    MarketPayload,
    SymbolsOverviewResponse,
    TradingViewHistoryResponse,
)
from app.services.historical import HistoricalService
from app.services.market import MarketDataService
from app.services.overview import OverviewService
from app.services.quotes import QuoteService
from app.services.streaming import ConnectionManager

router = APIRouter()
historical_router = APIRouter(prefix="/api/v1", tags=["charts"])
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


def _overview_service(request: Request) -> OverviewService:
    return request.app.state.overview_service  # type: ignore[no-any-return]


def _quote_service(request: Request) -> QuoteService:
    return request.app.state.quote_service  # type: ignore[no-any-return]


async def _market(
    request: Request,
    resource: str,
    path: str,
    params: dict[str, Any],
    ttl: int,
) -> MarketPayload:
    return await _market_service(request).get(
        resource, path, {key: value for key, value in params.items() if value is not None}, ttl
    )


@historical_router.get(
    "/historical/{ticker}",
    response_model=HistoricalResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="OHLCV history (DB-backed)",
)
async def historical(
    request: Request,
    ticker: Symbol,
    period: Period | None = None,
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


@historical_router.get(
    "/charts/{ticker}",
    response_model=TradingViewHistoryResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="TradingView Lightweight Charts OHLC bars",
)
async def tradingview_chart(
    request: Request,
    ticker: Symbol,
    period: Period | None = None,
    interval: Interval = "1d",
) -> TradingViewHistoryResponse:
    try:
        return await _historical_service(request).tradingview(ticker, interval, period)
    except HistoricalDataNotFoundError as exc:
        return JSONResponse(  # type: ignore[return-value]
            status_code=404, content={"detail": str(exc), "code": "historical_not_found"}
        )
    except HistoricalProviderError as exc:
        return JSONResponse(  # type: ignore[return-value]
            status_code=503,
            content={"detail": str(exc), "code": "historical_provider_unavailable"},
        )


@market_router.get(
    "/symbols",
    response_model=SymbolsOverviewResponse,
    summary="Curated symbol overview with live quote fields",
)
async def symbols_overview(request: Request) -> SymbolsOverviewResponse:
    return await _overview_service(request).list_symbols()


@market_router.get("/quotes/{symbol}")
async def quote(request: Request, symbol: Symbol) -> MarketPayload:
    try:
        return await _quote_service(request).get(symbol)
    except HistoricalProviderError as exc:
        return JSONResponse(  # type: ignore[return-value]
            status_code=503,
            content={"detail": str(exc), "code": "quote_unavailable"},
        )


@market_router.get("/symbols/search")
async def symbol_search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> MarketPayload:
    return await _market(
        request, "symbol-search", "/search", {"q": q, "exchange": DEFAULT_STOCK_EXCHANGE}, 86_400
    )


@market_router.get("/market/status")
async def market_status(request: Request) -> MarketPayload:
    return await _market(
        request,
        "market-status",
        "/stock/market-status",
        {"exchange": DEFAULT_STOCK_EXCHANGE},
        300,
    )


@market_router.get("/companies/{symbol}/profile")
async def company_profile(request: Request, symbol: Symbol) -> MarketPayload:
    return await _market(request, "company-profile", "/stock/profile2", {"symbol": symbol}, 604_800)


@market_router.get("/companies/{symbol}/news")
async def company_news(
    request: Request,
    symbol: Symbol,
    from_date: date | None = None,
    to_date: date | None = None,
) -> MarketPayload:
    end = to_date or date.today()
    start = from_date or (end - timedelta(days=7))
    return await _market(
        request,
        "company-news",
        "/company-news",
        {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()},
        1_800,
    )


@market_router.get("/companies/{symbol}/peers")
async def company_peers(request: Request, symbol: Symbol) -> MarketPayload:
    return await _market(request, "company-peers", "/stock/peers", {"symbol": symbol}, 604_800)


@market_router.get("/companies/{symbol}/fundamentals")
async def company_fundamentals(
    request: Request, symbol: Symbol, metric: str = "all"
) -> MarketPayload:
    return await _market(
        request,
        "company-fundamentals",
        "/stock/metric",
        {"symbol": symbol, "metric": metric},
        86_400,
    )


@market_router.get("/companies/{symbol}/earnings")
async def company_earnings(
    request: Request, symbol: Symbol, limit: Annotated[int, Query(ge=1, le=100)] = 4
) -> MarketPayload:
    return await _market(
        request, "company-earnings", "/stock/earnings", {"symbol": symbol, "limit": limit}, 86_400
    )


@market_router.get("/companies/{symbol}/recommendations")
async def recommendations(request: Request, symbol: Symbol) -> MarketPayload:
    return await _market(
        request, "recommendations", "/stock/recommendation", {"symbol": symbol}, 86_400
    )


@market_router.get("/calendars/earnings")
async def earnings_calendar(
    request: Request,
    from_date: date | None = None,
    to_date: date | None = None,
    symbol: Symbol | None = None,
) -> MarketPayload:
    # Free plan covers about one month of US earnings calendar.
    start = from_date or date.today()
    end = to_date or (start + timedelta(days=30))
    return await _market(
        request,
        "earnings-calendar",
        "/calendar/earnings",
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "symbol": symbol,
            "international": False,
        },
        3_600,
    )


@market_router.get("/forex/symbols")
async def forex_symbols(request: Request) -> MarketPayload:
    return await _market(
        request, "forex-symbols", "/forex/symbol", {"exchange": "oanda"}, 604_800
    )


@market_router.get("/crypto/symbols")
async def crypto_symbols(request: Request) -> MarketPayload:
    return await _market(
        request,
        "crypto-symbols",
        "/crypto/symbol",
        {"exchange": DEFAULT_CRYPTO_EXCHANGE},
        604_800,
    )


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


@router.get(
    "/api/ws-tester",
    response_class=HTMLResponse,
    tags=["websockets"],
    summary="Interactive browser WebSocket tester",
)
async def websocket_tester() -> HTMLResponse:
    return HTMLResponse(_WS_TESTER_HTML)


@router.websocket("/ws/live")
async def live(websocket: WebSocket, symbols: str = "") -> None:
    configured = frozenset(
        getattr(websocket.app.state, "stream_symbols", None)
        or websocket.app.state.settings.configured_stream_symbols
    )
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


_WS_TESTER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Live WebSocket Tester</title>
  <style>
    :root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #0b1220; color: #e8eefc; }
    main { max-width: 960px; margin: 0 auto; padding: 24px; }
    h1 { font-size: 1.4rem; margin: 0 0 8px; }
    p { color: #9db0d0; margin-top: 0; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0; }
    input, button {
      border: 1px solid #2a3a58; background: #121a2b; color: inherit;
      border-radius: 8px; padding: 10px 12px; font: inherit;
    }
    input { flex: 1; min-width: 240px; }
    button { cursor: pointer; background: #2554e8; border-color: #2554e8; }
    button.secondary { background: #1a2438; }
    #status { font-weight: 600; }
    #log {
      height: 55vh; overflow: auto; background: #070d18; border: 1px solid #223149;
      border-radius: 12px; padding: 12px; white-space: pre-wrap;
      font-family: ui-monospace, monospace;
      font-size: 12px; line-height: 1.45;
    }
  </style>
</head>
<body>
  <main>
    <h1>Live WebSocket Tester</h1>
    <p>
      Connects to <code>/ws/live</code>. Leave symbols empty for all curated streams,
      or pass a comma-separated subset (example: <code>AAPL,BINANCE:BTCUSDT</code>).
    </p>
    <div class="row">
      <input id="symbols" placeholder="leave empty for all curated symbols" value="" />
      <button id="connect">Connect</button>
      <button id="disconnect" class="secondary">Disconnect</button>
    </div>
    <p>Status: <span id="status">disconnected</span></p>
    <div id="log"></div>
  </main>
  <script>
    const logEl = document.getElementById("log");
    const statusEl = document.getElementById("status");
    let socket = null;

    function log(message) {
      const stamp = new Date().toISOString();
      logEl.textContent = `[${stamp}] ${message}\\n` + logEl.textContent;
    }

    function wsUrl(symbols) {
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const query = symbols ? `?symbols=${encodeURIComponent(symbols)}` : "";
      return `${protocol}//${location.host}/ws/live${query}`;
    }

    function detachSocket(active) {
      if (!active) return;
      active.onopen = null;
      active.onmessage = null;
      active.onerror = null;
      active.onclose = null;
      try {
        if (active.readyState === WebSocket.CONNECTING || active.readyState === WebSocket.OPEN) {
          active.close(1000, "client disconnect");
        }
      } catch (error) {
        log(`disconnect error: ${error}`);
      }
    }

    function disconnect(reason = "disconnected") {
      const active = socket;
      socket = null;
      statusEl.textContent = reason;
      if (active) {
        detachSocket(active);
        log("disconnected by user");
      }
    }

    document.getElementById("connect").onclick = () => {
      disconnect("reconnecting…");
      const symbols = document.getElementById("symbols").value.trim();
      const url = wsUrl(symbols);
      statusEl.textContent = "connecting…";
      const active = new WebSocket(url);
      socket = active;
      active.onopen = () => {
        if (socket !== active) return;
        statusEl.textContent = "connected";
        log(`opened ${url}`);
      };
      active.onmessage = (event) => {
        if (socket !== active) return;
        log(event.data);
      };
      active.onerror = () => {
        if (socket !== active) return;
        log("socket error");
      };
      active.onclose = (event) => {
        if (socket === active) socket = null;
        statusEl.textContent = `closed (${event.code})`;
        log(`closed code=${event.code} reason=${event.reason || "-"}`);
      };
    };

    document.getElementById("disconnect").onclick = () => disconnect();
  </script>
</body>
</html>
"""
