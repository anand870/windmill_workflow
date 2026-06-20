"""Tests for gold_price_provider.py — fallback chains and parsing logic."""
import pytest
from unittest.mock import patch, MagicMock

from f.gold.gold_price_provider import (
    TROY_OZ_TO_GRAM,
    _fetch_usd_current_goldapi,
    _fetch_usd_current_metalsdev,
    _fetch_usd_current_freegoldapi,
    fetch_usd_current,
    fetch_aed_current,
    fetch_inr_current,
    fetch_khaleejtimes_history,
    fetch_inr_history_nse,
)


# ── _fetch_usd_current_goldapi ────────────────────────────────────────────────

class TestFetchUSDCurrentGoldAPI:
    def _mock_response(self, data):
        resp = MagicMock()
        resp.json.return_value = data
        return resp

    def test_uses_price_gram_24k_when_present(self):
        resp = self._mock_response({"price_gram_24k": 60.5, "price": 1882.0})
        with patch("f.gold.gold_price_provider.requests.get", return_value=resp):
            result = _fetch_usd_current_goldapi("key")
        assert result == pytest.approx(60.5)

    def test_falls_back_to_troy_oz_price(self):
        resp = self._mock_response({"price_gram_24k": None, "price": 31.1035 * 2})
        with patch("f.gold.gold_price_provider.requests.get", return_value=resp):
            result = _fetch_usd_current_goldapi("key")
        assert result == pytest.approx(2.0)


# ── _fetch_usd_current_metalsdev ─────────────────────────────────────────────

class TestFetchUSDCurrentMetalsDev:
    def test_extracts_gold_price(self):
        resp = MagicMock()
        resp.json.return_value = {"metals": {"gold": "58.75"}}
        with patch("f.gold.gold_price_provider.requests.get", return_value=resp):
            result = _fetch_usd_current_metalsdev("key")
        assert result == pytest.approx(58.75)


# ── fetch_usd_current fallback chain ─────────────────────────────────────────

class TestFetchUSDCurrentFallback:
    def test_goldapi_wins_when_key_provided(self):
        with patch("f.gold.gold_price_provider._fetch_usd_current_goldapi", return_value=60.0) as mock_ga, \
             patch("f.gold.gold_price_provider._fetch_usd_current_metalsdev") as mock_md, \
             patch("f.gold.gold_price_provider._fetch_usd_current_freegoldapi") as mock_fg, \
             patch("f.gold.gold_price_provider._fetch_usd_current_yahoo") as mock_yf:
            price, source = fetch_usd_current("fg_key", "md_key", "ga_key")
        assert price == pytest.approx(60.0)
        assert source == "goldapi"
        mock_md.assert_not_called()
        mock_fg.assert_not_called()
        mock_yf.assert_not_called()

    def test_metalsdev_used_when_goldapi_fails(self):
        with patch("f.gold.gold_price_provider._fetch_usd_current_goldapi", side_effect=Exception("fail")), \
             patch("f.gold.gold_price_provider._fetch_usd_current_metalsdev", return_value=59.0) as mock_md, \
             patch("f.gold.gold_price_provider._fetch_usd_current_freegoldapi") as mock_fg, \
             patch("f.gold.gold_price_provider._fetch_usd_current_yahoo") as mock_yf:
            price, source = fetch_usd_current("fg_key", "md_key", "ga_key")
        assert price == pytest.approx(59.0)
        assert source == "metalsdev"
        mock_fg.assert_not_called()
        mock_yf.assert_not_called()

    def test_freegoldapi_used_when_higher_priority_fails(self):
        with patch("f.gold.gold_price_provider._fetch_usd_current_goldapi", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_metalsdev", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_freegoldapi", return_value=58.0), \
             patch("f.gold.gold_price_provider._fetch_usd_current_yahoo") as mock_yf:
            price, source = fetch_usd_current("fg_key", "md_key", "ga_key")
        assert price == pytest.approx(58.0)
        assert source == "freegoldapi"
        mock_yf.assert_not_called()

    def test_yahoo_fallback_last_resort(self):
        with patch("f.gold.gold_price_provider._fetch_usd_current_goldapi", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_metalsdev", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_freegoldapi", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_yahoo", return_value=57.5):
            price, source = fetch_usd_current("fg_key", "md_key", "ga_key")
        assert price == pytest.approx(57.5)
        assert source == "yfinance"

    def test_all_fail_raises_runtime_error(self):
        with patch("f.gold.gold_price_provider._fetch_usd_current_goldapi", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_metalsdev", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_freegoldapi", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_usd_current_yahoo", side_effect=Exception("yf fail")):
            with pytest.raises(RuntimeError, match="All USD current providers failed"):
                fetch_usd_current("fg_key", "md_key", "ga_key")

    def test_no_api_keys_skips_to_yahoo(self):
        with patch("f.gold.gold_price_provider._fetch_usd_current_yahoo", return_value=57.0) as mock_yf, \
             patch("f.gold.gold_price_provider._fetch_usd_current_goldapi") as mock_ga, \
             patch("f.gold.gold_price_provider._fetch_usd_current_metalsdev") as mock_md, \
             patch("f.gold.gold_price_provider._fetch_usd_current_freegoldapi") as mock_fg:
            price, source = fetch_usd_current("", "", "")
        assert source == "yfinance"
        mock_ga.assert_not_called()
        mock_md.assert_not_called()
        mock_fg.assert_not_called()


# ── fetch_aed_current fallback chain ─────────────────────────────────────────

class TestFetchAEDCurrentFallback:
    def test_igold_wins(self):
        igold_prices = {"24K": 230.0, "22K": 211.0, "21K": 201.0, "18K": 172.5}
        with patch("f.gold.gold_price_provider._fetch_aed_igold", return_value=igold_prices), \
             patch("f.gold.gold_price_provider._fetch_aed_dcog") as mock_dcog:
            p24, supplied, source, price_type = fetch_aed_current(100.0, "", "", "")
        assert p24 == pytest.approx(230.0)
        assert source == "igold"
        assert price_type == "local"
        mock_dcog.assert_not_called()

    def test_dcog_used_when_igold_fails(self):
        dcog_prices = {"24K": 231.0, "22K": 212.0, "21K": 202.0, "18K": 173.0}
        with patch("f.gold.gold_price_provider._fetch_aed_igold", side_effect=Exception("fail")), \
             patch("f.gold.gold_price_provider._fetch_aed_dcog", return_value=dcog_prices):
            p24, supplied, source, price_type = fetch_aed_current(100.0, "", "", "")
        assert p24 == pytest.approx(231.0)
        assert source == "dcog"
        assert price_type == "local"

    def test_usd_conversion_fallback(self):
        with patch("f.gold.gold_price_provider._fetch_aed_igold", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_aed_dcog", side_effect=Exception), \
             patch("f.gold.gold_price_provider.get_fx_rate", return_value=3.67):
            p24, supplied, source, price_type = fetch_aed_current(100.0, "", "", "")
        assert p24 == pytest.approx(367.0)
        assert supplied is None
        assert source == "usd_conversion"
        assert price_type == "converted"


# ── fetch_inr_current fallback chain ─────────────────────────────────────────

class TestFetchINRCurrentFallback:
    def test_khaleejtimes_wins(self):
        with patch("f.gold.gold_price_provider._fetch_inr_khaleejtimes", return_value=7500.0), \
             patch("f.gold.gold_price_provider._fetch_inr_metalsdev") as mock_md:
            price, source, price_type = fetch_inr_current(100.0, "md_key")
        assert price == pytest.approx(7500.0)
        assert source == "khaleejtimes"
        assert price_type == "local"
        mock_md.assert_not_called()

    def test_metalsdev_used_when_khaleejtimes_fails(self):
        with patch("f.gold.gold_price_provider._fetch_inr_khaleejtimes", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_inr_metalsdev", return_value=7400.0):
            price, source, price_type = fetch_inr_current(100.0, "md_key")
        assert price == pytest.approx(7400.0)
        assert source == "metalsdev_inr"
        assert price_type == "local"

    def test_usd_conversion_last_resort(self):
        with patch("f.gold.gold_price_provider._fetch_inr_khaleejtimes", side_effect=Exception), \
             patch("f.gold.gold_price_provider.get_fx_rate", return_value=83.5):
            price, source, price_type = fetch_inr_current(100.0, "")
        assert price == pytest.approx(8350.0)
        assert source == "usd_conversion"
        assert price_type == "converted"

    def test_no_metalsdev_key_skips_metalsdev(self):
        with patch("f.gold.gold_price_provider._fetch_inr_khaleejtimes", side_effect=Exception), \
             patch("f.gold.gold_price_provider._fetch_inr_metalsdev") as mock_md, \
             patch("f.gold.gold_utils.get_fx_rate", return_value=83.0):
            fetch_inr_current(100.0, "")
        mock_md.assert_not_called()


# ── fetch_khaleejtimes_history ────────────────────────────────────────────────

class TestFetchKhaaleejTimesHistory:
    def _make_response(self, country="uae"):
        resp = MagicMock()
        resp.json.return_value = {
            "status": True,
            "data": {
                "gold": {
                    "24k": [{"x": "2024-01-15", "y": "230.50"}, {"x": "2024-01-16", "y": "231.00"}],
                    "22k": [{"x": "2024-01-15", "y": "211.30"}, {"x": "2024-01-16", "y": "211.80"}],
                    "21k": [{"x": "2024-01-15", "y": "201.70"}, {"x": "2024-01-16", "y": "202.10"}],
                    "18k": [{"x": "2024-01-15", "y": "172.90"}, {"x": "2024-01-16", "y": "173.30"}],
                }
            },
        }
        return resp

    def test_returns_dict_keyed_by_date(self):
        with patch("f.gold.gold_price_provider.requests.get", return_value=self._make_response()):
            result = fetch_khaleejtimes_history("uae", 7)
        assert "2024-01-15" in result
        assert "2024-01-16" in result

    def test_all_carats_populated(self):
        with patch("f.gold.gold_price_provider.requests.get", return_value=self._make_response()):
            result = fetch_khaleejtimes_history("uae", 7)
        assert set(result["2024-01-15"].keys()) == {"24K", "22K", "21K", "18K"}

    def test_prices_parsed_correctly(self):
        with patch("f.gold.gold_price_provider.requests.get", return_value=self._make_response()):
            result = fetch_khaleejtimes_history("uae", 7)
        assert result["2024-01-15"]["24K"] == pytest.approx(230.50)

    def test_raises_on_api_error(self):
        resp = MagicMock()
        resp.json.return_value = {"status": False}
        with patch("f.gold.gold_price_provider.requests.get", return_value=resp):
            with pytest.raises(ValueError, match="KhaleejTimes history error"):
                fetch_khaleejtimes_history("uae", 7)

    def test_raises_when_no_data(self):
        resp = MagicMock()
        resp.json.return_value = {
            "status": True,
            "data": {"gold": {"24k": [], "22k": [], "21k": [], "18k": []}},
        }
        with patch("f.gold.gold_price_provider.requests.get", return_value=resp):
            with pytest.raises(ValueError, match="no data parsed"):
                fetch_khaleejtimes_history("uae", 7)

    def test_zero_prices_skipped(self):
        resp = MagicMock()
        resp.json.return_value = {
            "status": True,
            "data": {
                "gold": {
                    "24k": [{"x": "2024-01-15", "y": "0"}],
                    "22k": [], "21k": [], "18k": [],
                }
            },
        }
        with patch("f.gold.gold_price_provider.requests.get", return_value=resp):
            with pytest.raises(ValueError):
                fetch_khaleejtimes_history("uae", 7)


# ── fetch_inr_history_nse ─────────────────────────────────────────────────────

class TestFetchINRHistoryNSE:
    def _make_nse_response(self):
        resp = MagicMock()
        resp.json.return_value = {
            "data": [
                {"UpdatedDate": "15-JAN-2024", "SpotPrice2": "7520.5", "SpotPrice1": "7510.0"},
                {"UpdatedDate": "16-JAN-2024", "SpotPrice2": "7530.0", "SpotPrice1": "7525.0"},
                {"UpdatedDate": "17-JAN-2024", "SpotPrice2": "0", "SpotPrice1": "7540.0"},
            ]
        }
        return resp

    def test_returns_dict_keyed_by_iso_date(self):
        session_mock = MagicMock()
        session_mock.get.return_value = self._make_nse_response()
        with patch("f.gold.gold_price_provider.requests.Session", return_value=session_mock):
            result = fetch_inr_history_nse("2024-01-15", "2024-01-17")
        assert "2024-01-15" in result
        assert "2024-01-16" in result

    def test_spotprice2_preferred_over_spotprice1(self):
        session_mock = MagicMock()
        session_mock.get.return_value = self._make_nse_response()
        with patch("f.gold.gold_price_provider.requests.Session", return_value=session_mock):
            result = fetch_inr_history_nse("2024-01-15", "2024-01-17")
        assert result["2024-01-15"] == pytest.approx(7520.5)

    def test_falls_back_to_spotprice1_when_spotprice2_zero(self):
        session_mock = MagicMock()
        session_mock.get.return_value = self._make_nse_response()
        with patch("f.gold.gold_price_provider.requests.Session", return_value=session_mock):
            result = fetch_inr_history_nse("2024-01-15", "2024-01-17")
        assert result["2024-01-17"] == pytest.approx(7540.0)

    def test_invalid_date_format_skipped(self):
        resp = MagicMock()
        resp.json.return_value = {
            "data": [
                {"UpdatedDate": "INVALID", "SpotPrice2": "7500.0"},
                {"UpdatedDate": "15-JAN-2024", "SpotPrice2": "7520.0"},
            ]
        }
        session_mock = MagicMock()
        session_mock.get.return_value = resp
        with patch("f.gold.gold_price_provider.requests.Session", return_value=session_mock):
            result = fetch_inr_history_nse("2024-01-15", "2024-01-17")
        assert "2024-01-15" in result
        assert len(result) == 1

    def test_empty_data_returns_empty_dict(self):
        resp = MagicMock()
        resp.json.return_value = {"data": []}
        session_mock = MagicMock()
        session_mock.get.return_value = resp
        with patch("f.gold.gold_price_provider.requests.Session", return_value=session_mock):
            result = fetch_inr_history_nse("2024-01-15", "2024-01-17")
        assert result == {}

    def test_no_duplicate_dates(self):
        resp = MagicMock()
        resp.json.return_value = {
            "data": [
                {"UpdatedDate": "15-JAN-2024", "SpotPrice2": "7520.0"},
                {"UpdatedDate": "15-JAN-2024", "SpotPrice2": "7530.0"},  # duplicate
            ]
        }
        session_mock = MagicMock()
        session_mock.get.return_value = resp
        with patch("f.gold.gold_price_provider.requests.Session", return_value=session_mock):
            result = fetch_inr_history_nse("2024-01-15", "2024-01-17")
        assert len(result) == 1
        assert result["2024-01-15"] == pytest.approx(7520.0)  # first wins


# ── TROY_OZ_TO_GRAM constant ─────────────────────────────────────────────────

def test_troy_oz_to_gram_constant():
    assert TROY_OZ_TO_GRAM == pytest.approx(31.1035)
