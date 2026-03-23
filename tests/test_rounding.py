from src.utils import round_up, parse_turkish_number, col_letter_to_index, normalize_country
from src.weight_rounding import apply_rounding


class TestRoundUp:
    def test_exact_multiple_stays(self):
        assert round_up(0.5, 0.5) == 0.5

    def test_round_up_basic(self):
        assert round_up(0.3, 0.5) == 0.5

    def test_round_up_integer_interval(self):
        assert round_up(10.01, 1.0) == 11.0

    def test_round_up_tenth_interval(self):
        assert round_up(0.11, 0.1) == 0.2

    def test_zero(self):
        assert round_up(0, 0.5) == 0.0

    def test_very_small(self):
        assert round_up(0.001, 0.1) == 0.1

    def test_large_value(self):
        assert round_up(100.5, 1.0) == 101.0

    def test_exact_integer(self):
        assert round_up(10.0, 1.0) == 10.0

    def test_exact_half(self):
        assert round_up(1.0, 0.5) == 1.0

    def test_just_above_exact(self):
        assert round_up(0.51, 0.5) == 1.0

    def test_floating_point_edge(self):
        # 0.1 + 0.2 = 0.30000000000000004 in float
        assert round_up(0.1 + 0.2, 0.5) == 0.5

    def test_round_up_3kg_half(self):
        assert round_up(3.0, 0.5) == 3.0

    def test_round_up_2point5(self):
        assert round_up(2.5, 0.5) == 2.5

    def test_round_up_just_below_boundary(self):
        assert round_up(9.99, 0.5) == 10.0


class TestParseTurkishNumber:
    def test_standard_float(self):
        assert parse_turkish_number(1234.56) == 1234.56

    def test_turkish_format(self):
        assert parse_turkish_number("1.004,12") == 1004.12

    def test_comma_only(self):
        assert parse_turkish_number("3,5") == 3.5

    def test_dot_only(self):
        assert parse_turkish_number("3.5") == 3.5

    def test_none(self):
        assert parse_turkish_number(None) is None

    def test_nan(self):
        assert parse_turkish_number(float('nan')) is None

    def test_integer_string(self):
        assert parse_turkish_number("100") == 100.0

    def test_already_int(self):
        assert parse_turkish_number(100) == 100.0

    def test_empty_string(self):
        assert parse_turkish_number("") is None

    def test_whitespace_string(self):
        assert parse_turkish_number("  1.234,56  ") == 1234.56

    def test_currency_symbol(self):
        assert parse_turkish_number("$1,234.56") == 1234.56


class TestColLetterToIndex:
    def test_a(self):
        assert col_letter_to_index("A") == 0

    def test_z(self):
        assert col_letter_to_index("Z") == 25

    def test_aa(self):
        assert col_letter_to_index("AA") == 26

    def test_bk(self):
        assert col_letter_to_index("BK") == 62

    def test_bn(self):
        assert col_letter_to_index("BN") == 65

    def test_ac(self):
        assert col_letter_to_index("AC") == 28

    def test_ae(self):
        assert col_letter_to_index("AE") == 30

    def test_af(self):
        assert col_letter_to_index("AF") == 31


class TestNormalizeCountry:
    def test_us(self):
        assert normalize_country("US") == "US"

    def test_usa(self):
        assert normalize_country("USA") == "US"

    def test_united_states(self):
        assert normalize_country("United States") == "US"

    def test_amerika_turkish(self):
        assert normalize_country("AMERİKA") == "US"

    def test_gb(self):
        assert normalize_country("GB") == "GB"

    def test_uk(self):
        assert normalize_country("UK") == "GB"

    def test_ingiltere_turkish(self):
        assert normalize_country("İNGİLTERE") == "GB"

    def test_au(self):
        assert normalize_country("AU") == "AU"

    def test_avustralya(self):
        assert normalize_country("AVUSTRALYA") == "AU"

    def test_unknown_country(self):
        assert normalize_country("DE") == "DE"

    def test_case_insensitive(self):
        assert normalize_country("united kingdom") == "GB"

    def test_whitespace(self):
        assert normalize_country("  US  ") == "US"


class TestApplyRounding:
    # UPS
    def test_ups_express_under_10(self):
        assert apply_rounding("UPS", 3.2, service="express") == 3.5

    def test_ups_express_over_10(self):
        assert apply_rounding("UPS", 10.01, service="express") == 11.0

    def test_ups_expedited(self):
        assert apply_rounding("UPS", 3.2, service="expedited") == 4.0

    def test_ups_no_service_skips_rounding(self):
        assert apply_rounding("UPS", 3.2, service=None) == 3.2

    def test_ups_unknown_service_skips_rounding(self):
        assert apply_rounding("UPS", 3.2, service="saver") == 3.2

    # FedEx
    def test_fedex_under_71(self):
        assert apply_rounding("FedEx", 50.1) == 50.5

    def test_fedex_over_71(self):
        assert apply_rounding("FedEx", 71.1) == 72.0

    def test_fedex_exact_71(self):
        assert apply_rounding("FedEx", 71.0) == 71.0

    # THY Priority 1: GB + hiccup
    def test_thy_gb_hiccup_under_5(self):
        assert apply_rounding("THY", 4.3, destination="GB", customer_email="ops@hiccup.com") == 4.5

    def test_thy_gb_hiccup_over_5(self):
        assert apply_rounding("THY", 5.1, destination="INGILTERE", customer_email="ops@hiccup.com") == 6.0

    # THY Priority 2: US + hiccup
    def test_thy_us_hiccup_under_2_5(self):
        assert apply_rounding("THY", 2.1, destination="US", customer_email="OPS@HICCUP.COM") == 2.5

    def test_thy_us_hiccup_over_2_5(self):
        assert apply_rounding("THY", 2.6, destination="USA", customer_email="ops@hiccup.com") == 3.0

    # THY Priority 3: AU or US non-hiccup
    def test_thy_us_nonhiccup_under_0_5(self):
        assert apply_rounding("THY", 0.3, destination="USA") == 0.3

    def test_thy_us_nonhiccup_0_5_to_3(self):
        assert apply_rounding("THY", 1.2, destination="US") == 1.5

    def test_thy_au_nonhiccup_over_3(self):
        assert apply_rounding("THY", 3.1, destination="AVUSTRALYA") == 4.0

    # THY Priority 4: catch-all
    def test_thy_catchall_under_10(self):
        assert apply_rounding("THY", 7.3, destination="DE") == 7.5

    def test_thy_catchall_over_10(self):
        assert apply_rounding("THY", 10.5, destination="FR") == 11.0

    def test_thy_no_destination_falls_to_catchall(self):
        assert apply_rounding("THY", 7.3) == 7.5

    # THY country alias
    def test_thy_ingiltere_alias(self):
        assert apply_rounding("THY", 4.3, destination="İNGİLTERE", customer_email="ops@hiccup.com") == 4.5

    def test_thy_amerika_alias(self):
        assert apply_rounding("THY", 2.1, destination="AMERİKA", customer_email="ops@hiccup.com") == 2.5

    # PTT
    def test_ptt_under_0_5(self):
        assert apply_rounding("PTT", 0.3) == 0.3

    def test_ptt_over_0_5(self):
        assert apply_rounding("PTT", 0.7) == 1.0

    def test_ptt_exact_0_5(self):
        assert apply_rounding("PTT", 0.5) == 0.5

    # Aramex
    def test_aramex_under_10(self):
        assert apply_rounding("Aramex", 5.3) == 5.5

    def test_aramex_over_10(self):
        assert apply_rounding("Aramex", 10.3) == 11.0

    # None weight
    def test_none_weight(self):
        assert apply_rounding("UPS", None) is None
