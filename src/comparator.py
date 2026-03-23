import io
from dataclasses import dataclass

import pandas as pd

from src.weight_rounding import apply_rounding


@dataclass
class ComparisonSummary:
    total_waybills: int
    matched_count: int
    unmatched_invoice: int
    unmatched_qs: int
    weight_discrepancy_count: int
    price_discrepancy_count: int
    total_invoice_cost: float
    total_qs_expected_cost: float


def compare(
    invoice_df: pd.DataFrame,
    qs_df: pd.DataFrame,
    carrier: str,
) -> tuple[pd.DataFrame, ComparisonSummary, pd.DataFrame, pd.DataFrame]:
    """Join invoice and QS data, apply rounding, compute comparison."""
    # Ensure waybill columns are string
    invoice_df = invoice_df.copy()
    qs_df = qs_df.copy()
    invoice_df["waybill"] = invoice_df["waybill"].astype(str).str.strip()
    qs_df["qs_waybill"] = qs_df["qs_waybill"].astype(str).str.strip()

    # Left join: invoice is primary
    merged = invoice_df.merge(
        qs_df, left_on="waybill", right_on="qs_waybill", how="left"
    )

    # PTT invoice weights are in grams — convert to kg
    if carrier == "PTT":
        merged["weight_raw"] = merged["weight_raw"].apply(
            lambda w: w / 1000 if pd.notna(w) else w
        )

    # Apply rounding to both sides
    merged["weight_rounded_invoice"] = merged.apply(
        lambda row: _safe_round(carrier, row.get("weight_raw"), row), axis=1
    )
    merged["weight_rounded_qs"] = merged.apply(
        lambda row: _safe_round(carrier, row.get("qs_weight_raw"), row), axis=1
    )

    # Weight comparison
    merged["weight_match"] = merged.apply(
        lambda row: (
            abs(row["weight_rounded_invoice"] - row["weight_rounded_qs"]) < 1e-9
            if pd.notna(row["weight_rounded_invoice"]) and pd.notna(row["weight_rounded_qs"])
            else None
        ),
        axis=1,
    )
    merged["weight_difference"] = merged["weight_rounded_invoice"] - merged["weight_rounded_qs"]

    # Price comparison: Invoice Price vs (Sevkiyat Bedeli - ddp_bedeli)
    # For Aramex: use TL values
    if carrier in ("Aramex", "FedEx"):
        merged["qs_expected_cost"] = (
            merged["qs_ship_cost_tl"]
            - merged["qs_ddp_cost"].fillna(0) * merged["qs_ship_cost_rate"].fillna(0)
        )
    else:
        merged["qs_expected_cost"] = merged["qs_ship_cost"] - merged["qs_ddp_cost"].fillna(0)

    merged["price_difference"] = merged["qs_expected_cost"] - merged["price_raw"]
    merged["price_pct_change"] = merged.apply(
        lambda row: (
            (row["price_difference"] / row["qs_expected_cost"] * 100)
            if pd.notna(row["price_difference"]) and pd.notna(row["qs_expected_cost"]) and abs(row["qs_expected_cost"]) > 1e-9
            else None
        ),
        axis=1,
    )

    # Build comparison output
    output_cols = [
        "waybill", "weight_raw", "weight_rounded_invoice",
        "qs_weight_raw", "weight_rounded_qs",
        "weight_match", "weight_difference",
        "price_raw", "qs_expected_cost",
        "price_difference", "price_pct_change",
    ]
    if "destination" in merged.columns:
        output_cols.insert(1, "destination")
    if "qs_country" in merged.columns:
        insert_pos = 2 if "destination" in merged.columns else 1
        output_cols.insert(insert_pos, "qs_country")

    available_cols = [c for c in output_cols if c in merged.columns]
    comparison_df = merged[available_cols].copy()

    comparison_df = comparison_df.rename(columns={
        "waybill": "Waybill",
        "destination": "Destination",
        "qs_country": "Country",
        "weight_raw": "Invoice Weight (raw)",
        "weight_rounded_invoice": "Invoice Weight (rounded)",
        "qs_weight_raw": "QS Weight (raw)",
        "weight_rounded_qs": "QS Weight (rounded)",
        "weight_match": "Weight Match",
        "weight_difference": "Weight Difference",
        "price_raw": "Invoice Price",
        "qs_expected_cost": "Revenue After DDP",
        "price_difference": "Price Difference",
        "price_pct_change": "Price % Change",
    })

    # Identify unmatched
    unmatched_invoice = merged[merged["qs_waybill"].isna()][["waybill", "weight_raw", "price_raw"]].copy()
    unmatched_invoice = unmatched_invoice.rename(columns={
        "waybill": "Waybill", "weight_raw": "Weight", "price_raw": "Price"
    })

    invoice_waybills = set(invoice_df["waybill"].tolist())
    qs_carrier_filtered = qs_df[
        qs_df["qs_carrier"].str.lower().str.contains(carrier.lower(), na=False)
    ] if "qs_carrier" in qs_df.columns else qs_df
    unmatched_qs = qs_carrier_filtered[
        ~qs_carrier_filtered["qs_waybill"].isin(invoice_waybills)
    ][["qs_waybill", "qs_weight_raw", "qs_ship_cost"]].copy()
    unmatched_qs = unmatched_qs.rename(columns={
        "qs_waybill": "Waybill", "qs_weight_raw": "Weight", "qs_ship_cost": "Shipping Cost"
    })

    # Summary
    matched_mask = merged["qs_waybill"].notna()
    weight_disc = comparison_df["Weight Match"].eq(False).sum()
    price_disc = comparison_df["Price Difference"].abs().gt(0.01).sum()

    summary = ComparisonSummary(
        total_waybills=len(merged),
        matched_count=int(matched_mask.sum()),
        unmatched_invoice=len(unmatched_invoice),
        unmatched_qs=len(unmatched_qs),
        weight_discrepancy_count=int(weight_disc),
        price_discrepancy_count=int(price_disc),
        total_invoice_cost=merged["price_raw"].sum(),
        total_qs_expected_cost=merged.loc[matched_mask, "qs_expected_cost"].sum(),
    )

    return comparison_df, summary, unmatched_invoice, unmatched_qs


def _safe_round(carrier: str, weight, row: pd.Series) -> float | None:
    """Apply rounding with safe handling of NaN/None values."""
    if pd.isna(weight):
        return None
    return apply_rounding(
        carrier,
        float(weight),
        service=row.get("qs_service") if pd.notna(row.get("qs_service")) else None,
        destination=row.get("destination") if pd.notna(row.get("destination")) else None,
        customer_email=row.get("qs_customer") if pd.notna(row.get("qs_customer")) else None,
    )


def export_to_excel(
    comparison_df: pd.DataFrame,
    unmatched_invoice_df: pd.DataFrame,
    unmatched_qs_df: pd.DataFrame,
    summary: ComparisonSummary,
) -> bytes:
    """Export comparison results to an Excel file in memory."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        comparison_df.to_excel(writer, sheet_name="Comparison", index=False)
        if not unmatched_invoice_df.empty:
            unmatched_invoice_df.to_excel(writer, sheet_name="Unmatched Invoice", index=False)
        if not unmatched_qs_df.empty:
            unmatched_qs_df.to_excel(writer, sheet_name="Unmatched QS", index=False)

        summary_data = {
            "Metric": [
                "Total Waybills", "Matched", "Unmatched (Invoice)",
                "Unmatched (QS)", "Weight Discrepancies", "Price Discrepancies",
                "Total Invoice Cost", "Total Revenue After DDP",
            ],
            "Value": [
                summary.total_waybills, summary.matched_count,
                summary.unmatched_invoice, summary.unmatched_qs,
                summary.weight_discrepancy_count, summary.price_discrepancy_count,
                summary.total_invoice_cost, summary.total_qs_expected_cost,
            ],
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

    return output.getvalue()
