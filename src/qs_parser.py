import io

import pandas as pd

from src.utils import find_column, parse_turkish_number, strip_whitespace


QS_COLUMN_MAPPINGS = {
    "qs_waybill":        ("Konşimento", "B"),
    "qs_customer":       ("Müşteri", "O"),
    "qs_service":        ("Servis", "Y"),
    "qs_weight_raw":     ("Fatura Ağırlığı", "AC"),
    "qs_cust_price_ccy": ("Gönderi Bedeli Döviz Cinsi", "AA"),
    "qs_cust_price":     ("Gönderi Bedeli", "AB"),
    "qs_ship_cost_ccy":  ("Sevkiyat Bedeli Döviz Cinsi", "AD"),
    "qs_ship_cost":      ("Sevkiyat Bedeli", "AE"),
    "qs_ddp_cost":       ("ddp_bedeli", "AF"),
    "qs_ship_cost_rate": ("Sevkiyat Bedeli Kuru", "AG"),
    "qs_ship_cost_tl":   ("Sevkiyat Bedeli TL", "AH"),
    "qs_carrier":        ("Taşıyıcı", "X"),
}

NUMERIC_COLUMNS = {"qs_weight_raw", "qs_cust_price", "qs_ship_cost", "qs_ddp_cost", "qs_ship_cost_rate", "qs_ship_cost_tl"}
STRING_COLUMNS = {"qs_waybill", "qs_customer", "qs_service", "qs_cust_price_ccy", "qs_ship_cost_ccy", "qs_carrier"}


def parse_quicksight(file_bytes: bytes) -> pd.DataFrame:
    """Parse the QuickSight export Excel file."""
    # Detect header row by reading raw first
    df_raw = pd.read_excel(
        io.BytesIO(file_bytes), header=None, nrows=5, engine="openpyxl"
    )

    header_row = _detect_header_row(df_raw)

    df = pd.read_excel(
        io.BytesIO(file_bytes), header=header_row, engine="openpyxl"
    )

    # Strip whitespace from column names
    df.columns = [str(c).strip() for c in df.columns]

    # Resolve columns
    resolved = {}
    for std_name, (header_name, fallback_letter) in QS_COLUMN_MAPPINGS.items():
        col = find_column(df, header_name, fallback_letter)
        if col is None:
            raise ValueError(
                f"Could not resolve QS column '{std_name}' "
                f"(header: '{header_name}', fallback: '{fallback_letter}')"
            )
        resolved[std_name] = col

    # Build output DataFrame
    out = pd.DataFrame()
    for std_name, actual_col in resolved.items():
        if std_name in NUMERIC_COLUMNS:
            out[std_name] = df[actual_col].apply(parse_turkish_number)
        elif std_name in STRING_COLUMNS:
            out[std_name] = df[actual_col].apply(
                lambda v: strip_whitespace(str(v)) if pd.notna(v) else None
            )
        else:
            out[std_name] = df[actual_col]

    # Cast waybill to string
    out["qs_waybill"] = out["qs_waybill"].apply(
        lambda v: str(v).strip() if v is not None else None
    )

    # Drop rows with null waybill
    out = out[out["qs_waybill"].notna() & (out["qs_waybill"] != "") & (out["qs_waybill"] != "None")]
    out = out.reset_index(drop=True)

    return out


def _detect_header_row(df_raw: pd.DataFrame) -> int:
    """Detect if row 0 is a title row or the actual header."""
    if len(df_raw) == 0:
        return 0

    # Check if any known header text appears in row 0
    row0_values = [str(v).strip().lower() for v in df_raw.iloc[0] if pd.notna(v)]
    known_headers = ["konşimento", "müşteri", "servis", "taşıyıcı", "fatura ağırlığı", "r no"]

    for header in known_headers:
        if any(header in val for val in row0_values):
            return 0

    # Row 0 doesn't look like headers — assume it's a title row
    return 1
