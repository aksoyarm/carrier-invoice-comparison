import io

import pandas as pd

from src.utils import find_column, parse_turkish_number, strip_whitespace


# (header_name, fallback_column_letter)
COLUMN_MAPPINGS = {
    "UPS": {
        "waybill": ("Waybill", "A"),
        "weight":  ("Geçerli Ağırlık", "D"),
        "price":   ("Tutar", "J"),
    },
    "FedEx": {
        "waybill": ("Air Waybill Number", "Q"),
        "weight":  ("Rated Weight Amount", "BK"),
        "price":   ("Air Waybill Total Amount", "BN"),
    },
    "THY": {
        "waybill":     ("Tracking ID", "B"),
        "weight":      ("WDC CW", "H"),
        "price":       ("Tahsil Edilecek Tutar", "P"),
        "destination": ("Dest. Country", "F"),
    },
    "PTT": {
        "waybill": ("BARKOD NO", "B"),
        "weight":  ("AĞIRLIK", "G"),
        "price":   ("FATURA NAVLUN", "I"),
    },
    "Aramex": {
        "waybill": ("Airway Bill No.", "A"),
        "weight":  ("Chargeable Weight", "I"),
        "price":   ("Net Value", "L"),
    },
}

HEADER_ROW_OVERRIDE = {
    "UPS": 1,  # 0-indexed; UPS headers are in Excel Row 2
}

REQUIRED_FIELDS = {"waybill", "weight", "price"}


def parse_invoice(file_bytes: bytes, carrier: str) -> pd.DataFrame:
    """Parse a carrier invoice Excel file and return a standardized DataFrame."""
    if carrier not in COLUMN_MAPPINGS:
        raise ValueError(f"Unknown carrier: {carrier}")

    header_row = HEADER_ROW_OVERRIDE.get(carrier, 0)
    df = pd.read_excel(
        io.BytesIO(file_bytes), header=header_row, engine="openpyxl"
    )

    # Strip whitespace from column names
    df.columns = [str(c).strip() for c in df.columns]

    # Resolve columns
    mapping = COLUMN_MAPPINGS[carrier]
    resolved = _resolve_columns(df, mapping)

    # Build output DataFrame
    out = pd.DataFrame()
    out["waybill"] = df[resolved["waybill"]].apply(
        lambda v: strip_whitespace(str(v).strip()) if pd.notna(v) else None
    )
    out["weight_raw"] = df[resolved["weight"]].apply(parse_turkish_number)
    out["price_raw"] = df[resolved["price"]].apply(parse_turkish_number)

    if "destination" in resolved:
        out["destination"] = df[resolved["destination"]].apply(
            lambda v: strip_whitespace(str(v)) if pd.notna(v) else None
        )

    # Drop rows with null/empty waybill
    out = out[out["waybill"].notna() & (out["waybill"] != "") & (out["waybill"] != "None")]
    out = out.reset_index(drop=True)

    return out


def _resolve_columns(df: pd.DataFrame, mapping: dict) -> dict:
    """Resolve each field to an actual DataFrame column name."""
    resolved = {}
    for field, (header_name, fallback_letter) in mapping.items():
        col = find_column(df, header_name, fallback_letter)
        if col is None and field in REQUIRED_FIELDS:
            raise ValueError(
                f"Could not resolve required column '{field}' "
                f"(header: '{header_name}', fallback: '{fallback_letter}')"
            )
        if col is not None:
            resolved[field] = col
    return resolved
