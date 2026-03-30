import datetime
from unittest.mock import patch, MagicMock
import urllib.error

from src.tcmb import fetch_tcmb_rate, _parse_rates_xml, clear_cache


SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="28.03.2025" Date="03/28/2025">
    <Currency CrossOrder="0" Kod="USD" CurrencyCode="USD">
        <Unit>1</Unit>
        <Isim>ABD DOLARI</Isim>
        <CurrencyName>US DOLLAR</CurrencyName>
        <ForexBuying>36.1000</ForexBuying>
        <ForexSelling>36.1500</ForexSelling>
        <BanknoteBuying>36.0500</BanknoteBuying>
        <BanknoteSelling>36.2000</BanknoteSelling>
    </Currency>
    <Currency CrossOrder="1" Kod="EUR" CurrencyCode="EUR">
        <Unit>1</Unit>
        <Isim>EURO</Isim>
        <CurrencyName>EURO</CurrencyName>
        <ForexBuying>39.2000</ForexBuying>
        <ForexSelling>39.2800</ForexSelling>
        <BanknoteBuying>39.1500</BanknoteBuying>
        <BanknoteSelling>39.3300</BanknoteSelling>
    </Currency>
    <Currency CrossOrder="9" Kod="XDR" CurrencyCode="XDR">
        <Unit>1</Unit>
        <Isim>OZEL CEKME HAKKI (SDR)</Isim>
        <CurrencyName>SPECIAL DRAWING RIGHT (SDR)</CurrencyName>
        <ForexBuying></ForexBuying>
        <ForexSelling></ForexSelling>
    </Currency>
</Tarih_Date>
"""


class TestParseRatesXml:
    def test_extracts_usd(self):
        rates = _parse_rates_xml(SAMPLE_XML)
        assert rates["USD"] == 36.15

    def test_extracts_eur(self):
        rates = _parse_rates_xml(SAMPLE_XML)
        assert rates["EUR"] == 39.28

    def test_skips_empty_forex_selling(self):
        rates = _parse_rates_xml(SAMPLE_XML)
        assert "XDR" not in rates

    def test_unknown_currency_not_in_result(self):
        rates = _parse_rates_xml(SAMPLE_XML)
        assert rates.get("GBP") is None

    def test_malformed_xml(self):
        rates = _parse_rates_xml(b"<not valid xml")
        assert rates == {}

    def test_empty_input(self):
        rates = _parse_rates_xml(b"")
        assert rates == {}


class TestFetchTcmbRate:
    def setup_method(self):
        clear_cache()

    def test_try_returns_one(self):
        assert fetch_tcmb_rate(datetime.date(2025, 3, 28), "TRY") == 1.0

    def test_tl_returns_one(self):
        assert fetch_tcmb_rate(datetime.date(2025, 3, 28), "TL") == 1.0

    @patch("src.tcmb.urllib.request.urlopen")
    def test_successful_fetch(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_XML
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        rate = fetch_tcmb_rate(datetime.date(2025, 3, 28), "USD")
        assert rate == 36.15
        mock_urlopen.assert_called_once()

    @patch("src.tcmb.urllib.request.urlopen")
    def test_cache_prevents_second_call(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_XML
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        fetch_tcmb_rate(datetime.date(2025, 3, 28), "USD")
        fetch_tcmb_rate(datetime.date(2025, 3, 28), "EUR")
        assert mock_urlopen.call_count == 1

    @patch("src.tcmb.urllib.request.urlopen")
    def test_404_falls_back_to_previous_day(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_XML
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        # First call (Saturday) -> 404, second call (Friday) -> success
        mock_urlopen.side_effect = [
            urllib.error.HTTPError(None, 404, "Not Found", {}, None),
            mock_response,
        ]

        rate = fetch_tcmb_rate(datetime.date(2025, 3, 29), "USD")  # Saturday
        assert rate == 36.15
        assert mock_urlopen.call_count == 2

    @patch("src.tcmb.urllib.request.urlopen")
    def test_network_error_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        rate = fetch_tcmb_rate(datetime.date(2025, 3, 28), "USD")
        assert rate is None

    @patch("src.tcmb.urllib.request.urlopen")
    def test_unknown_currency_returns_none(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_XML
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        rate = fetch_tcmb_rate(datetime.date(2025, 3, 28), "XYZ")
        assert rate is None
