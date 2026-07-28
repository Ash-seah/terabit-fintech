"""Forex market-map tiles (majors, crosses, exotics, metals)."""

from __future__ import annotations

from app.core.marketmap_common import MarketMapAsset

_FLAG = "https://flagcdn.com/w80/{code}.png"
_METAL = "https://assets.parqet.com/logos/symbol/{symbol}"


def _flag(code: str) -> str:
    return _FLAG.format(code=code)


def _fx(
    symbol: str,
    name: str,
    description: str,
    sector: str,
    weight: float,
    flag_code: str,
) -> MarketMapAsset:
    logo = _METAL.format(symbol=symbol.replace("-", "")) if flag_code in {"xau", "xag"} else _flag(flag_code)
    return MarketMapAsset(symbol, name, description, sector, weight, logo)


# weight ≈ relative global turnover / importance for tile sizing
MARKETMAP_FOREX: tuple[MarketMapAsset, ...] = (
    # Majors
    _fx("EUR-USD", "EUR/USD", "Euro vs US dollar — the world’s most traded pair.", "Majors", 1.5e12, "eu"),
    _fx("GBP-USD", "GBP/USD", "British pound vs US dollar (Cable).", "Majors", 5.0e11, "gb"),
    _fx("USD-JPY", "USD/JPY", "US dollar vs Japanese yen.", "Majors", 6.0e11, "jp"),
    _fx("USD-CHF", "USD/CHF", "US dollar vs Swiss franc.", "Majors", 1.5e11, "ch"),
    _fx("AUD-USD", "AUD/USD", "Australian dollar vs US dollar.", "Majors", 2.0e11, "au"),
    _fx("USD-CAD", "USD/CAD", "US dollar vs Canadian dollar.", "Majors", 1.8e11, "ca"),
    _fx("NZD-USD", "NZD/USD", "New Zealand dollar vs US dollar.", "Majors", 8.0e10, "nz"),
    # Metals
    _fx("XAU-USD", "Gold", "Spot gold priced in US dollars.", "Metals", 4.0e11, "xau"),
    _fx("XAG-USD", "Silver", "Spot silver priced in US dollars.", "Metals", 8.0e10, "xag"),
    _fx("XAU-EUR", "Gold/EUR", "Spot gold priced in euros.", "Metals", 6.0e10, "xau"),
    _fx("XAU-GBP", "Gold/GBP", "Spot gold priced in pounds.", "Metals", 4.0e10, "xau"),
    _fx("XAU-JPY", "Gold/JPY", "Spot gold priced in yen.", "Metals", 3.5e10, "xau"),
    _fx("XAU-AUD", "Gold/AUD", "Spot gold priced in Australian dollars.", "Metals", 3.0e10, "xau"),
    _fx("XAU-CAD", "Gold/CAD", "Spot gold priced in Canadian dollars.", "Metals", 2.5e10, "xau"),
    _fx("XAU-CHF", "Gold/CHF", "Spot gold priced in Swiss francs.", "Metals", 2.5e10, "xau"),
    _fx("XAG-EUR", "Silver/EUR", "Spot silver priced in euros.", "Metals", 1.5e10, "xag"),
    _fx("XAG-GBP", "Silver/GBP", "Spot silver priced in pounds.", "Metals", 1.2e10, "xag"),
    _fx("XAG-JPY", "Silver/JPY", "Spot silver priced in yen.", "Metals", 1.0e10, "xag"),
    _fx("XAG-AUD", "Silver/AUD", "Spot silver priced in Australian dollars.", "Metals", 9.0e9, "xag"),
    # Minor crosses
    _fx("EUR-GBP", "EUR/GBP", "Euro vs British pound.", "Minor Crosses", 1.2e11, "eu"),
    _fx("EUR-JPY", "EUR/JPY", "Euro vs Japanese yen.", "Minor Crosses", 1.4e11, "eu"),
    _fx("EUR-CHF", "EUR/CHF", "Euro vs Swiss franc.", "Minor Crosses", 7.0e10, "eu"),
    _fx("EUR-AUD", "EUR/AUD", "Euro vs Australian dollar.", "Minor Crosses", 5.0e10, "eu"),
    _fx("EUR-CAD", "EUR/CAD", "Euro vs Canadian dollar.", "Minor Crosses", 4.5e10, "eu"),
    _fx("EUR-NZD", "EUR/NZD", "Euro vs New Zealand dollar.", "Minor Crosses", 2.5e10, "eu"),
    _fx("GBP-JPY", "GBP/JPY", "Pound vs yen — high-volatility cross.", "Minor Crosses", 9.0e10, "gb"),
    _fx("GBP-CHF", "GBP/CHF", "Pound vs Swiss franc.", "Minor Crosses", 3.5e10, "gb"),
    _fx("GBP-AUD", "GBP/AUD", "Pound vs Australian dollar.", "Minor Crosses", 3.0e10, "gb"),
    _fx("GBP-CAD", "GBP/CAD", "Pound vs Canadian dollar.", "Minor Crosses", 2.8e10, "gb"),
    _fx("GBP-NZD", "GBP/NZD", "Pound vs New Zealand dollar.", "Minor Crosses", 1.8e10, "gb"),
    _fx("AUD-JPY", "AUD/JPY", "Australian dollar vs yen.", "Minor Crosses", 6.0e10, "au"),
    _fx("AUD-CHF", "AUD/CHF", "Australian dollar vs Swiss franc.", "Minor Crosses", 2.0e10, "au"),
    _fx("AUD-CAD", "AUD/CAD", "Australian dollar vs Canadian dollar.", "Minor Crosses", 2.2e10, "au"),
    _fx("AUD-NZD", "AUD/NZD", "Australian vs New Zealand dollar.", "Minor Crosses", 2.0e10, "au"),
    _fx("CAD-JPY", "CAD/JPY", "Canadian dollar vs yen.", "Minor Crosses", 3.5e10, "ca"),
    _fx("CAD-CHF", "CAD/CHF", "Canadian dollar vs Swiss franc.", "Minor Crosses", 1.5e10, "ca"),
    _fx("NZD-JPY", "NZD/JPY", "New Zealand dollar vs yen.", "Minor Crosses", 2.5e10, "nz"),
    _fx("NZD-CHF", "NZD/CHF", "New Zealand dollar vs Swiss franc.", "Minor Crosses", 1.2e10, "nz"),
    _fx("CHF-JPY", "CHF/JPY", "Swiss franc vs yen.", "Minor Crosses", 3.0e10, "ch"),
    # Exotics
    _fx("USD-SEK", "USD/SEK", "US dollar vs Swedish krona.", "Exotics", 4.0e10, "se"),
    _fx("USD-NOK", "USD/NOK", "US dollar vs Norwegian krone.", "Exotics", 3.5e10, "no"),
    _fx("USD-DKK", "USD/DKK", "US dollar vs Danish krone.", "Exotics", 2.5e10, "dk"),
    _fx("USD-SGD", "USD/SGD", "US dollar vs Singapore dollar.", "Exotics", 5.0e10, "sg"),
    _fx("USD-HKD", "USD/HKD", "US dollar vs Hong Kong dollar.", "Exotics", 6.0e10, "hk"),
    _fx("USD-CNH", "USD/CNH", "US dollar vs offshore Chinese yuan.", "Exotics", 1.0e11, "cn"),
    _fx("USD-MXN", "USD/MXN", "US dollar vs Mexican peso.", "Exotics", 7.0e10, "mx"),
    _fx("USD-ZAR", "USD/ZAR", "US dollar vs South African rand.", "Exotics", 3.0e10, "za"),
    _fx("USD-TRY", "USD/TRY", "US dollar vs Turkish lira.", "Exotics", 4.5e10, "tr"),
    _fx("USD-INR", "USD/INR", "US dollar vs Indian rupee.", "Exotics", 5.5e10, "in"),
    _fx("USD-PLN", "USD/PLN", "US dollar vs Polish zloty.", "Exotics", 3.0e10, "pl"),
    _fx("USD-THB", "USD/THB", "US dollar vs Thai baht.", "Exotics", 2.0e10, "th"),
    _fx("EUR-SEK", "EUR/SEK", "Euro vs Swedish krona.", "Exotics", 2.5e10, "se"),
    _fx("EUR-NOK", "EUR/NOK", "Euro vs Norwegian krone.", "Exotics", 2.2e10, "no"),
    _fx("EUR-PLN", "EUR/PLN", "Euro vs Polish zloty.", "Exotics", 2.8e10, "pl"),
    _fx("EUR-TRY", "EUR/TRY", "Euro vs Turkish lira.", "Exotics", 2.0e10, "tr"),
    _fx("EUR-HUF", "EUR/HUF", "Euro vs Hungarian forint.", "Exotics", 1.5e10, "hu"),
    _fx("EUR-CZK", "EUR/CZK", "Euro vs Czech koruna.", "Exotics", 1.4e10, "cz"),
    _fx("GBP-SEK", "GBP/SEK", "Pound vs Swedish krona.", "Exotics", 1.2e10, "se"),
    _fx("GBP-NOK", "GBP/NOK", "Pound vs Norwegian krone.", "Exotics", 1.1e10, "no"),
    _fx("AUD-SGD", "AUD/SGD", "Australian dollar vs Singapore dollar.", "Exotics", 1.0e10, "sg"),
    _fx("NZD-SGD", "NZD/SGD", "New Zealand dollar vs Singapore dollar.", "Exotics", 8.0e9, "sg"),
)


def marketmap_forex() -> tuple[MarketMapAsset, ...]:
    return MARKETMAP_FOREX
