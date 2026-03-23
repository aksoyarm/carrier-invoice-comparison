import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, ColumnsAutoSizeMode

from src.classifier import classify_carrier
from src.parser import parse_invoice
from src.aggregator import aggregate_invoice
from src.qs_parser import parse_quicksight
from src.comparator import compare, export_to_excel


def _build_totals_row(df: pd.DataFrame) -> dict:
    """Build a totals row dict for AG Grid pinnedBottomRowData."""
    row = {"Waybill": "TOTAL"}

    for col in ["Destination", "Country", "Weight Match"]:
        if col in df.columns:
            row[col] = ""

    sum_cols = [
        "Invoice Weight (raw)", "Invoice Weight (rounded)",
        "QS Weight (raw)", "QS Weight (rounded)",
        "Weight Difference", "Invoice Price",
        "Revenue After DDP", "Price Difference",
    ]
    for col in sum_cols:
        if col in df.columns:
            row[col] = float(df[col].sum())

    if "Invoice Price" in df.columns and "Revenue After DDP" in df.columns:
        total_inv = df["Invoice Price"].sum()
        total_qs = df["Revenue After DDP"].sum()
        if abs(total_qs) > 1e-9:
            row["Price % Change"] = (total_qs - total_inv) / abs(total_qs) * 100
        else:
            row["Price % Change"] = None

    return row

st.set_page_config(page_title="Carrier Invoice Comparison", layout="wide")
st.title("Carrier Invoice Comparison")

# Sidebar: file uploaders
with st.sidebar:
    st.header("Upload Files")
    invoice_file = st.file_uploader("Carrier Invoice", type=["xlsx", "xls"])
    qs_file = st.file_uploader("QuickSight Export", type=["xlsx", "xls"])

if invoice_file and qs_file:
    with st.spinner("Classifying carrier and processing data..."):
        # Step 1: Classify carrier
        try:
            invoice_bytes = invoice_file.getvalue()
            result = classify_carrier(invoice_bytes)
        except Exception as e:
            st.error(f"Error reading invoice file: {e}")
            st.stop()

        # Classification banner
        col_c1, col_c2 = st.columns(2)
        col_c1.metric("Detected Carrier", result.carrier)
        col_c2.metric("Confidence", f"{result.confidence:.0%}")

        if result.carrier == "UNKNOWN":
            st.error(
                "Could not identify the carrier from the uploaded invoice. "
                "Please verify the file and try again."
            )
            st.stop()

        # Step 2: Parse invoice
        try:
            invoice_df = parse_invoice(invoice_bytes, result.carrier)
            invoice_df = aggregate_invoice(invoice_df, result.carrier)
        except ValueError as e:
            st.error(f"Error parsing invoice: {e}")
            st.stop()
        except Exception as e:
            st.error(f"Unexpected error parsing invoice: {e}")
            st.stop()

        # Step 3: Parse QuickSight
        try:
            qs_df = parse_quicksight(qs_file.getvalue())
        except ValueError as e:
            st.error(f"Error parsing QuickSight file: {e}")
            st.stop()
        except Exception as e:
            st.error(f"Unexpected error parsing QuickSight file: {e}")
            st.stop()

        # Step 4: Compare
        try:
            comparison_df, summary, unmatched_inv, unmatched_qs = compare(
                invoice_df, qs_df, result.carrier
            )
        except Exception as e:
            st.error(f"Error during comparison: {e}")
            st.stop()

    # Summary cards
    st.subheader("Summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Waybills", summary.total_waybills)
    col2.metric("Matched", summary.matched_count)
    col3.metric("Unmatched (Invoice)", summary.unmatched_invoice)
    col4.metric("Weight Discrepancies", summary.weight_discrepancy_count)
    col5.metric("Price Discrepancies", summary.price_discrepancy_count)

    qs_label = "Total Revenue After DDP (TL)" if result.carrier in ("Aramex", "FedEx") else "Total Revenue After DDP"
    col6, col7 = st.columns(2)
    col6.metric("Total Invoice Cost", f"{summary.total_invoice_cost:,.2f}")
    col7.metric(qs_label, f"{summary.total_qs_expected_cost:,.2f}")

    # Difference: absolute and percentage
    diff = summary.total_qs_expected_cost - summary.total_invoice_cost
    pct = (diff / summary.total_qs_expected_cost * 100) if summary.total_qs_expected_cost else 0
    sign = "+" if diff >= 0 else ""
    pct_sign = "+" if pct >= 0 else ""
    col8, col9 = st.columns(2)
    col8.metric("Profit", f"{sign}{diff:,.2f}")
    col9.metric("%Profit", f"{pct_sign}{pct:,.2f}%")

    st.divider()

    # Detailed comparison table with AG Grid
    st.subheader("Detailed Comparison")
    detail_df = comparison_df.copy()

    totals_row = _build_totals_row(detail_df)

    gb = GridOptionsBuilder.from_dataframe(detail_df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_column("Waybill", pinned="left")

    numeric_cols = [
        "Invoice Weight (raw)", "Invoice Weight (rounded)",
        "QS Weight (raw)", "QS Weight (rounded)",
        "Weight Difference", "Invoice Price",
        "Revenue After DDP", "Price Difference",
    ]
    for col in numeric_cols:
        if col in detail_df.columns:
            gb.configure_column(
                col, type=["numericColumn"],
                valueFormatter="x != null ? x.toFixed(2) : ''",
            )

    if "Price % Change" in detail_df.columns:
        gb.configure_column(
            "Price % Change", type=["numericColumn"],
            valueFormatter="x != null ? x.toFixed(2) + '%' : ''",
        )

    grid_options = gb.build()
    grid_options["pinnedBottomRowData"] = [totals_row]

    AgGrid(
        detail_df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.NO_UPDATE,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        theme="streamlit",
        height=500,
    )

    st.divider()

    # Weight Discrepancies
    st.subheader("Weight Discrepancies")
    weight_disc = comparison_df[comparison_df["Weight Match"] == False].copy()
    if weight_disc.empty:
        st.success("No weight discrepancies found!")
    else:
        weight_cols = [
            "Waybill", "Invoice Weight (rounded)",
            "QS Weight (rounded)", "Weight Difference",
        ]
        if "Destination" in weight_disc.columns:
            weight_cols.insert(1, "Destination")
        if "Country" in weight_disc.columns:
            insert_pos = 2 if "Destination" in weight_disc.columns else 1
            weight_cols.insert(insert_pos, "Country")
        available = [c for c in weight_cols if c in weight_disc.columns]
        st.warning(f"{len(weight_disc)} orders with weight mismatch")
        weight_disc_sorted = weight_disc[available].sort_values("Weight Difference", ascending=True)
        styled_w = weight_disc_sorted.style.apply(
            lambda row: ["background-color: #ffcccc"] * len(row), axis=1
        )
        st.dataframe(styled_w, use_container_width=True, hide_index=True)

    # Price Discrepancies
    st.subheader("Price Discrepancies")
    price_disc = comparison_df[comparison_df["Price Difference"].abs() > 0.01].copy()
    if price_disc.empty:
        st.success("No price discrepancies found!")
    else:
        st.warning(f"{len(price_disc)} orders with price mismatch")

        # Format Price % Change as string with % sign
        price_disc["Price % Change"] = price_disc["Price % Change"].apply(
            lambda v: f"{v:.2f}%" if pd.notna(v) else ""
        )

        price_cols = ["Waybill", "Invoice Price", "Revenue After DDP", "Price Difference", "Price % Change"]
        available = [c for c in price_cols if c in price_disc.columns]

        # Sort by Price Difference before adding sum row
        price_disc = price_disc.sort_values("Price Difference", ascending=True)

        # Add sum row
        total_inv = price_disc["Invoice Price"].sum()
        total_diff = price_disc["Price Difference"].sum()
        total_qs_rev = price_disc["Revenue After DDP"].sum()
        total_pct = f"{abs(total_diff) / total_qs_rev * 100:.2f}%" if total_qs_rev else ""
        sum_row = pd.DataFrame([{
            "Waybill": "TOTAL",
            "Invoice Price": total_inv,
            "Revenue After DDP": price_disc["Revenue After DDP"].sum(),
            "Price Difference": total_diff,
            "Price % Change": total_pct,
        }])
        price_with_total = pd.concat([price_disc[available], sum_row[available]], ignore_index=True)

        def _highlight_price(row):
            if row.get("Waybill") == "TOTAL":
                return ["font-weight: bold; background-color: #e0e0e0"] * len(row)
            return ["background-color: #ffe0b2"] * len(row)

        styled_p = price_with_total.style.apply(_highlight_price, axis=1)
        st.dataframe(styled_p, use_container_width=True, hide_index=True)

    # Unmatched sections
    if not unmatched_inv.empty:
        with st.expander(f"Unmatched Invoice Waybills ({len(unmatched_inv)})"):
            st.dataframe(unmatched_inv, use_container_width=True, hide_index=True)

    if not unmatched_qs.empty:
        with st.expander(f"Unmatched QS Waybills ({len(unmatched_qs)})"):
            st.dataframe(unmatched_qs, use_container_width=True, hide_index=True)

    st.divider()

    # Export
    excel_bytes = export_to_excel(comparison_df, unmatched_inv, unmatched_qs, summary)
    st.download_button(
        label="Download Comparison as Excel",
        data=excel_bytes,
        file_name="comparison_result.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Please upload both the Carrier Invoice and QuickSight Export files in the sidebar.")
