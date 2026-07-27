import asyncio
import contextlib
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import orjson
import websockets
from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed

from app.core.jsonutil import dumps_plain
from app.core.symbols import curated_upstream_stream_symbols, public_symbol_for
from app.db.repositories import delete_old_trades, persist_trades_and_minutes
from app.providers.yahoo import HistoricalProviderError, YahooFinanceProvider
from app.schemas import QuoteEvent, QuoteTick, Trade, TradeEvent
from app.services.cache import Cache

logger = logging.getLogger(__name__)
TRADE_CHANNEL = "market:trades"


def _round_price(value: float) -> float:
    return float(format(value, ".6f"))


def _round_volume(value: float) -> float:
    return float(format(value, ".8f"))


@dataclass(eq=False)
class FrontendConnection:
    websocket: WebSocket
    symbols: frozenset[str]
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(maxsize=200))
    writer: asyncio.Task[None] | None = None


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[FrontendConnection] = set()
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        symbols: frozenset[str],
        *,
        already_accepted: bool = False,
    ) -> FrontendConnection:
        if not already_accepted:
            await websocket.accept()
        connection = FrontendConnection(websocket=websocket, symbols=symbols)
        connection.writer = asyncio.create_task(self._writer(connection), name="frontend-ws-writer")
        async with self._lock:
            self._connections.add(connection)
        return connection

    async def disconnect(self, connection: FrontendConnection) -> None:
        async with self._lock:
            self._connections.discard(connection)
        if connection.writer is not None:
            connection.writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await connection.writer
        if connection.websocket.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(RuntimeError):
                await connection.websocket.close()

    async def broadcast(self, event: dict[str, Any]) -> None:
        event_symbols = {
            str(item.get("symbol")) for item in event.get("data", []) if item.get("symbol")
        }
        async with self._lock:
            connections = list(self._connections)
        overloaded: list[FrontendConnection] = []
        for connection in connections:
            if (
                event_symbols
                and connection.symbols
                and not connection.symbols.intersection(event_symbols)
            ):
                continue
            try:
                connection.queue.put_nowait(event)
            except asyncio.QueueFull:
                overloaded.append(connection)
        for connection in overloaded:
            logger.warning("Disconnecting backpressured frontend WebSocket")
            await self.disconnect(connection)

    @staticmethod
    async def _writer(connection: FrontendConnection) -> None:
        try:
            while True:
                event = await connection.queue.get()
                await asyncio.wait_for(
                    connection.websocket.send_text(dumps_plain(event)),
                    timeout=5,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.info("Frontend WebSocket writer stopped", exc_info=True)
            if connection.websocket.client_state == WebSocketState.CONNECTED:
                with contextlib.suppress(RuntimeError):
                    await connection.websocket.close(code=1000)


class FinnhubStreamer:
    def __init__(
        self,
        ws_url: str,
        api_key: str,
        public_symbols: tuple[str, ...],
        redis: Redis,
        cache: Cache,
        trade_queue: asyncio.Queue[Trade],
    ) -> None:
        self.url = f"{ws_url}?{urlencode({'token': api_key})}"
        # Subscribe with upstream IDs; emit public IDs to clients.
        self.upstream_symbols = curated_upstream_stream_symbols()
        self.public_symbols = public_symbols
        self.redis = redis
        self.cache = cache
        self.trade_queue = trade_queue

    async def run(self) -> None:
        attempt = 0
        while True:
            try:
                async with websockets.connect(
                    self.url, open_timeout=10, ping_interval=20, ping_timeout=20
                ) as websocket:
                    for symbol in self.upstream_symbols:
                        await websocket.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                    logger.info(
                        "Live feed connected; subscribed to %d upstream symbols",
                        len(self.upstream_symbols),
                    )
                    attempt = 0
                    while True:
                        raw = await asyncio.wait_for(websocket.recv(), timeout=60)
                        await self._handle(raw)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, TimeoutError, ValueError, RedisError):
                attempt += 1
                delay = min(60.0, 2 ** min(attempt, 6)) + random.uniform(0, 1)
                logger.warning("Live feed disconnected; retrying in %.1fs", delay)
                await asyncio.sleep(delay)

    async def _handle(self, raw: str | bytes) -> None:
        payload = orjson.loads(raw)
        if not isinstance(payload, dict) or payload.get("type") != "trade":
            return
        trades: list[Trade] = []
        for item in payload.get("data", []):
            try:
                trade = Trade(
                    symbol=public_symbol_for(str(item["s"])),
                    price=_round_price(float(item["p"])),
                    volume=_round_volume(float(item.get("v", 0))),
                    timestamp=datetime.fromtimestamp(float(item["t"]) / 1000, tz=UTC),
                    conditions=[str(value) for value in item.get("c", [])],
                )
            except (KeyError, TypeError, ValueError):
                logger.debug("Discarding malformed trade packet")
                continue
            trades.append(trade)
            await self.cache.set_json(
                f"latest:{trade.symbol}",
                trade.model_dump(mode="json"),
                300,
            )
            try:
                self.trade_queue.put_nowait(trade)
            except asyncio.QueueFull:
                logger.warning("Trade persistence queue full; dropping database copy")
        if trades:
            event = TradeEvent(data=trades).model_dump(mode="json")
            await self.redis.publish(TRADE_CHANNEL, dumps_plain(event).encode())


class RedisTradeSubscriber:
    def __init__(self, redis: Redis, manager: ConnectionManager) -> None:
        self.redis = redis
        self.manager = manager

    async def run(self) -> None:
        while True:
            pubsub = self.redis.pubsub()
            try:
                await pubsub.subscribe(TRADE_CHANNEL)
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    payload = orjson.loads(message["data"])
                    if isinstance(payload, dict):
                        await self.manager.broadcast(payload)
            except asyncio.CancelledError:
                raise
            except (RedisError, orjson.JSONDecodeError):
                logger.exception("Redis trade subscriber failed; reconnecting")
                await asyncio.sleep(1)
            finally:
                with contextlib.suppress(RedisError):
                    await pubsub.aclose()  # type: ignore[no-untyped-call]


async def quote_pulse_worker(
    symbols: tuple[str, ...],
    yahoo: YahooFinanceProvider,
    cache: Cache,
    redis: Redis,
    interval_seconds: float = 30.0,
) -> None:
    """Push Yahoo quotes for all curated symbols so equities still update after hours."""
    while True:
        try:
            quotes = await yahoo.quotes(symbols)
            ticks: list[QuoteTick] = []
            now = datetime.now(UTC)
            for symbol, quote in quotes.items():
                price = _round_price(float(quote["c"]))
                previous = (
                    _round_price(float(quote["pc"])) if quote.get("pc") is not None else None
                )
                change = _round_price(price - previous) if previous is not None else None
                change_percent = (
                    _round_price(((price - previous) / previous) * 100)
                    if previous
                    else None
                )
                tick = QuoteTick(
                    symbol=symbol,
                    price=price,
                    previous_close=previous,
                    change=change,
                    change_percent=change_percent,
                    timestamp=now,
                )
                ticks.append(tick)
                await cache.set_json(
                    f"latest:{symbol}",
                    {"price": price, "timestamp": now.isoformat()},
                    300,
                )
                await cache.set_json(f"quote:yahoo:{symbol}", quote, 120)
            if ticks:
                event = QuoteEvent(data=ticks).model_dump(mode="json")
                await redis.publish(TRADE_CHANNEL, dumps_plain(event).encode())
                logger.info("Published quote pulse for %d symbols", len(ticks))
        except (HistoricalProviderError, RedisError, TypeError, ValueError):
            logger.exception("Quote pulse failed")
        await asyncio.sleep(interval_seconds)


async def trade_persistence_worker(
    queue: asyncio.Queue[Trade],
    sessions: async_sessionmaker[AsyncSession],
    batch_size: int,
    flush_seconds: float,
) -> None:
    batch: list[Trade] = []
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=flush_seconds)
                batch.append(item)
                if len(batch) < batch_size:
                    continue
            except TimeoutError:
                if not batch:
                    continue
            await _flush_trade_batch(sessions, batch)
    finally:
        if batch:
            await _flush_trade_batch(sessions, batch)


async def _flush_trade_batch(
    sessions: async_sessionmaker[AsyncSession], batch: list[Trade]
) -> None:
    try:
        async with sessions() as session:
            await persist_trades_and_minutes(session, batch)
    except SQLAlchemyError:
        logger.exception("Trade batch persistence failed")
    finally:
        batch.clear()


async def retention_worker(sessions: async_sessionmaker[AsyncSession], retention_days: int) -> None:
    while True:
        try:
            async with sessions() as session:
                deleted = await delete_old_trades(session, retention_days)
            logger.info("Raw trade retention removed %d rows", deleted)
        except SQLAlchemyError:
            logger.exception("Raw trade retention failed")
        await asyncio.sleep(24 * 60 * 60)
