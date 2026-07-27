import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FinnhubError(Exception):
    code = "finnhub_error"


class FinnhubRateLimitError(FinnhubError):
    code = "provider_rate_limited"


class FinnhubEntitlementError(FinnhubError):
    code = "provider_entitlement_required"


class FinnhubUnavailableError(FinnhubError):
    code = "provider_unavailable"


class FinnhubClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Finnhub-Token": api_key, "User-Agent": "financial-data-backend/0.1"},
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | list[Any]:
        for attempt in range(3):
            try:
                response = await self.client.get(path, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise FinnhubUnavailableError("Finnhub is unreachable") from exc
                await asyncio.sleep(0.5 * (2**attempt))
                continue

            if response.status_code == 429:
                raise FinnhubRateLimitError("Finnhub request quota is exhausted")
            if response.status_code in {401, 403}:
                raise FinnhubEntitlementError(
                    "This Finnhub account is not entitled to this dataset"
                )
            if response.status_code >= 500:
                if attempt == 2:
                    raise FinnhubUnavailableError("Finnhub returned a server error")
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise FinnhubUnavailableError("Finnhub returned an invalid response") from exc
            if isinstance(payload, dict) and payload.get("error"):
                message = str(payload["error"])
                if "access" in message.lower() or "premium" in message.lower():
                    raise FinnhubEntitlementError(
                        "This Finnhub account is not entitled to this dataset"
                    )
                raise FinnhubUnavailableError(message)
            if not isinstance(payload, (dict, list)):
                raise FinnhubUnavailableError("Finnhub returned an unexpected payload")
            return payload
        raise FinnhubUnavailableError("Finnhub request failed")

    async def close(self) -> None:
        await self.client.aclose()
