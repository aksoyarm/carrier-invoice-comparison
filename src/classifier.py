import io
import re
from dataclasses import dataclass

import pandas as pd

from src.utils import strip_whitespace


@dataclass
class ClassificationResult:
    carrier: str       # "UPS", "FedEx", "THY", "PTT", "Aramex", or "UNKNOWN"
    confidence: float  # 0.0 - 1.0
    method: str        # "header_keywords", "cell_a1_pattern", "tracking_regex", "column_count", "none"


HEADER_SIGNATURES = {
    "UPS":    ["Waybill", "Geçerli Ağırlık", "Fatura P.Birimi", "Fatura Tutarı"],
    "FedEx":  ["Billing Country/Territory", "Air Waybill Number", "Rated Weight Amount", "Dim Divisor"],
    "THY":    ["WDC CW", "Dağıtım Noktası", "Konsolide", "HS Code", "Tracking ID"],
    "PTT":    ["BARKOD NO", "GİDİŞ TÜRÜ", "VARIŞ ÜLKESİ", "FATURA NAVLUN"],
    "Aramex": ["Airway Bill No.", "Chargeable Weight", "Pick up Date", "AR Exchange Rate"],
}

TRACKING_PATTERNS = {
    "UPS":    r"^1Z[A-Z0-9]{16,}",
    "FedEx":  r"^\d{12,15}$",
    "THY":    r"^33Q6R5\d+",
    "PTT":    r"^RE\d{9}TR$",
    "Aramex": r"^\d{11}$",
}

# Ordered for first-match-wins in overlapping ranges
COLUMN_COUNT_RANGES = [
    ("FedEx", 81, 9999),
    ("THY", 18, 25),
    ("Aramex", 15, 22),
    ("UPS", 10, 15),
    ("PTT", 8, 12),
]


def classify_carrier(file_bytes: bytes) -> ClassificationResult:
    """Classify which carrier an invoice belongs to using a 4-layer cascade."""
    # Read raw data (no headers) — limited rows for efficiency
    df_small = pd.read_excel(
        io.BytesIO(file_bytes), header=None, nrows=10, engine="openpyxl"
    )

    # Layer 1: Header keyword matching
    result = _layer1_header_keywords(df_small)
    if result:
        return result

    # Layer 2: Cell A1 pattern
    result = _layer2_cell_a1(df_small)
    if result:
        return result

    # Layer 3: Tracking number regex
    result = _layer3_tracking_regex(df_small)
    if result:
        return result

    # Layer 4: Column count — needs full column set
    df_full = pd.read_excel(
        io.BytesIO(file_bytes), header=None, nrows=1, engine="openpyxl"
    )
    result = _layer4_column_count(df_full)
    if result:
        return result

    return ClassificationResult("UNKNOWN", 0.0, "none")


def _layer1_header_keywords(df: pd.DataFrame) -> ClassificationResult | None:
    """Scan rows 0-1 for header keywords. Best score >= 0.5 wins."""
    # Collect all cell values from rows 0-1 as stripped lowercase strings
    cell_values = set()
    for row_idx in range(min(2, len(df))):
        for val in df.iloc[row_idx]:
            if pd.notna(val):
                cell_values.add(str(strip_whitespace(str(val))).lower())

    best_carrier = None
    best_score = 0.0

    for carrier, keywords in HEADER_SIGNATURES.items():
        matched = sum(1 for kw in keywords if kw.lower() in cell_values)
        score = matched / len(keywords)
        if score > best_score:
            best_score = score
            best_carrier = carrier

    if best_score >= 0.5 and best_carrier:
        return ClassificationResult(best_carrier, best_score, "header_keywords")
    return None


def _layer2_cell_a1(df: pd.DataFrame) -> ClassificationResult | None:
    """Check if cell A1 starts with 'Fatura Detay UPY' -> UPS."""
    if len(df) == 0 or len(df.columns) == 0:
        return None
    val = df.iloc[0, 0]
    if pd.notna(val) and str(val).strip().lower().startswith("fatura detay upy"):
        return ClassificationResult("UPS", 0.8, "cell_a1_pattern")
    return None


def _layer3_tracking_regex(df: pd.DataFrame) -> ClassificationResult | None:
    """Match first tracking value against carrier regex patterns."""
    # Sample first non-null value from columns A and B, starting from row 2
    sample_value = None
    for col_idx in [0, 1]:
        if col_idx >= len(df.columns):
            continue
        for row_idx in range(2, len(df)):
            val = df.iloc[row_idx, col_idx]
            if pd.notna(val):
                sample_value = str(val).strip()
                break
        if sample_value:
            break

    if not sample_value:
        return None

    matches = []
    for carrier, pattern in TRACKING_PATTERNS.items():
        if re.match(pattern, sample_value):
            matches.append(carrier)

    if len(matches) == 1:
        return ClassificationResult(matches[0], 0.7, "tracking_regex")
    return None


def _layer4_column_count(df: pd.DataFrame) -> ClassificationResult | None:
    """Classify by column count. First matching range wins."""
    col_count = len(df.columns)
    for carrier, min_cols, max_cols in COLUMN_COUNT_RANGES:
        if min_cols <= col_count <= max_cols:
            return ClassificationResult(carrier, 0.3, "column_count")
    return None
