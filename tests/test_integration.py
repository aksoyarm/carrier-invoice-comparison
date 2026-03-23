"""Integration tests using real test data files.

Carrier Invoices.xlsx has 5 sheets — each treated as a separate upload.
QuickSight Data.xlsx has 5 sheets — merged into one for testing.
"""
import io

import pandas as pd
import pytest

from src.classifier import classify_carrier
from src.parser import parse_invoice
from src.aggregator import aggregate_invoice
from src.qs_parser import parse_quicksight
from src.comparator import compare

INVOICE_PATH = "/Users/armanaksoy/express-calculator/test-data/Carrier Invoices.xlsx"
QS_PATH = "/Users/armanaksoy/express-calculator/test-data/QuickSight Data.xlsx"

CARRIER_SHEETS = {
    "UPS": "UPS Fatura",
    "FedEx": "Fedex Fatura",
    "THY": "THY Fatura",
    "PTT": "PTT Fatura",
    "Aramex": "Aramex Fatura",
}

QS_SHEETS = [
    "UPS Sevkıyat",
    "Fedex Sevkıyat",
    "THY Sevkiyat",
    "PTT Sevkiyat",
    "Aramex Sevkiyat",
]


def _extract_sheet_as_bytes(path: str, sheet_name: str) -> bytes:
    """Read one sheet from a multi-sheet Excel file and return as standalone Excel bytes."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False, engine="openpyxl")
    return buf.getvalue()


def _build_merged_qs_bytes() -> bytes:
    """Merge all QS sheets into one single-sheet Excel file with randomized rows."""
    frames = []
    for sheet in QS_SHEETS:
        df_raw = pd.read_excel(QS_PATH, sheet_name=sheet, header=None, engine="openpyxl")
        # Find the header row (look for 'Konşimento' in any row)
        header_row_idx = None
        for i in range(min(5, len(df_raw))):
            row_vals = [str(v).strip() for v in df_raw.iloc[i] if pd.notna(v)]
            if any("Konşimento" in v for v in row_vals):
                header_row_idx = i
                break
        if header_row_idx is None:
            continue
        # Re-read with correct header
        df = pd.read_excel(QS_PATH, sheet_name=sheet, header=header_row_idx, engine="openpyxl")
        # Drop any fully-NaN rows that might exist between title and data
        df = df.dropna(how="all")
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    # Randomize row order
    merged = merged.sample(frac=1, random_state=42).reset_index(drop=True)

    buf = io.BytesIO()
    merged.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


@pytest.fixture(scope="module")
def merged_qs_bytes():
    return _build_merged_qs_bytes()


@pytest.fixture(scope="module")
def merged_qs_df(merged_qs_bytes):
    return parse_quicksight(merged_qs_bytes)


class TestClassification:
    @pytest.mark.parametrize("expected_carrier,sheet_name", list(CARRIER_SHEETS.items()))
    def test_classify_each_carrier(self, expected_carrier, sheet_name):
        invoice_bytes = _extract_sheet_as_bytes(INVOICE_PATH, sheet_name)
        result = classify_carrier(invoice_bytes)
        assert result.carrier == expected_carrier, (
            f"Expected {expected_carrier} but got {result.carrier} "
            f"(method={result.method}, confidence={result.confidence})"
        )


class TestInvoiceParsing:
    @pytest.mark.parametrize("carrier,sheet_name", list(CARRIER_SHEETS.items()))
    def test_parse_each_carrier(self, carrier, sheet_name):
        invoice_bytes = _extract_sheet_as_bytes(INVOICE_PATH, sheet_name)
        df = parse_invoice(invoice_bytes, carrier)
        assert len(df) > 0, f"No rows parsed for {carrier}"
        assert "waybill" in df.columns
        assert "weight_raw" in df.columns
        assert "price_raw" in df.columns
        # Check no null waybills
        assert df["waybill"].notna().all()
        # Check weights and prices are numeric
        assert df["weight_raw"].dtype in ("float64", "int64")
        assert df["price_raw"].dtype in ("float64", "int64")
        print(f"\n{carrier}: {len(df)} rows parsed")
        print(df.head(3).to_string())


class TestAggregation:
    @pytest.mark.parametrize("carrier,sheet_name", list(CARRIER_SHEETS.items()))
    def test_aggregate_each_carrier(self, carrier, sheet_name):
        invoice_bytes = _extract_sheet_as_bytes(INVOICE_PATH, sheet_name)
        df = parse_invoice(invoice_bytes, carrier)
        agg = aggregate_invoice(df, carrier)
        assert len(agg) > 0
        # No duplicate waybills after aggregation
        assert agg["waybill"].is_unique, f"Duplicate waybills after aggregation for {carrier}"
        print(f"\n{carrier}: {len(df)} rows -> {len(agg)} after aggregation")


class TestQSParsing:
    def test_parse_merged_qs(self, merged_qs_df):
        assert len(merged_qs_df) > 0
        assert "qs_waybill" in merged_qs_df.columns
        assert "qs_weight_raw" in merged_qs_df.columns
        assert "qs_cust_price" in merged_qs_df.columns
        assert "qs_ship_cost" in merged_qs_df.columns
        print(f"\nQS: {len(merged_qs_df)} total rows")
        print(merged_qs_df.head(3).to_string())


class TestFullPipeline:
    @pytest.mark.parametrize("carrier,sheet_name", list(CARRIER_SHEETS.items()))
    def test_full_pipeline(self, carrier, sheet_name, merged_qs_bytes, merged_qs_df):
        # Parse invoice
        invoice_bytes = _extract_sheet_as_bytes(INVOICE_PATH, sheet_name)
        invoice_df = parse_invoice(invoice_bytes, carrier)
        invoice_df = aggregate_invoice(invoice_df, carrier)

        # Compare
        comp_df, summary, unmatched_inv, unmatched_qs = compare(
            invoice_df, merged_qs_df, carrier
        )

        print(f"\n=== {carrier} Pipeline Results ===")
        print(f"  Invoice waybills: {len(invoice_df)}")
        print(f"  Total waybills: {summary.total_waybills}")
        print(f"  Matched: {summary.matched_count}")
        print(f"  Unmatched (invoice): {summary.unmatched_invoice}")
        print(f"  Unmatched (QS): {summary.unmatched_qs}")
        print(f"  Weight discrepancies: {summary.weight_discrepancy_count}")
        print(f"  Total invoice cost: {summary.total_invoice_cost:.2f}")
        print(f"  Total QS expected cost: {summary.total_qs_expected_cost:.2f}")

        if not comp_df.empty:
            print(f"\n  Sample comparison rows:")
            print(comp_df.head(3).to_string())

        # Basic sanity checks
        assert summary.total_waybills == len(invoice_df)
        assert summary.matched_count + summary.unmatched_invoice == summary.total_waybills
        assert summary.matched_count > 0, f"No matches found for {carrier} — check waybill format"
