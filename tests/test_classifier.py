import io

import pandas as pd

from src.classifier import (
    _layer1_header_keywords,
    _layer2_cell_a1,
    _layer3_tracking_regex,
    _layer4_column_count,
)


def _make_df(rows, num_cols=None):
    """Create a DataFrame from a list of row lists."""
    if num_cols:
        # Pad rows to have num_cols columns
        rows = [row + [None] * (num_cols - len(row)) for row in rows]
    return pd.DataFrame(rows)


class TestLayer1HeaderKeywords:
    def test_ups(self):
        df = _make_df([
            ["Fatura Detay UPY - Mart 2026", None, None],
            ["Waybill", "Tarih", "Ülke", "Geçerli Ağırlık", "Para Birimi",
             "Fatura P.Birimi", "Servis", "Ürün Kodu", "Paket", "Fatura Tutarı"],
        ])
        result = _layer1_header_keywords(df)
        assert result is not None
        assert result.carrier == "UPS"
        assert result.confidence >= 0.5

    def test_fedex(self):
        df = _make_df([
            ["Billing Country/Territory", "Air Waybill Number", "Service Type",
             "Rated Weight Amount", "Dim Divisor", "Other Col"],
        ])
        result = _layer1_header_keywords(df)
        assert result is not None
        assert result.carrier == "FedEx"

    def test_thy(self):
        df = _make_df([
            ["Col1", "Tracking ID", "WDC CW", "Dağıtım Noktası", "Konsolide", "HS Code"],
        ])
        result = _layer1_header_keywords(df)
        assert result is not None
        assert result.carrier == "THY"

    def test_ptt(self):
        df = _make_df([
            ["BARKOD NO", "GİDİŞ TÜRÜ", "VARIŞ ÜLKESİ", "AĞIRLIK", "FATURA NAVLUN"],
        ])
        result = _layer1_header_keywords(df)
        assert result is not None
        assert result.carrier == "PTT"

    def test_aramex(self):
        df = _make_df([
            ["Airway Bill No.", "Chargeable Weight", "Pick up Date", "AR Exchange Rate"],
        ])
        result = _layer1_header_keywords(df)
        assert result is not None
        assert result.carrier == "Aramex"

    def test_no_match(self):
        df = _make_df([["Random", "Headers", "Here"]])
        result = _layer1_header_keywords(df)
        assert result is None


class TestLayer2CellA1:
    def test_ups_match(self):
        df = _make_df([["Fatura Detay UPY - Mart 2026", None]])
        result = _layer2_cell_a1(df)
        assert result is not None
        assert result.carrier == "UPS"
        assert result.confidence == 0.8

    def test_no_match(self):
        df = _make_df([["Some other title", None]])
        result = _layer2_cell_a1(df)
        assert result is None


class TestLayer3TrackingRegex:
    def test_ups_tracking(self):
        df = _make_df([
            ["Header1", "Header2"],
            ["SubHeader1", "SubHeader2"],
            ["1ZABC12345678901234", "data"],
        ])
        result = _layer3_tracking_regex(df)
        assert result is not None
        assert result.carrier == "UPS"

    def test_ptt_tracking(self):
        df = _make_df([
            ["Header1", "Header2"],
            ["SubHeader1", "SubHeader2"],
            ["RE123456789TR", "data"],
        ])
        result = _layer3_tracking_regex(df)
        assert result is not None
        assert result.carrier == "PTT"

    def test_thy_tracking(self):
        df = _make_df([
            ["Header1", "Header2"],
            ["SubHeader1", "SubHeader2"],
            ["33Q6R5001234", "data"],
        ])
        result = _layer3_tracking_regex(df)
        assert result is not None
        assert result.carrier == "THY"

    def test_no_data(self):
        df = _make_df([["Header1"], ["SubHeader1"]])
        result = _layer3_tracking_regex(df)
        assert result is None


class TestLayer4ColumnCount:
    def test_fedex_many_cols(self):
        df = _make_df([[None] * 168])
        result = _layer4_column_count(df)
        assert result is not None
        assert result.carrier == "FedEx"

    def test_thy_22_cols(self):
        df = _make_df([[None] * 22])
        result = _layer4_column_count(df)
        assert result is not None
        assert result.carrier == "THY"

    def test_ups_13_cols(self):
        df = _make_df([[None] * 13])
        result = _layer4_column_count(df)
        assert result is not None
        assert result.carrier == "UPS"

    def test_ptt_9_cols(self):
        df = _make_df([[None] * 9])
        result = _layer4_column_count(df)
        assert result is not None
        assert result.carrier == "PTT"

    def test_aramex_20_cols(self):
        df = _make_df([[None] * 20])
        result = _layer4_column_count(df)
        # 20 is in THY range (18-25) first, so THY wins
        assert result is not None
        assert result.carrier == "THY"

    def test_aramex_16_cols(self):
        df = _make_df([[None] * 16])
        result = _layer4_column_count(df)
        assert result is not None
        assert result.carrier == "Aramex"

    def test_no_match(self):
        df = _make_df([[None] * 5])
        result = _layer4_column_count(df)
        assert result is None


class TestLayerPriority:
    def test_layer1_takes_priority(self):
        """If Layer 1 matches, later layers are not used even if they would also match."""
        df = _make_df([
            ["Waybill", "Geçerli Ağırlık", "Fatura P.Birimi", "Fatura Tutarı"],
            ["1ZABC12345678901234", "5.0", "USD", "100.00"],
        ])
        # Layer 1 should match UPS, Layer 3 would also match UPS
        result = _layer1_header_keywords(df)
        assert result is not None
        assert result.carrier == "UPS"
        assert result.method == "header_keywords"
