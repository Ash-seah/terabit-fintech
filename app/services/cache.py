import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import orjson
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def get_json(self, key: str) -> Any | None:
        try:
            value = await self.redis.get(key)
            return orjson.loads(value) if value is not None else None
        except (RedisError, orjson.JSONDecodeError):
            logger.exception("Redis read failed")
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self.redis.set(key, orjson.dumps(value), ex=ttl)
        except RedisError:
            logger.exception("Redis write failed")

    async def mget_json(self, keys: list[str]) -> list[Any | None]:
        if not keys:
            return []
        try:
            values = await self.redis.mget(keys)
        except RedisError:
            logger.exception("Redis mget failed")
            return [None] * len(keys)
        parsed: list[Any | None] = []
        for value in values:
            if value is None:
                parsed.append(None)
                continue
            try:
                parsed.append(orjson.loads(value))
            except orjson.JSONDecodeError:
                parsed.append(None)
        return parsed

    @asynccontextmanager
    async def lock(self, key: str, lock_ttl: int = 20) -> AsyncIterator[None]:
        lock = self.redis.lock(f"lock:{key}", timeout=lock_ttl, blocking_timeout=5)
        try:
            acquired = bool(await lock.acquire())
        except RedisError:
            logger.exception("Redis lock failed")
            yield
            return
        try:
            yield
        finally:
            if acquired:
                try:
                    await lock.release()
                except RedisError:
                    logger.warning("Redis lock release failed", exc_info=True)


class RedisTokenBucket:
    _SCRIPT = """
    local capacity = tonumber(ARGV[1])
    local refill_per_second = tonumber(ARGV[2])
    local time = redis.call('TIME')
    local now = tonumber(time[1]) + tonumber(time[2]) / 1000000
    local state = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
    local tokens = tonumber(state[1]) or capacity
    local updated = tonumber(state[2]) or now
    tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill_per_second)
    local allowed = 0
    if tokens >= 1 then
        tokens = tokens - 1
        allowed = 1
    end
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
    redis.call('EXPIRE', KEYS[1], math.ceil((capacity / refill_per_second) * 2))
    return allowed
    """

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def allow(self, bucket: str, limit: int, window_seconds: int = 60) -> bool:
        capacity = min(5, limit - 1)
        refill_per_second = (limit - capacity) / window_seconds
        try:
            allowed = await self.redis.eval(
                self._SCRIPT,
                1,
                bucket,
                capacity,
                refill_per_second,
            )
            return bool(allowed)
        except RedisError:
            logger.exception("Rate limiter unavailable; failing closed")
            return False
