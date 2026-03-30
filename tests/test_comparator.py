from unittest.mock import patch

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
                 "qs_ship_cost_tl", "qs_carrier", "qs_country",
                 "qs_payment_date"]:
        if col not in df.columns:
            df[col] = None
    return df


@patch("src.comparator.fetch_tcmb_rate", return_value=None)
class TestCompareBasicJoin:
    def test_all_matched(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
            {"waybill": "WB002", "weight_raw": 3.0, "price_raw": 50.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 100.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "FedEx"},
            {"qs_waybill": "WB002", "qs_weight_raw": 3.0,
             "qs_ship_cost": 50.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 50.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        assert summary.total_waybills == 2
        assert summary.matched_count == 2
        assert summary.unmatched_invoice == 0

    def test_unmatched_invoice(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
            {"waybill": "WB003", "weight_raw": 2.0, "price_raw": 30.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 100.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "FedEx"},
        ])
        _, summary, unmatched_inv, _ = compare(inv, qs, "FedEx")
        assert summary.unmatched_invoice == 1
        assert unmatched_inv.iloc[0]["Waybill"] == "WB003"

    def test_unmatched_qs(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 100.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "FedEx"},
            {"qs_waybill": "WB999", "qs_weight_raw": 1.0,
             "qs_ship_cost": 15.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 15.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "FedEx"},
        ])
        _, summary, _, unmatched_qs = compare(inv, qs, "FedEx")
        assert summary.unmatched_qs == 1
        assert unmatched_qs.iloc[0]["Waybill"] == "WB999"


@patch("src.comparator.fetch_tcmb_rate", return_value=None)
class TestCompareRounding:
    def test_weight_rounding_applied(self, _mock_tcmb):
        """FedEx: 5.3 rounds to 5.5"""
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.3, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.3,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 100.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "FedEx"},
        ])
        comp_df, _, _, _ = compare(inv, qs, "FedEx")
        assert comp_df.iloc[0]["Invoice Weight (rounded)"] == 5.5
        assert comp_df.iloc[0]["QS Weight (rounded)"] == 5.5
        assert comp_df.iloc[0]["Weight Match"] == True

    def test_weight_discrepancy(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.3, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 6.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 100.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        assert comp_df.iloc[0]["Weight Match"] == False
        assert summary.weight_discrepancy_count == 1


@patch("src.comparator.fetch_tcmb_rate", return_value=None)
class TestComparePTT:
    def test_ptt_gram_conversion_invoice_only(self, _mock_tcmb):
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


@patch("src.comparator.fetch_tcmb_rate", return_value=None)
class TestComparePriceExpected:
    def test_price_match_ship_minus_ddp(self, _mock_tcmb):
        """QS Expected = Sevkiyat Bedeli TL - ddp_bedeli * Sevkiyat Bedeli Kuru (for FedEx)"""
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 80.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 20.0,
             "qs_ship_cost_tl": 3600.0, "qs_ship_cost_rate": 36.0,
             "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        # Expected TL = 3600 - 20 * 36 = 3600 - 720 = 2880, Invoice = 80
        assert comp_df.iloc[0]["Revenue After DDP"] == 2880.0
        assert summary.price_discrepancy_count == 1

    def test_price_mismatch(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 2880.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 20.0,
             "qs_ship_cost_tl": 3600.0, "qs_ship_cost_rate": 36.0,
             "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        # Expected TL = 3600 - 20 * 36 = 2880, Invoice = 2880 → match
        assert comp_df.iloc[0]["Revenue After DDP"] == 2880.0
        assert comp_df.iloc[0]["Price Difference"] == 0.0
        assert summary.price_discrepancy_count == 0

    def test_fedex_uses_tl(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 2880.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 20.0,
             "qs_ship_cost_rate": 36.0, "qs_ship_cost_tl": 3600.0,
             "qs_carrier": "FedEx"},
        ])
        comp_df, summary, _, _ = compare(inv, qs, "FedEx")
        # Expected TL = 3600 - 20 * 36 = 2880
        assert comp_df.iloc[0]["Revenue After DDP"] == 2880.0
        assert comp_df.iloc[0]["Price Difference"] == 0.0
        assert summary.total_qs_expected_cost == 2880.0

    def test_aramex_uses_tl(self, _mock_tcmb):
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
        assert comp_df.iloc[0]["Revenue After DDP"] == 578.5
        assert comp_df.iloc[0]["Price Difference"] == 578.5 - 600.0
        assert summary.total_qs_expected_cost == 578.5


@patch("src.comparator.fetch_tcmb_rate", return_value=None)
class TestCompareCountryColumn:
    def test_country_column_present_in_output(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 100.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "THY", "qs_country": "US"},
        ])
        comp_df, _, _, _ = compare(inv, qs, "THY")
        assert "Country" in comp_df.columns
        assert comp_df.iloc[0]["Country"] == "US"

    def test_country_column_none_when_missing(self, _mock_tcmb):
        inv = _make_invoice_df([
            {"waybill": "WB001", "weight_raw": 5.0, "price_raw": 100.0},
        ])
        qs = _make_qs_df([
            {"qs_waybill": "WB001", "qs_weight_raw": 5.0,
             "qs_ship_cost": 100.0, "qs_ddp_cost": 0,
             "qs_ship_cost_tl": 100.0, "qs_ship_cost_rate": 1.0,
             "qs_carrier": "THY"},
        ])
        comp_df, _, _, _ = compare(inv, qs, "THY")
        assert "Country" in comp_df.columns
