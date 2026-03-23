import pandas as pd

from src.comparator import compare


def _make_invoice_df(rows):
    cols = ["waybill", "weight_raw", "price_raw"]
    return pd.DataFrame(rows, columns=cols)


def _make_qs_df(rows):
    df = pd.DataFrame(rows)
    for col in ["qs_waybill", "qs_customer", "qs_service", "qs_weight_raw",
                 "qs_cust_price_ccy", "qs_cust_price", "qs_ship_cost_ccy",
                 "qs_ship_cost", "qs_ddp_cost", "qs_ship_cost_rate",
                 "qs_ship_cost_tl", "qs_carrier"]:
        if col not in df.columns:
            df[col] = None
    return df


class TestCompareBasicJoin:
    def test_all_matched(self):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
            {"waybill": "WB002", "weight_raw": 3.0, "price_raw": 50.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0, "qs_carrier": "FedEx"},
            {"qs_waybill": "WB002", "qs_weight_raw": 3.0,
             "qs_ship_cost": 50.0, "qs_ddp_cost": 0, "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        assert summary.total_waybills == 2
        assert summary.matched_count == 2
        assert summary.unmatched_invoice == 0

    def test_unmatched_invoice(self):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
            {"waybill": "WB003", "weight_raw": 2.0, "price_raw": 30.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0, "qs_carrier": "FedEx"},
        ])
        _, summary, unmatched_inv, _ = compare(inv, qs, "FedEx")
        assert summary.unmatched_invoice == 1
        assert unmatched_inv.iloc[0]["Waybill"] == "WB003"

    def test_unmatched_qs(self):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0, "qs_carrier": "FedEx"},
            {"qs_waybill": "WB999", "qs_weight_raw": 1.0,
             "qs_ship_cost": 15.0, "qs_ddp_cost": 0, "qs_carrier": "FedEx"},
        ])
        _, summary, _, unmatched_qs = compare(inv, qs, "FedEx")
        assert summary.unmatched_qs == 1
        assert unmatched_qs.iloc[0]["Waybill"] == "WB999"


class TestCompareRounding:
    def test_weight_rounding_applied(self):
        """FedEx: 5.3 rounds to 5.5"""
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.3, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.3,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0, "qs_carrier": "FedEx"},
        ])
        comp_df, _, _, _ = compare(inv, qs, "FedEx")
        assert comp_df.iloc[0]["Invoice Weight (rounded)"] == 5.5
        assert comp_df.iloc[0]["QS Weight (rounded)"] == 5.5
        assert comp_df.iloc[0]["Weight Match"] == True

    def test_weight_discrepancy(self):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.3, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 6.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0, "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        assert comp_df.iloc[0]["Weight Match"] == False
        assert summary.weight_discrepancy_count == 1


class TestComparePTT:
    def test_ptt_gram_conversion_invoice_only(self):
        inv = _make_invoice_df([
            {"waybill": "RE123456789TR", "weight_raw": 700.0, "price_raw": 50.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "RE123456789TR", "qs_weight_raw": 0.7,
             "qs_ship_cost": 50.0, "qs_ddp_cost": 0, "qs_carrier": "PTT"},
        ])
        comp_df, _, _, _ = compare(inv, qs, "PTT")
        assert comp_df.iloc[0]["Invoice Weight (rounded)"] == 1.0
        assert comp_df.iloc[0]["QS Weight (rounded)"] == 1.0


class TestComparePriceExpected:
    def test_price_match_ship_minus_ddp(self):
        """QS Expected = Sevkiyat Bedeli - ddp_bedeli"""
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 80.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 20.0, "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        # Expected = 100 - 20 = 80, Invoice = 80 → match
        assert comp_df.iloc[0]["QS Revenue - DDP"] == 80.0
        assert comp_df.iloc[0]["Price Difference"] == 0.0
        assert comp_df.iloc[0]["Price % Change"] == 0.0
        assert summary.price_discrepancy_count == 0

    def test_price_mismatch(self):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 90.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 20.0, "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        # Expected = 80, Invoice = 90 → diff = -10, pct = -10/90 * 100 ≈ -11.11%
        assert comp_df.iloc[0]["Price Difference"] == -10.0
        assert abs(comp_df.iloc[0]["Price % Change"] - (-100 / 9)) < 0.01
        assert summary.price_discrepancy_count == 1

    def test_aramex_uses_tl(self):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 600.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 15.0, "qs_ddp_cost": 2.0,
             "qs_ship_cost_rate": 44.5, "qs_ship_cost_tl": 667.5,
             "qs_carrier": "Aramex"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "Aramex")
        # Expected TL = 667.5 - 2.0 * 44.5 = 578.5
        assert comp_df.iloc[0]["QS Revenue - DDP"] == 578.5
        assert comp_df.iloc[0]["Price Difference"] == 578.5 - 600.0
        assert summary.total_qs_expected_cost == 578.5
