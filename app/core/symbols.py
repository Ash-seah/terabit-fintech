"""Curated market universe used by the frontend overview and live stream."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SymbolSpec:
    symbol: str
    name: str
    asset_class: str
    yfinance_symbol: str
    stream: bool = True


# Liquid US equities + one crypto pair. Free Finnhub WS allows up to 50 symbols.
CURATED_SYMBOLS: tuple[SymbolSpec, ...] = (
    SymbolSpec("AAPL", "Apple Inc.", "equity", "AAPL"),
    SymbolSpec("MSFT", "Microsoft Corporation", "equity", "MSFT"),
    SymbolSpec("GOOGL", "Alphabet Inc.", "equity", "GOOGL"),
    SymbolSpec("AMZN", "Amazon.com Inc.", "equity", "AMZN"),
    SymbolSpec("NVDA", "NVIDIA Corporation", "equity", "NVDA"),
    SymbolSpec("META", "Meta Platforms Inc.", "equity", "META"),
    SymbolSpec("TSLA", "Tesla Inc.", "equity", "TSLA"),
    SymbolSpec("JPM", "JPMorgan Chase & Co.", "equity", "JPM"),
    SymbolSpec("V", "Visa Inc.", "equity", "V"),
    SymbolSpec("JNJ", "Johnson & Johnson", "equity", "JNJ"),
    SymbolSpec("BINANCE:BTCUSDT", "Bitcoin / Tether", "crypto", "BTC-USD"),
)

DEFAULT_STOCK_EXCHANGE = "US"
DEFAULT_CRYPTO_EXCHANGE = "binance"
DEFAULT_FOREX_EXCHANGE = "oanda"


def curated_by_symbol() -> dict[str, SymbolSpec]:
    return {item.symbol: item for item in CURATED_SYMBOLS}


def curated_stream_symbols() -> tuple[str, ...]:
    return tuple(item.symbol for item in CURATED_SYMBOLS if item.stream)


def yfinance_symbol_for(symbol: str) -> str:
    mapped = curated_by_symbol().get(symbol.upper())
    return mapped.yfinance_symbol if mapped is not None else symbol
