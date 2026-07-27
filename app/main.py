import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.api.router import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.providers.finnhub import (
    FinnhubClient,
    FinnhubEntitlementError,
    FinnhubError,
    FinnhubRateLimitError,
)
from app.providers.yahoo import YahooFinanceProvider
from app.schemas import Trade
from app.services.cache import Cache, RedisTokenBucket
from app.services.historical import HistoricalService
from app.services.market import MarketDataService
from app.services.overview import OverviewService
from app.services.quotes import QuoteService
from app.services.streaming import (
    ConnectionManager,
    FinnhubStreamer,
    RedisTradeSubscriber,
    retention_worker,
    trade_persistence_worker,
)

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config: Settings = app.state.settings
    redis = Redis.from_url(config.redis_url, decode_responses=False)
    database = Database(config.database_url)
    cache = Cache(redis)
    limiter = RedisTokenBucket(redis)
    finnhub = FinnhubClient(config.finnhub_rest_url, config.finnhub_api_key.get_secret_value())
    manager = ConnectionManager()
    trade_queue: asyncio.Queue[Trade] = asyncio.Queue(maxsize=10_000)

    yahoo = YahooFinanceProvider()
    app.state.redis = redis
    app.state.database = database
    app.state.cache = cache
    app.state.connection_manager = manager
    app.state.historical_service = HistoricalService(
        cache,
        database.session_factory,
        yahoo,
        config.historical_cache_ttl_seconds,
    )
    app.state.market_service = MarketDataService(
        cache,
        limiter,
        database.session_factory,
        finnhub,
        config.finnhub_rest_calls_per_minute,
    )
    app.state.overview_service = OverviewService(
        cache,
        yahoo,
        database.session_factory,
        ttl=config.overview_cache_ttl_seconds,
    )
    app.state.quote_service = QuoteService(
        cache,
        yahoo,
        ttl=config.quote_cache_ttl_seconds,
    )

    try:
        await redis.ping()
    except RedisError:
        logger.exception("Redis unavailable during startup; degraded mode enabled")

    stream_symbols = config.configured_stream_symbols
    logger.info(
        "Subscribing live stream to %d symbols: %s",
        len(stream_symbols),
        ",".join(stream_symbols),
    )
    app.state.stream_symbols = stream_symbols
    streamer = FinnhubStreamer(
        config.finnhub_ws_url,
        config.finnhub_api_key.get_secret_value(),
        stream_symbols,
        redis,
        cache,
        trade_queue,
    )
    tasks = [
        asyncio.create_task(streamer.run(), name="finnhub-streamer"),
        asyncio.create_task(
            RedisTradeSubscriber(redis, manager).run(), name="redis-trade-subscriber"
        ),
        asyncio.create_task(
            trade_persistence_worker(
                trade_queue,
                database.session_factory,
                config.trade_batch_size,
                config.trade_flush_seconds,
            ),
            name="trade-persistence",
        ),
        asyncio.create_task(
            retention_worker(database.session_factory, config.raw_trade_retention_days),
            name="trade-retention",
        ),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await finnhub.close()
        with contextlib.suppress(RedisError):
            await redis.aclose()
        await database.dispose()


def create_app() -> FastAPI:
    # Docs live under /api/* so host Nginx `location /api` proxies match production URLs
    # such as https://fintech.terabitventure.com/api/docs without path rewriting.
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Cached historical and live financial market data. "
            "Swagger: /api/docs. Interactive WebSocket tester: /api/ws-tester."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.configured_cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def public_rate_limit(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if path.startswith(
            ("/health", "/api/docs", "/api/redoc", "/api/openapi.json", "/api/ws-tester")
        ):
            return await call_next(request)
        redis: Redis = request.app.state.redis
        limiter = RedisTokenBucket(redis)
        client_ip = request.client.host if request.client else "unknown"
        if not await limiter.allow(
            f"ratelimit:client:{client_ip}",
            settings.frontend_rate_limit_per_minute,
        ):
            return JSONResponse(
                status_code=429,
                content={"detail": "Request rate limit exceeded", "code": "rate_limited"},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

    @app.exception_handler(FinnhubError)
    async def finnhub_error_handler(_request: Request, exc: FinnhubError) -> JSONResponse:
        if isinstance(exc, FinnhubRateLimitError):
            status = 429
        elif isinstance(exc, FinnhubEntitlementError):
            status = 403
        else:
            status = 503
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc), "code": exc.code},
            headers={"Retry-After": "60"} if status == 429 else None,
        )

    app.include_router(router)
    return app


app = create_app()
