import asyncio
import json
from typing import Any

import pytest
from starlette.websockets import WebSocketState

from app.schemas import Trade
from app.services.streaming import ConnectionManager, FinnhubStreamer


class FakeWebSocket:
    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.client_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_connection_manager_filters_symbols() -> None:
    manager = ConnectionManager()
    aapl_socket = FakeWebSocket()
    btc_socket = FakeWebSocket()
    aapl = await manager.connect(aapl_socket, frozenset({"AAPL"}))  # type: ignore[arg-type]
    btc = await manager.connect(btc_socket, frozenset({"BINANCE:BTCUSDT"}))  # type: ignore[arg-type]

    await manager.broadcast({"type": "trade", "data": [{"symbol": "AAPL"}]})
    await asyncio.sleep(0)
    assert len(aapl_socket.sent) == 1
    assert btc_socket.sent == []
    await manager.disconnect(aapl)
    await manager.disconnect(btc)


@pytest.mark.asyncio
async def test_finnhub_packet_is_normalized_and_published() -> None:
    published: list[bytes] = []
    cached: list[str] = []

    class FakeRedis:
        async def publish(self, channel: str, value: bytes) -> None:
            published.append(value)

    class FakeCache:
        async def set_json(self, key: str, value: Any, ttl: int) -> None:
            cached.append(key)

    queue: asyncio.Queue[Trade] = asyncio.Queue()
    streamer = FinnhubStreamer(
        "wss://example.test",
        "secret",
        ("AAPL",),
        FakeRedis(),  # type: ignore[arg-type]
        FakeCache(),  # type: ignore[arg-type]
        queue,
    )
    await streamer._handle(
        json.dumps(
            {
                "type": "trade",
                "data": [{"s": "AAPL", "p": 200.5, "v": 10, "t": 1_700_000_000_000}],
            }
        )
    )
    assert cached == ["latest:AAPL"]
    assert queue.qsize() == 1
    assert json.loads(published[0])["data"][0]["symbol"] == "AAPL"
