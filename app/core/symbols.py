"""Curated market universe with public symbols and private upstream mappings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SymbolSpec:
    """Public `symbol` is what the API and frontend use."""

    symbol: str
    name: str
    asset_class: str  # equity | crypto | forex
    yfinance_symbol: str
    stream_symbol: str  # upstream live feed identifier
    stream: bool = True


# Keep stream count under the free live-feed ceiling (50).
CURATED_SYMBOLS: tuple[SymbolSpec, ...] = (
    # US equities
    SymbolSpec("AAPL", "Apple Inc.", "equity", "AAPL", "AAPL"),
    SymbolSpec("MSFT", "Microsoft Corporation", "equity", "MSFT", "MSFT"),
    SymbolSpec("GOOGL", "Alphabet Inc.", "equity", "GOOGL", "GOOGL"),
    SymbolSpec("AMZN", "Amazon.com Inc.", "equity", "AMZN", "AMZN"),
    SymbolSpec("NVDA", "NVIDIA Corporation", "equity", "NVDA", "NVDA"),
    SymbolSpec("META", "Meta Platforms Inc.", "equity", "META", "META"),
    SymbolSpec("TSLA", "Tesla Inc.", "equity", "TSLA", "TSLA"),
    SymbolSpec("AVGO", "Broadcom Inc.", "equity", "AVGO", "AVGO"),
    SymbolSpec("JPM", "JPMorgan Chase & Co.", "equity", "JPM", "JPM"),
    SymbolSpec("V", "Visa Inc.", "equity", "V", "V"),
    SymbolSpec("MA", "Mastercard Inc.", "equity", "MA", "MA"),
    SymbolSpec("JNJ", "Johnson & Johnson", "equity", "JNJ", "JNJ"),
    SymbolSpec("WMT", "Walmart Inc.", "equity", "WMT", "WMT"),
    SymbolSpec("XOM", "Exxon Mobil Corporation", "equity", "XOM", "XOM"),
    SymbolSpec("UNH", "UnitedHealth Group Inc.", "equity", "UNH", "UNH"),
    SymbolSpec("HD", "The Home Depot Inc.", "equity", "HD", "HD"),
    SymbolSpec("PG", "Procter & Gamble Co.", "equity", "PG", "PG"),
    SymbolSpec("COST", "Costco Wholesale Corporation", "equity", "COST", "COST"),
    SymbolSpec("NFLX", "Netflix Inc.", "equity", "NFLX", "NFLX"),
    SymbolSpec("AMD", "Advanced Micro Devices Inc.", "equity", "AMD", "AMD"),
    SymbolSpec("CRM", "Salesforce Inc.", "equity", "CRM", "CRM"),
    SymbolSpec("ORCL", "Oracle Corporation", "equity", "ORCL", "ORCL"),
    SymbolSpec("BAC", "Bank of America Corporation", "equity", "BAC", "BAC"),
    SymbolSpec("KO", "The Coca-Cola Company", "equity", "KO", "KO"),
    SymbolSpec("PEP", "PepsiCo Inc.", "equity", "PEP", "PEP"),
    SymbolSpec("DIS", "The Walt Disney Company", "equity", "DIS", "DIS"),
    SymbolSpec("INTC", "Intel Corporation", "equity", "INTC", "INTC"),
    SymbolSpec("CSCO", "Cisco Systems Inc.", "equity", "CSCO", "CSCO"),
    SymbolSpec("ADBE", "Adobe Inc.", "equity", "ADBE", "ADBE"),
    SymbolSpec("QCOM", "QUALCOMM Inc.", "equity", "QCOM", "QCOM"),
    # Crypto
    SymbolSpec("BTC-USD", "Bitcoin", "crypto", "BTC-USD", "BINANCE:BTCUSDT"),
    SymbolSpec("ETH-USD", "Ethereum", "crypto", "ETH-USD", "BINANCE:ETHUSDT"),
    SymbolSpec("SOL-USD", "Solana", "crypto", "SOL-USD", "BINANCE:SOLUSDT"),
    # FX majors (streamed live)
    SymbolSpec("EUR-USD", "Euro / US Dollar", "forex", "EURUSD=X", "OANDA:EUR_USD"),
    SymbolSpec("GBP-USD", "British Pound / US Dollar", "forex", "GBPUSD=X", "OANDA:GBP_USD"),
    SymbolSpec("USD-JPY", "US Dollar / Japanese Yen", "forex", "JPY=X", "OANDA:USD_JPY"),
    SymbolSpec("USD-CHF", "US Dollar / Swiss Franc", "forex", "CHF=X", "OANDA:USD_CHF"),
    SymbolSpec("AUD-USD", "Australian Dollar / US Dollar", "forex", "AUDUSD=X", "OANDA:AUD_USD"),
    SymbolSpec("USD-CAD", "US Dollar / Canadian Dollar", "forex", "CAD=X", "OANDA:USD_CAD"),
    SymbolSpec("NZD-USD", "New Zealand Dollar / US Dollar", "forex", "NZDUSD=X", "OANDA:NZD_USD"),
)

DEFAULT_STOCK_EXCHANGE = "US"
DEFAULT_CRYPTO_EXCHANGE = "binance"
DEFAULT_FOREX_EXCHANGE = "oanda"

# Full FX catalog for GET /forex/symbols (majors, crosses, metals, selected exotics).
FOREX_CATALOG: tuple[tuple[str, str], ...] = (
    ("EUR-USD", "Euro / US Dollar"),
    ("GBP-USD", "British Pound / US Dollar"),
    ("USD-JPY", "US Dollar / Japanese Yen"),
    ("USD-CHF", "US Dollar / Swiss Franc"),
    ("AUD-USD", "Australian Dollar / US Dollar"),
    ("USD-CAD", "US Dollar / Canadian Dollar"),
    ("NZD-USD", "New Zealand Dollar / US Dollar"),
    ("EUR-GBP", "Euro / British Pound"),
    ("EUR-JPY", "Euro / Japanese Yen"),
    ("EUR-CHF", "Euro / Swiss Franc"),
    ("EUR-AUD", "Euro / Australian Dollar"),
    ("EUR-CAD", "Euro / Canadian Dollar"),
    ("EUR-NZD", "Euro / New Zealand Dollar"),
    ("GBP-JPY", "British Pound / Japanese Yen"),
    ("GBP-CHF", "British Pound / Swiss Franc"),
    ("GBP-AUD", "British Pound / Australian Dollar"),
    ("GBP-CAD", "British Pound / Canadian Dollar"),
    ("GBP-NZD", "British Pound / New Zealand Dollar"),
    ("AUD-JPY", "Australian Dollar / Japanese Yen"),
    ("AUD-CHF", "Australian Dollar / Swiss Franc"),
    ("AUD-CAD", "Australian Dollar / Canadian Dollar"),
    ("AUD-NZD", "Australian Dollar / New Zealand Dollar"),
    ("CAD-JPY", "Canadian Dollar / Japanese Yen"),
    ("CAD-CHF", "Canadian Dollar / Swiss Franc"),
    ("NZD-JPY", "New Zealand Dollar / Japanese Yen"),
    ("NZD-CHF", "New Zealand Dollar / Swiss Franc"),
    ("CHF-JPY", "Swiss Franc / Japanese Yen"),
    ("USD-SEK", "US Dollar / Swedish Krona"),
    ("USD-NOK", "US Dollar / Norwegian Krone"),
    ("USD-DKK", "US Dollar / Danish Krone"),
    ("USD-SGD", "US Dollar / Singapore Dollar"),
    ("USD-HKD", "US Dollar / Hong Kong Dollar"),
    ("USD-CNH", "US Dollar / Chinese Yuan"),
    ("USD-MXN", "US Dollar / Mexican Peso"),
    ("USD-ZAR", "US Dollar / South African Rand"),
    ("USD-TRY", "US Dollar / Turkish Lira"),
    ("USD-INR", "US Dollar / Indian Rupee"),
    ("USD-PLN", "US Dollar / Polish Zloty"),
    ("EUR-SEK", "Euro / Swedish Krona"),
    ("EUR-NOK", "Euro / Norwegian Krone"),
    ("EUR-PLN", "Euro / Polish Zloty"),
    ("EUR-TRY", "Euro / Turkish Lira"),
    ("EUR-HUF", "Euro / Hungarian Forint"),
    ("EUR-CZK", "Euro / Czech Koruna"),
    ("GBP-SEK", "British Pound / Swedish Krona"),
    ("GBP-NOK", "British Pound / Norwegian Krone"),
    ("AUD-SGD", "Australian Dollar / Singapore Dollar"),
    ("NZD-SGD", "New Zealand Dollar / Singapore Dollar"),
    ("USD-THB", "US Dollar / Thai Baht"),
    ("XAU-USD", "Gold / US Dollar"),
    ("XAG-USD", "Silver / US Dollar"),
    ("XAU-EUR", "Gold / Euro"),
    ("XAU-GBP", "Gold / British Pound"),
    ("XAU-JPY", "Gold / Japanese Yen"),
    ("XAU-AUD", "Gold / Australian Dollar"),
    ("XAU-CAD", "Gold / Canadian Dollar"),
    ("XAU-CHF", "Gold / Swiss Franc"),
    ("XAG-EUR", "Silver / Euro"),
    ("XAG-GBP", "Silver / British Pound"),
    ("XAG-JPY", "Silver / Japanese Yen"),
    ("XAG-AUD", "Silver / Australian Dollar"),
)

_ALIAS_TO_PUBLIC: dict[str, str] = {}
for _spec in CURATED_SYMBOLS:
    _ALIAS_TO_PUBLIC[_spec.symbol.upper()] = _spec.symbol
    _ALIAS_TO_PUBLIC[_spec.stream_symbol.upper()] = _spec.symbol
    _ALIAS_TO_PUBLIC[_spec.yfinance_symbol.upper()] = _spec.symbol
for _symbol, _ in FOREX_CATALOG:
    _ALIAS_TO_PUBLIC[_symbol.upper()] = _symbol
    _ALIAS_TO_PUBLIC[_symbol.replace("-", "").upper()] = _symbol
    _ALIAS_TO_PUBLIC[_symbol.replace("-", "/").upper()] = _symbol
    _ALIAS_TO_PUBLIC[f"OANDA:{_symbol.replace('-', '_')}"] = _symbol

_ALIAS_TO_PUBLIC["BTCUSDT"] = "BTC-USD"
_ALIAS_TO_PUBLIC["ETHUSDT"] = "ETH-USD"
_ALIAS_TO_PUBLIC["SOLUSDT"] = "SOL-USD"
_ALIAS_TO_PUBLIC["BTCUSD"] = "BTC-USD"
_ALIAS_TO_PUBLIC["EURUSD"] = "EUR-USD"
_ALIAS_TO_PUBLIC["GBPUSD"] = "GBP-USD"


def curated_by_symbol() -> dict[str, SymbolSpec]:
    return {item.symbol: item for item in CURATED_SYMBOLS}


def curated_stream_symbols() -> tuple[str, ...]:
    """Public symbols that should be live-streamed."""
    return tuple(item.symbol for item in CURATED_SYMBOLS if item.stream)


def curated_upstream_stream_symbols() -> tuple[str, ...]:
    """Upstream feed identifiers for subscription."""
    return tuple(item.stream_symbol for item in CURATED_SYMBOLS if item.stream)


def normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper().replace(" ", "")
    if cleaned in _ALIAS_TO_PUBLIC:
        return _ALIAS_TO_PUBLIC[cleaned]
    if cleaned.startswith("OANDA:"):
        return cleaned.split(":", 1)[1].replace("_", "-")
    if cleaned.startswith("BINANCE:"):
        rest = cleaned.split(":", 1)[1]
        return _ALIAS_TO_PUBLIC.get(rest, rest)
    if "/" in cleaned:
        return cleaned.replace("/", "-")
    return cleaned


def resolve_spec(symbol: str) -> SymbolSpec | None:
    return curated_by_symbol().get(normalize_symbol(symbol))


def _yahoo_fx_symbol(public: str) -> str:
    parts = public.split("-")
    if len(parts) != 2:
        return public
    base, quote = parts
    if base == "USD":
        return f"{quote}=X"
    return f"{base}{quote}=X"


def yfinance_symbol_for(symbol: str) -> str:
    mapped = resolve_spec(symbol)
    if mapped is not None:
        return mapped.yfinance_symbol
    public = normalize_symbol(symbol)
    if "-" in public:
        return _yahoo_fx_symbol(public)
    return symbol


def stream_symbol_for(symbol: str) -> str:
    mapped = resolve_spec(symbol)
    if mapped is not None:
        return mapped.stream_symbol
    public = normalize_symbol(symbol)
    if "-" in public:
        return f"OANDA:{public.replace('-', '_')}"
    return symbol


def public_symbol_for(upstream_or_public: str) -> str:
    return normalize_symbol(upstream_or_public)


def symbols_by_asset_class(asset_class: str) -> tuple[SymbolSpec, ...]:
    return tuple(item for item in CURATED_SYMBOLS if item.asset_class == asset_class)


def forex_catalog_payload() -> list[dict[str, str]]:
    return [
        {
            "symbol": symbol,
            "name": name,
            "display_symbol": symbol.replace("-", "/"),
            "asset_class": "forex",
        }
        for symbol, name in FOREX_CATALOG
    ]


def sanitize_forex_upstream_list(payload: Any) -> list[dict[str, str]]:
    """Normalize a raw upstream FX symbol list into vendor-neutral public IDs."""
    if not isinstance(payload, list):
        return forex_catalog_payload()

    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw_symbol = str(item.get("symbol") or "")
        public = normalize_symbol(raw_symbol)
        if not public or "-" not in public or public in seen:
            continue
        seen.add(public)
        name = str(item.get("description") or item.get("displaySymbol") or public)
        for prefix in ("Oanda ", "OANDA ", "oanda "):
            if name.startswith(prefix):
                name = name[len(prefix) :]
                break
        display = str(item.get("displaySymbol") or public.replace("-", "/"))
        cleaned.append(
            {
                "symbol": public,
                "name": name,
                "display_symbol": display,
                "asset_class": "forex",
            }
        )
    cleaned.sort(key=lambda row: row["symbol"])
    return cleaned or forex_catalog_payload()
