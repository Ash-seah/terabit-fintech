import pytest
from redis.exceptions import RedisError

from app.services.cache import RedisTokenBucket


@pytest.mark.asyncio
async def test_rate_limiter_enforces_limit() -> None:
    class FakeRedis:
        results = iter((1, 1, 0))

        async def eval(self, script: str, key_count: int, *args: object) -> int:
            return next(self.results)

    limiter = RedisTokenBucket(FakeRedis())  # type: ignore[arg-type]
    assert await limiter.allow("test", 2)
    assert await limiter.allow("test", 2)
    assert not await limiter.allow("test", 2)


@pytest.mark.asyncio
async def test_rate_limiter_fails_closed_when_redis_drops() -> None:
    class BrokenRedis:
        async def eval(self, script: str, key_count: int, *args: object) -> int:
            raise RedisError("offline")

    limiter = RedisTokenBucket(BrokenRedis())  # type: ignore[arg-type]
    assert not await limiter.allow("test", 10)
