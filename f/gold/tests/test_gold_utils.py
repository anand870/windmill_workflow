"""Tests for gold_utils.py — build_rows, compute_indicators, MA, RSI."""
import pytest
from f.gold.gold_utils import (
    PURITY,
    TROY_OZ_TO_GRAM,
    build_rows,
    compute_indicators,
    _compute_ma,
    _compute_rsi14,
)

CARATS = list(PURITY.keys())  # ["24K", "22K", "21K", "18K"]


# ── build_rows ────────────────────────────────────────────────────────────────

class TestBuildRows:
    def test_returns_four_rows(self):
        rows = build_rows("2024-01-15", "USD", 60.0, None, None, None, "test", "local")
        assert len(rows) == 4

    def test_all_carats_present(self):
        rows = build_rows("2024-01-15", "USD", 60.0, None, None, None, "test", "local")
        assert {r["carat"] for r in rows} == set(CARATS)

    def test_purity_math(self):
        price_24k = 100.0
        rows = build_rows("2024-01-15", "USD", price_24k, None, None, None, "test", "local")
        by_carat = {r["carat"]: r for r in rows}
        assert by_carat["24K"]["price"] == pytest.approx(100.0)
        assert by_carat["22K"]["price"] == pytest.approx(91.7)
        assert by_carat["21K"]["price"] == pytest.approx(87.5)
        assert by_carat["18K"]["price"] == pytest.approx(75.0)

    def test_24k_calculated_false(self):
        rows = build_rows("2024-01-15", "USD", 60.0, None, None, None, "test", "local")
        by_carat = {r["carat"]: r for r in rows}
        assert by_carat["24K"]["calculated"] is False

    def test_lower_carats_calculated_true_by_default(self):
        rows = build_rows("2024-01-15", "USD", 60.0, None, None, None, "test", "local")
        by_carat = {r["carat"]: r for r in rows}
        for carat in ["22K", "21K", "18K"]:
            assert by_carat[carat]["calculated"] is True

    def test_supplied_carats_sets_calculated_false(self):
        supplied = {"24K": 100.0, "22K": 92.0, "21K": 88.0, "18K": 76.0}
        rows = build_rows("2024-01-15", "AED", 100.0, None, None, None, "igold", "local",
                          supplied_carats=supplied)
        by_carat = {r["carat"]: r for r in rows}
        for carat in CARATS:
            assert by_carat[carat]["calculated"] is False

    def test_supplied_carats_uses_provided_prices(self):
        supplied = {"22K": 92.5, "21K": 88.1}
        rows = build_rows("2024-01-15", "AED", 100.0, None, None, None, "igold", "local",
                          supplied_carats=supplied)
        by_carat = {r["carat"]: r for r in rows}
        assert by_carat["22K"]["price"] == pytest.approx(92.5)
        assert by_carat["21K"]["price"] == pytest.approx(88.1)
        # 18K not supplied → computed, calculated=True
        assert by_carat["18K"]["price"] == pytest.approx(75.0)
        assert by_carat["18K"]["calculated"] is True

    def test_ohlc_scales_with_purity(self):
        rows = build_rows("2024-01-15", "USD", 100.0, 98.0, 102.0, 97.0, "test", "local")
        by_carat = {r["carat"]: r for r in rows}
        assert by_carat["22K"]["open"] == pytest.approx(98.0 * 0.917)
        assert by_carat["22K"]["high"] == pytest.approx(102.0 * 0.917)
        assert by_carat["22K"]["low"] == pytest.approx(97.0 * 0.917)

    def test_ohlc_none_when_not_provided(self):
        rows = build_rows("2024-01-15", "USD", 100.0, None, None, None, "test", "local")
        for row in rows:
            assert row["open"] is None
            assert row["high"] is None
            assert row["low"] is None

    def test_metadata_fields(self):
        rows = build_rows("2024-01-15", "INR", 7000.0, None, None, None, "khaleejtimes", "local")
        for row in rows:
            assert row["date"] == "2024-01-15"
            assert row["currency"] == "INR"
            assert row["source"] == "khaleejtimes"
            assert row["price_type"] == "local"

    def test_converted_price_type(self):
        rows = build_rows("2024-01-15", "AED", 230.0, None, None, None, "usd_conversion", "converted")
        for row in rows:
            assert row["price_type"] == "converted"


# ── _compute_ma ───────────────────────────────────────────────────────────────

class TestComputeMA:
    def test_insufficient_data_returns_none(self):
        prices = list(range(1, 7))  # 6 prices, need 7 for MA7
        assert _compute_ma(prices, 7, 5) is None

    def test_exact_window(self):
        prices = [1.0] * 7
        result = _compute_ma(prices, 7, 6)
        assert result == pytest.approx(1.0)

    def test_correct_average(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        result = _compute_ma(prices, 7, 6)
        assert result == pytest.approx(4.0)

    def test_sliding_window(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
        # MA7 at index 7 should use prices[1..7] = [20,30,40,50,60,70,80]
        result = _compute_ma(prices, 7, 7)
        assert result == pytest.approx(50.0)

    def test_ma30_needs_30_prices(self):
        prices = list(range(29))
        assert _compute_ma(prices, 30, 28) is None
        prices = list(range(30))
        assert _compute_ma(prices, 30, 29) is not None


# ── _compute_rsi14 ────────────────────────────────────────────────────────────

class TestComputeRSI14:
    def test_insufficient_data_all_none(self):
        prices = [100.0] * 14  # need ≥ 15
        result = _compute_rsi14(prices)
        assert all(v is None for v in result)

    def test_returns_same_length(self):
        prices = list(range(1, 31))
        result = _compute_rsi14(prices)
        assert len(result) == 30

    def test_first_valid_at_index_14(self):
        prices = [100.0 + i for i in range(30)]
        result = _compute_rsi14(prices)
        assert result[13] is None
        assert result[14] is not None

    def test_rsi_bounds(self):
        prices = [100.0 + i * 0.5 for i in range(50)]
        result = _compute_rsi14(prices)
        for v in result:
            if v is not None:
                assert 0.0 <= v <= 100.0

    def test_all_gains_rsi_100(self):
        # Strictly increasing prices → avg_loss = 0 → RSI = 100
        prices = [float(i) for i in range(1, 20)]
        result = _compute_rsi14(prices)
        assert result[14] == pytest.approx(100.0)

    def test_all_losses_rsi_0(self):
        # Strictly decreasing prices → avg_gain = 0 → RSI ≈ 0
        prices = [float(100 - i) for i in range(20)]
        result = _compute_rsi14(prices)
        assert result[14] == pytest.approx(0.0)

    def test_wilder_smoothing_continues(self):
        prices = [100.0 + (i % 3) * 2 for i in range(30)]
        result = _compute_rsi14(prices)
        # All values after index 14 should be non-None
        for v in result[14:]:
            assert v is not None


# ── compute_indicators ────────────────────────────────────────────────────────

class TestComputeIndicators:
    def _make_rows(self, n, start_price=100.0, step=0.5):
        from datetime import date, timedelta
        base = date(2024, 1, 1)
        return [(str(base + timedelta(days=i)), start_price + i * step) for i in range(n)]

    def test_empty_input(self):
        assert compute_indicators([]) == []

    def test_too_few_rows_no_indicators(self):
        # With 5 rows only, nothing qualifies (need at least 7 for MA7)
        rows = self._make_rows(5)
        result = compute_indicators(rows)
        assert result == []

    def test_ma7_available_from_index_6(self):
        rows = self._make_rows(10)
        result = compute_indicators(rows)
        dates = {r["date"] for r in result}
        # Index 6 = day 7 (first MA7-eligible)
        from datetime import date, timedelta
        day7 = str(date(2024, 1, 1) + timedelta(days=6))
        assert day7 in dates

    def test_correct_ma7_value(self):
        prices = [10.0] * 100
        rows = [(f"2024-01-{i+1:02d}", 10.0) for i in range(100)]
        result = compute_indicators(rows)
        # All prices equal → MA7 = 10.0
        for r in result:
            if r["ma7"] is not None:
                assert r["ma7"] == pytest.approx(10.0)

    def test_ma30_none_before_30_rows(self):
        rows = self._make_rows(30)
        result = compute_indicators(rows)
        from datetime import date, timedelta
        day29 = str(date(2024, 1, 1) + timedelta(days=28))
        row_29 = next((r for r in result if r["date"] == day29), None)
        if row_29:
            assert row_29["ma30"] is None

    def test_ma90_none_before_90_rows(self):
        rows = self._make_rows(100)
        result = compute_indicators(rows)
        from datetime import date, timedelta
        day89 = str(date(2024, 1, 1) + timedelta(days=88))
        row = next((r for r in result if r["date"] == day89), None)
        if row:
            assert row["ma90"] is None

    def test_rsi14_available_after_14_rows(self):
        rows = self._make_rows(50)
        result = compute_indicators(rows)
        from datetime import date, timedelta
        day15 = str(date(2024, 1, 1) + timedelta(days=14))
        row = next((r for r in result if r["date"] == day15), None)
        assert row is not None
        assert row["rsi14"] is not None

    def test_result_dict_keys(self):
        rows = self._make_rows(20)
        result = compute_indicators(rows)
        for r in result:
            assert set(r.keys()) == {"date", "ma7", "ma30", "ma90", "rsi14"}

    def test_200_rows_all_indicators_present_for_last(self):
        rows = self._make_rows(200)
        result = compute_indicators(rows)
        last = result[-1]
        assert last["ma7"] is not None
        assert last["ma30"] is not None
        assert last["ma90"] is not None
        assert last["rsi14"] is not None
