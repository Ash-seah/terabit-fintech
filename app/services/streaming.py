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

from app.db.repositories import delete_old_trades, persist_trades_and_minutes
from app.schemas import Trade, TradeEvent
from app.services.cache import Cache

logger = logging.getLogger(__name__)
TRADE_CHANNEL = "market:trades"


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

    async def connect(self, websocket: WebSocket, symbols: frozenset[str]) -> FrontendConnection:
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
            if connection.symbols and not connection.symbols.intersection(event_symbols):
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
        while True:
            event = await connection.queue.get()
            await asyncio.wait_for(connection.websocket.send_json(event), timeout=5)


class FinnhubStreamer:
    def __init__(
        self,
        ws_url: str,
        api_key: str,
        symbols: tuple[str, ...],
        redis: Redis,
        cache: Cache,
        trade_queue: asyncio.Queue[Trade],
    ) -> None:
        self.url = f"{ws_url}?{urlencode({'token': api_key})}"
        self.symbols = symbols
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
                    for symbol in self.symbols:
                        await websocket.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                    logger.info("Finnhub WebSocket connected")
                    attempt = 0
                    while True:
                        raw = await asyncio.wait_for(websocket.recv(), timeout=60)
                        await self._handle(raw)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, TimeoutError, ValueError, RedisError):
                attempt += 1
                delay = min(60.0, 2 ** min(attempt, 6)) + random.uniform(0, 1)
                logger.warning("Finnhub WebSocket disconnected; retrying in %.1fs", delay)
                await asyncio.sleep(delay)

    async def _handle(self, raw: str | bytes) -> None:
        payload = orjson.loads(raw)
        if not isinstance(payload, dict) or payload.get("type") != "trade":
            return
        trades: list[Trade] = []
        for item in payload.get("data", []):
            try:
                trade = Trade(
                    symbol=str(item["s"]).upper(),
                    price=float(item["p"]),
                    volume=float(item.get("v", 0)),
                    timestamp=datetime.fromtimestamp(float(item["t"]) / 1000, tz=UTC),
                    conditions=[str(value) for value in item.get("c", [])],
                )
            except (KeyError, TypeError, ValueError):
                logger.debug("Discarding malformed Finnhub trade")
                continue
            trades.append(trade)
            await self.cache.set_json(f"latest:{trade.symbol}", trade.model_dump(mode="json"), 60)
            try:
                self.trade_queue.put_nowait(trade)
            except asyncio.QueueFull:
                logger.warning("Trade persistence queue full; dropping database copy")
        if trades:
            event = TradeEvent(data=trades).model_dump(mode="json")
            await self.redis.publish(TRADE_CHANNEL, orjson.dumps(event))


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
