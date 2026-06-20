"""
Live integration tests — hit real external URLs.

Run with:
    python -m pytest f/gold/tests/test_live_apis.py -v -m live

Or alongside unit tests (they're always collected but marked):
    python -m pytest f/gold/tests/ -v

Disabled APIs (known broken):
  - Metals.dev   — marked skip, re-enable when subscription is active
  - FreeGoldAPI  — marked skip, re-enable when subscription is active

Key-gated APIs:
  - GoldAPI      — skipped unless GOLDAPI_KEY env var is set

All other providers are expected to work without credentials.
"""

import os
import pytest
from datetime import date, timedelta

# ── helpers ───────────────────────────────────────────────────────────────────

def _recent_weekday(offset: int = 2) -> str:
    """Return a recent weekday date string, going back `offset` weekdays."""
    d = date.today()
    count = 0
    while count < offset:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return d.strftime("%Y-%m-%d")


def _assert_positive_price(price, label="price"):
    assert isinstance(price, float), f"{label} must be float, got {type(price)}"
    assert price > 0, f"{label} must be positive, got {price}"


def _assert_carat_dict(d: dict, label="carat dict"):
    assert isinstance(d, dict), f"{label} must be dict"
    assert "24K" in d, f"{label} missing 24K"
    for carat, price in d.items():
        assert price > 0, f"{label}[{carat}] must be positive"


# ── mark ─────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.live


# ── FX rate (open.er-api.com → yfinance fallback) ────────────────────────────

class TestLiveFXRate:
    def setup_method(self):
        import f.gold.gold_utils as gu
        gu._fx_cache.clear()

    def test_aed_rate_reasonable(self):
        from f.gold.gold_utils import get_fx_rate
        rate = get_fx_rate("AED")
        _assert_positive_price(rate, "USD/AED")
        # AED is pegged near 3.67
        assert 3.5 < rate < 3.9, f"USD/AED rate {rate} looks wrong"

    def test_inr_rate_reasonable(self):
        from f.gold.gold_utils import get_fx_rate
        rate = get_fx_rate("INR")
        _assert_positive_price(rate, "USD/INR")
        assert 70 < rate < 110, f"USD/INR rate {rate} looks wrong"

    def test_cache_returns_same_value(self):
        from f.gold.gold_utils import get_fx_rate
        r1 = get_fx_rate("AED")
        r2 = get_fx_rate("AED")
        assert r1 == r2


# ── USD current ───────────────────────────────────────────────────────────────

class TestLiveUSDCurrent:
    def test_yahoo_finance(self):
        from f.gold.gold_price_provider import _fetch_usd_current_yahoo
        price = _fetch_usd_current_yahoo()
        _assert_positive_price(price, "USD/g via yfinance")
        # Gold has been in the $50–$120/g range historically
        assert 40 < price < 200, f"USD/g {price} looks wrong"

    @pytest.mark.skipif(
        not os.environ.get("GOLDAPI_KEY"),
        reason="GOLDAPI_KEY env var not set",
    )
    def test_goldapi(self):
        from f.gold.gold_price_provider import _fetch_usd_current_goldapi
        price = _fetch_usd_current_goldapi(os.environ["GOLDAPI_KEY"])
        _assert_positive_price(price, "USD/g via GoldAPI")
        assert 40 < price < 200

    @pytest.mark.skip(reason="Metals.dev subscription not active")
    def test_metalsdev(self):
        from f.gold.gold_price_provider import _fetch_usd_current_metalsdev
        price = _fetch_usd_current_metalsdev(os.environ.get("METALSDEV_KEY", ""))
        _assert_positive_price(price, "USD/g via Metals.dev")

    @pytest.mark.skip(reason="FreeGoldAPI subscription not active")
    def test_freegoldapi(self):
        from f.gold.gold_price_provider import _fetch_usd_current_freegoldapi
        price = _fetch_usd_current_freegoldapi(os.environ.get("FREEGOLDAPI_KEY", ""))
        _assert_positive_price(price, "USD/g via FreeGoldAPI")

    def test_fetch_usd_current_fallback_chain(self):
        """End-to-end: no keys → falls through to yfinance."""
        from f.gold.gold_price_provider import fetch_usd_current
        price, source = fetch_usd_current("", "", "")
        _assert_positive_price(price, f"USD/g via {source}")
        assert source == "yfinance"


# ── AED current ───────────────────────────────────────────────────────────────

class TestLiveAEDCurrent:
    def test_igold_scrape(self):
        from f.gold.gold_price_provider import _fetch_aed_igold
        prices = _fetch_aed_igold()
        _assert_carat_dict(prices, "iGold AED prices")
        # AED 24K is typically 230–400/g
        assert 150 < prices["24K"] < 600, f"iGold 24K AED {prices['24K']} looks wrong"

    def test_igold_returns_all_carats(self):
        from f.gold.gold_price_provider import _fetch_aed_igold
        prices = _fetch_aed_igold()
        assert set(prices.keys()) >= {"24K", "22K", "21K", "18K"}

    def test_igold_carats_descend_with_purity(self):
        from f.gold.gold_price_provider import _fetch_aed_igold
        p = _fetch_aed_igold()
        assert p["24K"] > p["22K"] > p.get("21K", 0)

    def test_dcog_api(self):
        from f.gold.gold_price_provider import _fetch_aed_dcog
        prices = _fetch_aed_dcog()
        _assert_carat_dict(prices, "DCOG AED prices")
        assert 150 < prices["24K"] < 600, f"DCOG 24K AED {prices['24K']} looks wrong"

    def test_dcog_returns_all_carats(self):
        from f.gold.gold_price_provider import _fetch_aed_dcog
        prices = _fetch_aed_dcog()
        assert "24K" in prices and "22K" in prices

    def test_igold_and_dcog_prices_agree(self):
        """iGold and DCOG should be within 2% of each other."""
        from f.gold.gold_price_provider import _fetch_aed_igold, _fetch_aed_dcog
        ig = _fetch_aed_igold()["24K"]
        dcog = _fetch_aed_dcog()["24K"]
        diff_pct = abs(ig - dcog) / dcog * 100
        assert diff_pct < 2.0, f"iGold ({ig}) and DCOG ({dcog}) differ by {diff_pct:.1f}%"

    def test_fetch_aed_current_fallback_chain(self):
        from f.gold.gold_price_provider import fetch_usd_current, fetch_aed_current
        usd, _ = fetch_usd_current("", "", "")
        p24, supplied, source, price_type = fetch_aed_current(usd, "", "", "")
        _assert_positive_price(p24, f"AED/g via {source}")
        assert source in ("igold", "dcog", "usd_conversion")


# ── INR current ───────────────────────────────────────────────────────────────

class TestLiveINRCurrent:
    def test_khaleejtimes_inr(self):
        from f.gold.gold_price_provider import _fetch_inr_khaleejtimes
        price = _fetch_inr_khaleejtimes()
        _assert_positive_price(price, "INR/g via KhaleejTimes")
        # INR 24K is typically 5000–10000/g
        assert 4000 < price < 15000, f"KhaleejTimes INR {price} looks wrong"

    @pytest.mark.skip(reason="Metals.dev subscription not active")
    def test_metalsdev_inr(self):
        from f.gold.gold_price_provider import _fetch_inr_metalsdev
        price = _fetch_inr_metalsdev(os.environ.get("METALSDEV_KEY", ""))
        _assert_positive_price(price, "INR/g via Metals.dev")

    def test_fetch_inr_current_fallback_chain(self):
        from f.gold.gold_price_provider import fetch_usd_current, fetch_inr_current
        usd, _ = fetch_usd_current("", "", "")
        price, source, price_type = fetch_inr_current(usd, "")
        _assert_positive_price(price, f"INR/g via {source}")
        assert source in ("khaleejtimes", "usd_conversion")


# ── USD historical ────────────────────────────────────────────────────────────

class TestLiveUSDHistory:
    def test_yahoo_finance_history(self):
        from f.gold.gold_price_provider import _fetch_usd_history_yahoo
        target = _recent_weekday(3)
        results = _fetch_usd_history_yahoo({target})
        assert len(results) >= 1, f"Expected data for {target}"
        date_str, price, open_, high, low = results[0]
        assert date_str == target
        _assert_positive_price(price, "USD/g history via yfinance")
        assert 40 < price < 200

    def test_yahoo_ohlc_relationship(self):
        """high >= close >= low for any day that has full OHLC."""
        from f.gold.gold_price_provider import _fetch_usd_history_yahoo
        target = _recent_weekday(5)
        results = _fetch_usd_history_yahoo({target})
        for date_str, price, open_, high, low in results:
            if high is not None and low is not None:
                assert high >= price >= low, (
                    f"OHLC invariant violated on {date_str}: "
                    f"high={high} close={price} low={low}"
                )

    def test_yahoo_multiple_dates(self):
        from f.gold.gold_price_provider import _fetch_usd_history_yahoo
        dates = {_recent_weekday(i) for i in range(2, 6)}
        results = _fetch_usd_history_yahoo(dates)
        result_dates = {r[0] for r in results}
        # At least half the requested dates should come back
        assert len(result_dates) >= len(dates) // 2

    @pytest.mark.skip(reason="FreeGoldAPI subscription not active")
    def test_freegoldapi_history(self):
        import requests
        from f.gold.gold_price_provider import TROY_OZ_TO_GRAM
        key = os.environ.get("FREEGOLDAPI_KEY", "")
        target = _recent_weekday(3)
        r = requests.get(
            f"https://freegoldapi.com/api/XAU/USD/history?start_date={target}&end_date={target}",
            headers={"x-access-token": key}, timeout=15)
        r.raise_for_status()
        data = r.json()
        entries = data if isinstance(data, list) else data.get("data", [])
        assert entries, f"FreeGoldAPI returned no data for {target}"

    def test_fetch_usd_history_fallback_chain(self):
        from f.gold.gold_price_provider import fetch_usd_history
        target = _recent_weekday(3)
        results, source = fetch_usd_history({target}, "", "", "")
        assert results, f"No USD history returned for {target}"
        assert source == "yfinance"
        _, price, *_ = results[0]
        _assert_positive_price(price, f"USD/g history via {source}")


# ── AED historical (KhaleejTimes) ────────────────────────────────────────────

class TestLiveAEDHistory:
    def test_khaleejtimes_uae(self):
        from f.gold.gold_price_provider import fetch_khaleejtimes_history
        result = fetch_khaleejtimes_history("uae", 10)
        assert isinstance(result, dict) and result, "Expected non-empty dict"
        sample_date = next(iter(result))
        _assert_carat_dict(result[sample_date], f"KhaleejTimes AED on {sample_date}")

    def test_khaleejtimes_uae_aed_range(self):
        from f.gold.gold_price_provider import fetch_khaleejtimes_history
        result = fetch_khaleejtimes_history("uae", 7)
        for d, carats in result.items():
            if "24K" in carats:
                assert 150 < carats["24K"] < 600, (
                    f"KhaleejTimes AED 24K on {d}: {carats['24K']} looks wrong"
                )

    def test_khaleejtimes_uae_carats_descend(self):
        from f.gold.gold_price_provider import fetch_khaleejtimes_history
        result = fetch_khaleejtimes_history("uae", 7)
        for d, carats in result.items():
            if "24K" in carats and "22K" in carats:
                assert carats["24K"] > carats["22K"], (
                    f"24K should be > 22K on {d}: {carats}"
                )


# ── INR historical ────────────────────────────────────────────────────────────

class TestLiveINRHistory:
    def test_khaleejtimes_india(self):
        from f.gold.gold_price_provider import fetch_khaleejtimes_history
        result = fetch_khaleejtimes_history("india", 10)
        assert isinstance(result, dict) and result
        sample_date = next(iter(result))
        _assert_carat_dict(result[sample_date], f"KhaleejTimes INR on {sample_date}")

    def test_khaleejtimes_india_inr_range(self):
        from f.gold.gold_price_provider import fetch_khaleejtimes_history
        result = fetch_khaleejtimes_history("india", 7)
        for d, carats in result.items():
            if "24K" in carats:
                assert 4000 < carats["24K"] < 25000, (
                    f"KhaleejTimes INR 24K on {d}: {carats['24K']} looks wrong"
                )

    def test_nse_india(self):
        from f.gold.gold_price_provider import fetch_inr_history_nse
        to_date = _recent_weekday(1)
        from_date = _recent_weekday(5)
        result = fetch_inr_history_nse(from_date, to_date)
        assert isinstance(result, dict) and result, (
            f"NSE returned no data for {from_date}–{to_date}"
        )
        for d, price in result.items():
            _assert_positive_price(float(price), f"NSE INR on {d}")
            assert 4000 < price < 25000, f"NSE INR {price} on {d} looks wrong"

    def test_nse_dates_are_iso_format(self):
        from f.gold.gold_price_provider import fetch_inr_history_nse
        to_date = _recent_weekday(1)
        from_date = _recent_weekday(7)
        result = fetch_inr_history_nse(from_date, to_date)
        for d in result:
            date.fromisoformat(d)  # raises if not valid ISO format

    @pytest.mark.skip(reason="Metals.dev subscription not active")
    def test_metalsdev_inr_history(self):
        from f.gold.gold_price_provider import fetch_inr_history_metalsdev
        target = _recent_weekday(3)
        results = fetch_inr_history_metalsdev(os.environ.get("METALSDEV_KEY", ""), [target])
        assert results
        _, price, *_ = results[0]
        _assert_positive_price(float(price), "INR/g history via Metals.dev")

    def test_nse_and_khaleejtimes_broadly_agree(self):
        """NSE and KhaleejTimes INR 24K prices should be within 5% for overlapping dates."""
        from f.gold.gold_price_provider import fetch_inr_history_nse, fetch_khaleejtimes_history
        to_date = _recent_weekday(1)
        from_date = _recent_weekday(7)
        nse = fetch_inr_history_nse(from_date, to_date)
        kt = fetch_khaleejtimes_history("india", 10)
        common = set(nse) & set(kt)
        if not common:
            pytest.skip(f"No overlapping dates between NSE and KhaleejTimes ({from_date}–{to_date})")
        for d in common:
            nse_price = nse[d]
            kt_price = kt[d].get("24K")
            if kt_price is None:
                continue
            diff_pct = abs(nse_price - kt_price) / kt_price * 100
            assert diff_pct < 5.0, (
                f"NSE ({nse_price}) and KhaleejTimes ({kt_price}) on {d} differ by {diff_pct:.1f}%"
            )
