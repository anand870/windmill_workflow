"""Tests for flow step helper functions (pure logic, no DB/network)."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock


# ── daily_refresh / step2 helpers ─────────────────────────────────────────────

class TestWeekdayDatesInWindow:
    def _call(self, history_days, today_override=None):
        with patch("f.gold.daily_refresh__flow.step2_history_gap_fill.datetime") as mock_dt:
            today = today_override or date(2024, 6, 3)  # Monday
            mock_dt.today.return_value = MagicMock(date=lambda: today)
            mock_dt.strptime = __import__("datetime").datetime.strptime
            from f.gold.daily_refresh__flow.step2_history_gap_fill import _weekday_dates_in_window
            return _weekday_dates_in_window(history_days)

    def test_returns_set(self):
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _weekday_dates_in_window
        result = _weekday_dates_in_window(5)
        assert isinstance(result, set)

    def test_no_weekends_in_result(self):
        # Use a known Monday so we can reason about what dates fall in window
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _weekday_dates_in_window
        # Run with a generous window; spot-check no date is a weekend
        result = _weekday_dates_in_window(10)
        for d_str in result:
            d = date.fromisoformat(d_str)
            assert d.weekday() < 5, f"{d_str} is a weekend day"

    def test_excludes_today(self):
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _weekday_dates_in_window
        today_str = date.today().strftime("%Y-%m-%d")
        result = _weekday_dates_in_window(5)
        assert today_str not in result

    def test_window_respects_days(self):
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _weekday_dates_in_window
        result = _weekday_dates_in_window(1)
        # At most 1 date (yesterday if weekday)
        assert len(result) <= 1

    def test_zero_days_returns_empty(self):
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _weekday_dates_in_window
        result = _weekday_dates_in_window(0)
        assert result == set()


class TestKtRangeDays:
    def test_result_positive(self):
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _kt_range_days
        missing = {"2024-01-10", "2024-01-11"}
        result = _kt_range_days(missing)
        assert result > 0

    def test_older_date_gives_larger_range(self):
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _kt_range_days
        recent = _kt_range_days({date.today().strftime("%Y-%m-%d")})
        older = _kt_range_days({"2020-01-01"})
        assert older > recent

    def test_adds_buffer(self):
        # Result should be days-since + 2
        from f.gold.daily_refresh__flow.step2_history_gap_fill import _kt_range_days
        target = date.today() - timedelta(days=5)
        result = _kt_range_days({target.strftime("%Y-%m-%d")})
        assert result == pytest.approx(7, abs=1)  # 5 days + 2


# ── get_fx_rate caching ───────────────────────────────────────────────────────

class TestGetFXRate:
    def setup_method(self):
        import f.gold.gold_utils as gu
        gu._fx_cache.clear()

    def test_returns_rate_from_api(self):
        resp = MagicMock()
        resp.json.return_value = {"rates": {"AED": 3.67}}
        # requests is imported lazily inside get_fx_rate — patch at the top-level module
        with patch("requests.get", return_value=resp):
            from f.gold.gold_utils import get_fx_rate
            result = get_fx_rate("AED")
        assert result == pytest.approx(3.67)

    def test_caches_result(self):
        resp = MagicMock()
        resp.json.return_value = {"rates": {"INR": 83.5}}
        with patch("requests.get", return_value=resp) as mock_get:
            from f.gold.gold_utils import get_fx_rate
            get_fx_rate("INR")
            get_fx_rate("INR")  # second call should use cache
        assert mock_get.call_count == 1

    def test_yfinance_fallback_on_api_failure(self):
        # yfinance is also imported lazily — patch at the top-level module
        with patch("requests.get", side_effect=Exception("api down")), \
             patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.fast_info = {"last_price": 83.2}
            from f.gold.gold_utils import get_fx_rate
            result = get_fx_rate("INR")
        assert result == pytest.approx(83.2)

    def test_raises_when_all_fail(self):
        with patch("requests.get", side_effect=Exception("fail")), \
             patch("yfinance.Ticker", side_effect=Exception("yf fail")):
            from f.gold.gold_utils import get_fx_rate
            with pytest.raises(RuntimeError, match="Could not fetch FX rate"):
                get_fx_rate("XYZ")


# ── build_rows edge cases for step logic ─────────────────────────────────────

class TestBuildRowsIntegration:
    """Higher-level checks that verify how steps use build_rows."""

    def test_aed_conversion_price_correct(self):
        from f.gold.gold_utils import build_rows
        usd = 100.0
        fx = 3.67
        rows = build_rows("2024-01-15", "AED", usd * fx, None, None, None,
                          "usd_conversion", "converted")
        by_carat = {r["carat"]: r for r in rows}
        assert by_carat["24K"]["price"] == pytest.approx(367.0)
        assert by_carat["24K"]["price_type"] == "converted"

    def test_inr_conversion_price_correct(self):
        from f.gold.gold_utils import build_rows
        usd = 100.0
        fx = 83.5
        rows = build_rows("2024-01-15", "INR", usd * fx, None, None, None,
                          "usd_conversion", "converted")
        by_carat = {r["carat"]: r for r in rows}
        assert by_carat["24K"]["price"] == pytest.approx(8350.0)

    def test_ohlc_conversion_scales_correctly(self):
        from f.gold.gold_utils import build_rows
        fx = 3.67
        rows = build_rows(
            "2024-01-15", "AED",
            100.0 * fx,
            98.0 * fx,   # open
            102.0 * fx,  # high
            97.0 * fx,   # low
            "usd_conversion", "converted",
        )
        by_carat = {r["carat"]: r for r in rows}
        assert by_carat["22K"]["open"] == pytest.approx(98.0 * fx * 0.917)
        assert by_carat["22K"]["high"] == pytest.approx(102.0 * fx * 0.917)
        assert by_carat["22K"]["low"] == pytest.approx(97.0 * fx * 0.917)
