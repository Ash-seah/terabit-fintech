import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import get_snapshot, upsert_snapshot
from app.providers.finnhub import (
    FinnhubClient,
    FinnhubEntitlementError,
    FinnhubError,
    FinnhubRateLimitError,
)
from app.schemas import MarketPayload
from app.services.cache import Cache, RedisTokenBucket

logger = logging.getLogger(__name__)


class MarketDataService:
    def __init__(
        self,
        cache: Cache,
        limiter: RedisTokenBucket,
        sessions: async_sessionmaker[AsyncSession],
        client: FinnhubClient,
        quota_per_minute: int,
    ) -> None:
        self.cache = cache
        self.limiter = limiter
        self.sessions = sessions
        self.client = client
        self.quota_per_minute = quota_per_minute

    async def get(
        self,
        resource: str,
        path: str,
        params: dict[str, Any],
        ttl: int,
    ) -> MarketPayload:
        canonical = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
        digest = hashlib.sha256(f"{path}:{canonical}".encode()).hexdigest()
        key = f"finnhub:{resource}:{digest}"
        entitlement_key = f"{key}:entitlement"
        if await self.cache.get_json(entitlement_key) is not None:
            raise FinnhubEntitlementError("This dataset is not available on the current plan")
        cached = await self.cache.get_json(key)
        if isinstance(cached, (dict, list)):
            return cached

        async with self.cache.lock(key):
            cached = await self.cache.get_json(key)
            if isinstance(cached, (dict, list)):
                return cached

            if not await self.limiter.allow("ratelimit:finnhub:rest", self.quota_per_minute):
                stale = await self._snapshot(key)
                if stale is not None:
                    return stale
                raise FinnhubRateLimitError("Request quota is temporarily exhausted")

            try:
                payload = await self.client.get(path, params)
            except FinnhubEntitlementError:
                await self.cache.set_json(entitlement_key, {"denied": True}, 300)
                raise
            except FinnhubError:
                stale = await self._snapshot(key)
                if stale is not None:
                    return stale
                raise

            await self.cache.set_json(key, payload, ttl)
            try:
                async with self.sessions() as session:
                    await upsert_snapshot(
                        session,
                        key,
                        payload,
                        datetime.now(UTC) + timedelta(seconds=ttl),
                    )
            except SQLAlchemyError:
                logger.exception("Provider snapshot persistence failed")
            return payload

    async def _snapshot(self, key: str) -> MarketPayload | None:
        try:
            async with self.sessions() as session:
                snapshot = await get_snapshot(session, key, allow_expired=True)
            return snapshot[0] if snapshot is not None else None
        except SQLAlchemyError:
            logger.exception("Provider snapshot fallback failed")
            return None
