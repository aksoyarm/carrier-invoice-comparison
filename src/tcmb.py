"""TCMB (Central Bank of Turkey) exchange rate fetcher.

Fetches Forex Selling (Döviz Satış) rates from the public TCMB XML API.
URL pattern: https://www.tcmb.gov.tr/kurlar/{YYYYMM}/{DDMMYYYY}.xml
"""

import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

# Cache: date string "YYYY-MM-DD" -> {currency_code: forex_selling_rate}
_rate_cache: dict[str, dict[str, float]] = {}


def fetch_tcmb_rate(date: datetime.date, currency: str) -> float | None:
    """Fetch the TCMB Forex Selling rate for a given date and currency.

    Returns 1.0 for TRY/TL (base currency, no API call needed).
    Returns None on error or if the currency is not found.
    """
    currency = currency.strip().upper()
    if currency in ("TRY", "TL"):
        return 1.0

    date_key = date.isoformat()

    if date_key not in _rate_cache:
        _rate_cache[date_key] = _fetch_rates_for_date(date)

    return _rate_cache[date_key].get(currency)


def _fetch_rates_for_date(target_date: datetime.date) -> dict[str, float]:
    """Fetch all currency rates for target_date, falling back up to 7 days for weekends/holidays."""
    candidate = target_date
    for _ in range(7):
        url = (
            f"https://www.tcmb.gov.tr/kurlar/"
            f"{candidate.strftime('%Y%m')}/{candidate.strftime('%d%m%Y')}.xml"
        )
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return _parse_rates_xml(response.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                candidate -= datetime.timedelta(days=1)
                continue
            return {}
        except (urllib.error.URLError, OSError, TimeoutError):
            return {}
    return {}


def _parse_rates_xml(xml_bytes: bytes) -> dict[str, float]:
    """Parse TCMB XML response and extract ForexSelling rates for all currencies."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}

    rates = {}
    for currency_el in root.findall("Currency"):
        code = currency_el.get("CurrencyCode")
        if not code:
            continue
        selling_el = currency_el.find("ForexSelling")
        if selling_el is None or not selling_el.text:
            continue
        try:
            rates[code] = float(selling_el.text)
        except ValueError:
            continue
    return rates


def clear_cache() -> None:
    """Clear the in-memory rate cache."""
    _rate_cache.clear()
