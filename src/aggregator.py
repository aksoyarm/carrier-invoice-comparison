import pandas as pd


AGGREGATION_RULES = {
    "UPS":    {"grouping": "multi", "weight_agg": "first", "price_agg": "sum"},
    "FedEx":  {"grouping": "multi", "weight_agg": "max",   "price_agg": "sum"},
    "THY":    {"grouping": "single"},
    "PTT":    {"grouping": "single"},
    "Aramex": {"grouping": "single"},
}


def aggregate_invoice(df: pd.DataFrame, carrier: str) -> pd.DataFrame:
    """Group invoice rows by waybill and aggregate per carrier rules."""
    rules = AGGREGATION_RULES.get(carrier)
    if rules is None:
        raise ValueError(f"Unknown carrier: {carrier}")

    if rules["grouping"] == "single":
        # Deduplicate — take first occurrence if duplicates exist
        return df.drop_duplicates(subset="waybill", keep="first").reset_index(drop=True)

    # Multi-row grouping (UPS, FedEx)
    agg_dict = {
        "weight_raw": rules["weight_agg"],
        "price_raw": rules["price_agg"],
    }

    # Preserve extra columns (like destination) with 'first'
    for col in df.columns:
        if col not in ("waybill", "weight_raw", "price_raw"):
            agg_dict[col] = "first"

    result = df.groupby("waybill", as_index=False).agg(agg_dict)
    return result.reset_index(drop=True)
