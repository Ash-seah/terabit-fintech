"""Shared market-map tile metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketMapAsset:
    symbol: str
    name: str
    description: str
    sector: str
    market_cap: float  # relative weight / approx USD for tile sizing
    logo: str
