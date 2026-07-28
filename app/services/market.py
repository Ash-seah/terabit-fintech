import hashlib
import json
import logging
import time
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
    """Finnhub REST access with soft TTL + long Redis retention to minimize quota use."""

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
        retention = max(ttl * 12, 86_400)

        if await self.cache.get_json(entitlement_key) is not None:
            raise FinnhubEntitlementError("This dataset is not available on the current plan")

        cached = await self.cache.get_json(key)
        if isinstance(cached, dict) and "payload" in cached and "fetched_at" in cached:
            age = time.time() - float(cached["fetched_at"])
            payload = cached["payload"]
            if isinstance(payload, (dict, list)) and age <= ttl:
                return payload
            # Soft-expired: serve stale immediately and only refresh under lock/quota.
            if isinstance(payload, (dict, list)) and age <= retention:
                refreshed = await self._try_refresh(key, path, params, ttl, retention)
                return refreshed if refreshed is not None else payload

        async with self.cache.lock(key) as acquired:
            cached = await self.cache.get_json(key)
            if isinstance(cached, dict) and "payload" in cached and "fetched_at" in cached:
                age = time.time() - float(cached["fetched_at"])
                payload = cached["payload"]
                if isinstance(payload, (dict, list)) and age <= ttl:
                    return payload

            if not acquired:
                stale = await self._stale_payload(key)
                if stale is not None:
                    return stale
                raise FinnhubRateLimitError("Request quota is temporarily exhausted")

            if not await self.limiter.allow("ratelimit:finnhub:rest", self.quota_per_minute):
                stale = await self._stale_payload(key)
                if stale is not None:
                    return stale
                raise FinnhubRateLimitError("Request quota is temporarily exhausted")

            try:
                payload = await self.client.get(path, params)
            except FinnhubEntitlementError:
                await self.cache.set_json(entitlement_key, {"denied": True}, 86_400)
                raise
            except FinnhubError:
                stale = await self._stale_payload(key)
                if stale is not None:
                    return stale
                raise

            await self._store(key, payload, ttl, retention)
            return payload

    async def _try_refresh(
        self,
        key: str,
        path: str,
        params: dict[str, Any],
        ttl: int,
        retention: int,
    ) -> MarketPayload | None:
        async with self.cache.lock(key, lock_ttl=5, blocking_timeout=0.05) as acquired:
            if not acquired:
                return None
            cached = await self.cache.get_json(key)
            if isinstance(cached, dict) and "payload" in cached and "fetched_at" in cached:
                age = time.time() - float(cached["fetched_at"])
                payload = cached["payload"]
                if isinstance(payload, (dict, list)) and age <= ttl:
                    return payload
            if not await self.limiter.allow("ratelimit:finnhub:rest", self.quota_per_minute):
                return None
            try:
                payload = await self.client.get(path, params)
            except FinnhubError:
                return None
            await self._store(key, payload, ttl, retention)
            return payload

    async def _store(
        self,
        key: str,
        payload: MarketPayload,
        ttl: int,
        retention: int,
    ) -> None:
        envelope = {"payload": payload, "fetched_at": time.time()}
        await self.cache.set_json(key, envelope, retention)
        try:
            async with self.sessions() as session:
                await upsert_snapshot(
                    session,
                    key,
                    payload,
                    datetime.now(UTC) + timedelta(seconds=max(ttl, retention)),
                )
        except SQLAlchemyError:
            logger.exception("Provider snapshot persistence failed")

    async def _stale_payload(self, key: str) -> MarketPayload | None:
        cached = await self.cache.get_json(key)
        payload = cached.get("payload") if isinstance(cached, dict) else None
        if isinstance(payload, (dict, list)):
            return payload
        try:
            async with self.sessions() as session:
                snapshot = await get_snapshot(session, key, allow_expired=True)
            if snapshot is None:
                return None
            data = snapshot[0]
            return data if isinstance(data, (dict, list)) else None
        except SQLAlchemyError:
            logger.exception("Provider snapshot fallback failed")
            return None
