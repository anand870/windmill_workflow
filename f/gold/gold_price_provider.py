# requirements:
# requests
# beautifulsoup4
# yfinance

import re
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

from f.gold.gold_utils import get_fx_rate

TROY_OZ_TO_GRAM = 31.1035


# ── USD current ───────────────────────────────────────────────────────────────

def _fetch_usd_current_freegoldapi(key: str) -> float:
    r = requests.get("https://freegoldapi.com/api/XAU/USD",
                     headers={"x-access-token": key}, timeout=10)
    r.raise_for_status()
    d = r.json()
    return float(d.get("price_gram_24k") or d.get("price_troy_oz", 0) / TROY_OZ_TO_GRAM)


def _fetch_usd_current_metalsdev(key: str) -> float:
    r = requests.get(f"https://api.metals.dev/v1/latest?api_key={key}&currency=USD&unit=g", timeout=10)
    r.raise_for_status()
    return float(r.json()["metals"]["gold"])


def _fetch_usd_current_goldapi(key: str) -> float:
    r = requests.get("https://www.goldapi.io/api/XAU/USD",
                     headers={"x-access-token": key}, timeout=10)
    r.raise_for_status()
    d = r.json()
    return float(d.get("price_gram_24k") or d.get("price", 0) / TROY_OZ_TO_GRAM)


def _fetch_usd_current_yahoo() -> float:
    ticker = yf.Ticker("GC=F")
    return ticker.fast_info["last_price"] / TROY_OZ_TO_GRAM


def fetch_usd_current(freegoldapi_key: str, metalsdev_key: str, goldapi_key: str) -> tuple:
    if goldapi_key:
        try:
            return _fetch_usd_current_goldapi(goldapi_key), "goldapi"
        except Exception as e:
            print(f"GoldAPI current failed: {e}")
    if metalsdev_key:
        try:
            return _fetch_usd_current_metalsdev(metalsdev_key), "metalsdev"
        except Exception as e:
            print(f"Metals.dev current failed: {e}")
    if freegoldapi_key:
        try:
            return _fetch_usd_current_freegoldapi(freegoldapi_key), "freegoldapi"
        except Exception as e:
            print(f"FreeGoldAPI current failed: {e}")
    try:
        return _fetch_usd_current_yahoo(), "yfinance"
    except Exception as e:
        raise RuntimeError(f"All USD current providers failed: {e}")


# ── AED current ───────────────────────────────────────────────────────────────

def _fetch_aed_igold() -> dict:
    r = requests.get(
        "https://igold.ae/gold-rate/",
        headers={"User-Agent": "Mozilla/5.0 (compatible; GoldAdvisor/2.0)"},
        timeout=15,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    table = next(
        (t for t in soup.find_all("table")
         if (thead := t.find("thead")) and "24K" in thead.get_text()),
        None,
    )
    if table is None:
        raise ValueError("iGold: could not find carat price table on page")
    header_cells = table.find("thead").find_all("td")
    carats = [c.get_text(strip=True) for c in header_cells]
    body_cells = table.find("tbody").find_all("td")
    prices_raw = [c.get_text(strip=True) for c in body_cells]
    if len(carats) != len(prices_raw):
        raise ValueError(f"iGold: header/body cell count mismatch ({len(carats)} vs {len(prices_raw)})")
    prices = {}
    for carat_label, price_str in zip(carats, prices_raw):
        numeric = re.sub(r"[^\d.]", "", price_str)
        if numeric:
            prices[carat_label] = float(numeric)
    if not prices.get("24K") or prices["24K"] <= 0:
        raise ValueError(f"iGold: missing or invalid 24K price: {prices}")
    return prices


def _fetch_aed_dcog() -> dict:
    r = requests.post(
        "https://dubaicityofgold.com/gold-rate-app/dcoggoldrate",
        data={"vendor_key": "DCOG_KEY_964592976"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if str(data.get("status")) != "1":
        raise ValueError(f"DCOG API error: {data.get('msg', 'unknown')}")
    prices = {}
    for carat, key in [("24K", "gold_rate_24k"), ("22K", "gold_rate_22k"),
                       ("21K", "gold_rate_21k"), ("18K", "gold_rate_18k")]:
        val = data.get(key)
        try:
            v = float(val) if val is not None else None
            if v and v > 0:
                prices[carat] = v
        except (ValueError, TypeError):
            pass
    if not prices.get("24K"):
        raise ValueError(f"DCOG: missing or invalid 24K price: {data}")
    return prices


def fetch_aed_current(usd_price: float, freegoldapi_key: str, metalsdev_key: str, goldapi_key: str) -> tuple:
    try:
        prices = _fetch_aed_igold()
        p24 = prices.get("24K", list(prices.values())[0])
        return p24, prices, "igold", "local"
    except Exception as e:
        print(f"iGold AED failed: {e}")
    try:
        prices = _fetch_aed_dcog()
        p24 = prices.get("24K", list(prices.values())[0])
        return p24, prices, "dcog", "local"
    except Exception as e:
        print(f"DCOG AED failed: {e}")
    fx = get_fx_rate("AED")
    return usd_price * fx, None, "usd_conversion", "converted"


# ── INR current ───────────────────────────────────────────────────────────────

def _fetch_inr_khaleejtimes() -> float:
    r = requests.get(
        "https://api.khaleejtimes.com/JoyalukkasGold_ajx/get_Gold_data_new_countries",
        params={"country": "india"},
        headers={"origin": "https://www.khaleejtimes.com"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    for row in data.get("rates", []):
        if (row.get("type") or "").strip() != "24K":
            continue
        for slot in ("evening", "afternoon", "morning"):
            numeric = re.sub(r"[^\d.]", "", row.get(slot) or "")
            if numeric:
                val = float(numeric)
                if val > 0:
                    return val
    raise ValueError("Khaleejtimes: no INR 24K price found")


def _fetch_inr_metalsdev(key: str) -> float:
    r = requests.get(f"https://api.metals.dev/v1/latest?api_key={key}&currency=INR&unit=g", timeout=10)
    r.raise_for_status()
    return float(r.json()["metals"]["gold"])


def fetch_inr_current(usd_price: float, metalsdev_key: str) -> tuple:
    try:
        price = _fetch_inr_khaleejtimes()
        return price, "khaleejtimes", "local"
    except Exception as e:
        print(f"Khaleejtimes INR failed: {e}")
    if metalsdev_key:
        try:
            price = _fetch_inr_metalsdev(metalsdev_key)
            return price, "metalsdev_inr", "local"
        except Exception as e:
            print(f"Metals.dev INR failed: {e}")
    fx = get_fx_rate("INR")
    return usd_price * fx, "usd_conversion", "converted"


# ── USD historical ────────────────────────────────────────────────────────────

def _fetch_usd_history_yahoo(missing_dates: set) -> list:
    start = min(missing_dates)
    end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    ticker = yf.Ticker("GC=F")
    hist = ticker.history(start=start, end=end)
    results = []
    for idx, row in hist.iterrows():
        date = idx.strftime("%Y-%m-%d")
        if date not in missing_dates:
            continue
        price = float(row["Close"]) / TROY_OZ_TO_GRAM
        open_ = float(row["Open"]) / TROY_OZ_TO_GRAM if row["Open"] else None
        high = float(row["High"]) / TROY_OZ_TO_GRAM if row["High"] else None
        low = float(row["Low"]) / TROY_OZ_TO_GRAM if row["Low"] else None
        results.append((date, price, open_, high, low))
    return results


def fetch_usd_history(missing_dates: set, freegoldapi_key: str, metalsdev_key: str, goldapi_key: str) -> tuple:
    try:
        data = _fetch_usd_history_yahoo(missing_dates)
        if data:
            return data, "yfinance"
    except Exception as e:
        print(f"Yahoo Finance history failed: {e}")

    if freegoldapi_key:
        try:
            start = min(missing_dates)
            end = max(missing_dates)
            r = requests.get(
                f"https://freegoldapi.com/api/XAU/USD/history?start_date={start}&end_date={end}",
                headers={"x-access-token": freegoldapi_key}, timeout=15)
            r.raise_for_status()
            data = r.json()
            results = []
            for entry in data if isinstance(data, list) else data.get("data", []):
                date = entry.get("date") or entry.get("timestamp", "")[:10]
                if date not in missing_dates:
                    continue
                raw = entry.get("price_gram_24k") or entry.get("price_troy_oz", 0) / TROY_OZ_TO_GRAM
                results.append((date, float(raw), None, None, None))
            if results:
                return results, "freegoldapi"
        except Exception as e:
            print(f"FreeGoldAPI history failed: {e}")

    raise RuntimeError("All USD historical providers failed")


# ── INR historical (NSE India) ────────────────────────────────────────────────

def fetch_inr_history_nse(from_date: str, to_date: str) -> dict:
    """
    Fetch INR gold spot prices from NSE India for a date range.
    from_date, to_date: YYYY-MM-DD strings (inclusive).
    Returns {date: price} where date is YYYY-MM-DD and price is INR/gram (24K GOLD1G).
    NSE data is published ~1 day late — only suitable for historical fills.
    """
    from_str = datetime.strptime(from_date, "%Y-%m-%d").strftime("%d-%m-%Y")
    to_str = datetime.strptime(to_date, "%Y-%m-%d").strftime("%d-%m-%Y")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "accept": "*/*",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "referer": "https://www.nseindia.com/historical-spot-price",
    })
    # Establish session cookies by loading the main page first
    session.get("https://www.nseindia.com/", timeout=15)

    r = session.get(
        "https://www.nseindia.com/api/historical-spot-price",
        params={"symbol": "GOLD1G", "fromDate": from_str, "toDate": to_str},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json().get("data", [])

    by_date: dict = {}
    for entry in data:
        # UpdatedDate: "19-JUN-2026" -> parse to YYYY-MM-DD
        raw_date = entry.get("UpdatedDate", "")
        try:
            iso_date = datetime.strptime(raw_date, "%d-%b-%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        price = None
        for key in ("SpotPrice2", "SpotPrice1"):
            try:
                v = float(entry[key])
                if v > 0:
                    price = v
                    break
            except (KeyError, ValueError, TypeError):
                continue
        if price and iso_date not in by_date:
            by_date[iso_date] = price

    return by_date


# ── INR historical (Metals.dev) ───────────────────────────────────────────────

def fetch_inr_history_metalsdev(key: str, dates: list) -> list:
    """Returns list of (date, price, None, None, None) for the given dates."""
    results = []
    for date in sorted(dates):
        r = requests.get(
            f"https://api.metals.dev/v1/latest?api_key={key}&currency=INR&unit=g&date={date}",
            timeout=10)
        r.raise_for_status()
        price = r.json()["metals"]["gold"]
        results.append((date, float(price), None, None, None))
    return results


# ── AED / INR historical (KhaleejTimes) ──────────────────────────────────────

def fetch_khaleejtimes_history(country: str, days: int) -> dict:
    """
    country: 'uae' for AED, 'india' for INR
    Returns {date: {"24K": float, "22K": float, "21K": float, "18K": float}}
    """
    r = requests.get(
        "https://api.khaleejtimes.com/JoyalukkasGold_ajx/gold_rates",
        params={"country": country, "range": days},
        headers={"origin": "https://www.khaleejtimes.com"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("status"):
        raise ValueError(f"KhaleejTimes history error ({country}): {data}")
    gold = data["data"]["gold"]
    by_date: dict = {}
    for key, label in [("24k", "24K"), ("22k", "22K"), ("21k", "21K"), ("18k", "18K")]:
        for entry in gold.get(key, []):
            price = float(entry["y"])
            if price > 0:
                by_date.setdefault(entry["x"], {})[label] = price
    if not by_date:
        raise ValueError(f"KhaleejTimes history: no data parsed for country={country}")
    return by_date


def main():
    pass
