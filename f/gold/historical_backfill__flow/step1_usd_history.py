# requirements:
# requests
# yfinance
# sqlalchemy
# psycopg2-binary

import requests
import yfinance as yf
from datetime import datetime, timedelta
from sqlalchemy import create_engine

from f.gold.gold_utils import build_rows, UPSERT_SQL

TROY_OZ_TO_GRAM = 31.1035


def _fetch_usd_history_yahoo(days: int) -> list:
    ticker = yf.Ticker("GC=F")
    hist = ticker.history(period=f"{days}d")
    results = []
    for idx, row in hist.iterrows():
        date = idx.strftime("%Y-%m-%d")
        price = float(row["Close"]) / TROY_OZ_TO_GRAM
        open_ = float(row["Open"]) / TROY_OZ_TO_GRAM if row["Open"] else None
        high = float(row["High"]) / TROY_OZ_TO_GRAM if row["High"] else None
        low = float(row["Low"]) / TROY_OZ_TO_GRAM if row["Low"] else None
        results.append({"date": date, "price": price, "open": open_, "high": high, "low": low})
    return results


def _fetch_usd_history_freegoldapi(days: int, key: str) -> list:
    end = datetime.today()
    start = end - timedelta(days=days)
    url = (f"https://freegoldapi.com/api/XAU/USD/history"
           f"?start_date={start.strftime('%Y-%m-%d')}&end_date={end.strftime('%Y-%m-%d')}")
    r = requests.get(url, headers={"x-access-token": key}, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = []
    for entry in data if isinstance(data, list) else data.get("data", []):
        date = entry.get("date") or entry.get("timestamp", "")[:10]
        raw = entry.get("price_gram_24k") or entry.get("price_troy_oz", 0) / TROY_OZ_TO_GRAM
        results.append({"date": date, "price": float(raw), "open": None, "high": None, "low": None})
    return results


def _fetch_usd_history_metalsdev(days: int, key: str) -> list:
    results = []
    for i in range(days):
        date = (datetime.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            r = requests.get(
                f"https://api.metals.dev/v1/latest?api_key={key}&currency=USD&unit=g&date={date}",
                timeout=10)
            r.raise_for_status()
            price = r.json()["metals"]["gold"]
            results.append({"date": date, "price": float(price), "open": None, "high": None, "low": None})
        except Exception:
            continue
    return results


def _fetch_usd_history_goldapi(days: int, key: str) -> list:
    results = []
    for i in range(days):
        date = datetime.today() - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        date_fmt = date.strftime("%Y%m%d")
        try:
            r = requests.get(
                f"https://www.goldapi.io/api/XAU/USD/{date_fmt}",
                headers={"x-access-token": key}, timeout=10)
            r.raise_for_status()
            d = r.json()
            price = d.get("price_gram_24k") or d.get("price", 0) / TROY_OZ_TO_GRAM
            results.append({"date": date_str, "price": float(price), "open": None, "high": None, "low": None})
        except Exception:
            continue
    return results


def fetch_usd_history(days: int, freegoldapi_key: str, metalsdev_key: str, goldapi_key: str) -> tuple:
    try:
        data = _fetch_usd_history_yahoo(days)
        if data:
            return data, "yfinance"
    except Exception as e:
        print(f"Yahoo Finance history failed: {e}")
    if freegoldapi_key:
        try:
            data = _fetch_usd_history_freegoldapi(days, freegoldapi_key)
            if data:
                return data, "freegoldapi"
        except Exception as e:
            print(f"FreeGoldAPI history failed: {e}")
    if metalsdev_key:
        try:
            data = _fetch_usd_history_metalsdev(days, metalsdev_key)
            if data:
                return data, "metalsdev"
        except Exception as e:
            print(f"Metals.dev history failed: {e}")
    if goldapi_key:
        try:
            data = _fetch_usd_history_goldapi(days, goldapi_key)
            if data:
                return data, "goldapi"
        except Exception as e:
            print(f"GoldAPI history failed: {e}")
    raise RuntimeError("All USD historical providers failed")


def main(
    database_url: str,
    days: int = 365,
    freegoldapi_key: str = "",
    metalsdev_key: str = "",
    goldapi_key: str = "",
) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    print(f"=== Step 1: USD historical prices (last {days} days) ===")

    usd_history, source = fetch_usd_history(days, freegoldapi_key, metalsdev_key, goldapi_key)

    rows_to_upsert = []
    for entry in usd_history:
        rows_to_upsert.extend(build_rows(
            entry["date"], "USD", entry["price"],
            entry["open"], entry["high"], entry["low"],
            source, "local"))

    with engine.begin() as conn:
        for row in rows_to_upsert:
            conn.execute(UPSERT_SQL, row)

    print(f"USD: upserted {len(rows_to_upsert)} rows via {source}")
    return {"usd_history": usd_history, "source": source, "rows_upserted": len(rows_to_upsert)}
