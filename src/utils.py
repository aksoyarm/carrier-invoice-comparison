import math
import re

import pandas as pd


def parse_turkish_number(value) -> float | None:
    """Convert a value to float, handling Turkish locale formatting (dot=thousands, comma=decimal)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return float(value)
    if not isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    s = value.strip()
    # Remove currency symbols and whitespace
    s = re.sub(r'[^\d.,-]', '', s)
    if not s:
        return None

    has_dot = '.' in s
    has_comma = ',' in s

    try:
        if has_dot and has_comma:
            # Determine format by which separator comes last
            last_dot = s.rfind('.')
            last_comma = s.rfind(',')
            if last_comma > last_dot:
                # Turkish format: 1.004,12 -> comma is decimal
                s = s.replace('.', '').replace(',', '.')
            else:
                # English format: 1,234.56 -> dot is decimal
                s = s.replace(',', '')
        elif has_comma:
            # Comma as decimal: 3,5 -> 3.5
            s = s.replace(',', '.')
        # else: standard decimal or integer
        return float(s)
    except ValueError:
        return None


def round_up(value: float, interval: float) -> float:
    """Round value UP to the next multiple of interval. Exact multiples stay unchanged."""
    if value == 0:
        return 0.0
    remainder = value % interval
    if remainder < 1e-9 or (interval - remainder) < 1e-9:
        # Value is already (effectively) an exact multiple
        return round(value, 10)
    return round(math.ceil(value / interval) * interval, 10)


def strip_whitespace(value):
    """Strip leading/trailing whitespace from strings. Pass through non-strings."""
    if isinstance(value, str):
        return value.strip()
    return value


def col_letter_to_index(letter: str) -> int:
    """Convert Excel column letter(s) to 0-based index. 'A'->0, 'Z'->25, 'AA'->26, 'BK'->62."""
    letter = letter.upper()
    index = 0
    for ch in letter:
        index = index * 26 + (ord(ch) - ord('A') + 1)
    return index - 1


def find_column(df: pd.DataFrame, header_name: str, fallback_col_letter: str) -> str | None:
    """Resolve a column by header name (case-insensitive), then by fallback column letter index."""
    header_lower = header_name.lower().strip()
    columns = df.columns.tolist()

    # Step 1: exact match (case-insensitive, stripped)
    for col in columns:
        if str(col).strip().lower() == header_lower:
            return col

    # Step 2: substring containment (case-insensitive)
    for col in columns:
        if header_lower in str(col).strip().lower():
            return col

    # Step 3: fallback to positional index
    idx = col_letter_to_index(fallback_col_letter)
    if idx < len(columns):
        return columns[idx]

    return None


# Country alias mappings
_COUNTRY_ALIASES = {}
_US_NAMES = ["US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA", "AMERIKA", "AMERİKA"]
_GB_NAMES = ["GB", "UK", "UNITED KINGDOM", "GREAT BRITAIN", "İNGİLTERE", "INGILTERE"]
_AU_NAMES = ["AU", "AUSTRALIA", "AVUSTRALYA"]

for name in _US_NAMES:
    _COUNTRY_ALIASES[name] = "US"
for name in _GB_NAMES:
    _COUNTRY_ALIASES[name] = "GB"
for name in _AU_NAMES:
    _COUNTRY_ALIASES[name] = "AU"


def normalize_country(country: str) -> str:
    """Normalize country strings to canonical codes (US, GB, AU). Returns uppercased original if no alias."""
    if not isinstance(country, str):
        return str(country).upper() if country is not None else ""
    return _COUNTRY_ALIASES.get(country.strip().upper(), country.strip().upper())
