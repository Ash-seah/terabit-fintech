"""Public logo URLs for equities, crypto, and FX."""

from __future__ import annotations

from app.core.catalogs import CRYPTO_CATALOG, STOCK_CATALOG
from app.core.symbols import FOREX_CATALOG, normalize_symbol

_STOCK_NAMES = {symbol: name for symbol, name in STOCK_CATALOG}
_CRYPTO_NAMES = {symbol: name for symbol, name in CRYPTO_CATALOG}
_FOREX_NAMES = {symbol: name for symbol, name in FOREX_CATALOG}

_CRYPTO_ICON = (
    "https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/{slug}.png"
)
_FLAG = "https://flagcdn.com/w80/{code}.png"
_EQUITY_LOGO = "https://assets.parqet.com/logos/symbol/{symbol}"

_FX_FLAG: dict[str, str] = {
    "EUR": "eu",
    "GBP": "gb",
    "USD": "us",
    "JPY": "jp",
    "CHF": "ch",
    "AUD": "au",
    "CAD": "ca",
    "NZD": "nz",
    "SEK": "se",
    "NOK": "no",
    "DKK": "dk",
    "SGD": "sg",
    "HKD": "hk",
    "CNH": "cn",
    "MXN": "mx",
    "ZAR": "za",
    "TRY": "tr",
    "INR": "in",
    "PLN": "pl",
    "HUF": "hu",
    "CZK": "cz",
    "THB": "th",
}


def logo_url_for(symbol: str) -> str:
    public = normalize_symbol(symbol)
    if public in _CRYPTO_NAMES:
        slug = public.split("-", 1)[0].lower()
        if slug == "pol":
            slug = "matic"
        return _CRYPTO_ICON.format(slug=slug)
    if public in _FOREX_NAMES or ("-" in public and len(public.split("-")) == 2):
        base = public.split("-", 1)[0]
        if base in {"XAU", "XAG"}:
            return _EQUITY_LOGO.format(symbol=public.replace("-", ""))
        code = _FX_FLAG.get(base, base[:2].lower())
        return _FLAG.format(code=code)
    tidy = public.replace("-", ".")
    return _EQUITY_LOGO.format(symbol=tidy)


def display_name_for(symbol: str) -> str | None:
    public = normalize_symbol(symbol)
    return _STOCK_NAMES.get(public) or _CRYPTO_NAMES.get(public) or _FOREX_NAMES.get(public)


def peer_card(symbol: str) -> dict[str, str]:
    public = normalize_symbol(symbol)
    card = {"symbol": public, "logo": logo_url_for(public)}
    name = display_name_for(public)
    if name:
        card["name"] = name
    return card
