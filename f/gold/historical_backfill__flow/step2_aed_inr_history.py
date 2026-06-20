# requirements:
# sqlalchemy
# requests
# beautifulsoup4
# yfinance
# psycopg2-binary

from sqlalchemy import create_engine

from f.gold.gold_utils import get_fx_rate, build_rows, UPSERT_SQL
from f.gold.gold_price_provider import (
    fetch_khaleejtimes_history,
    fetch_inr_history_metalsdev,
    fetch_inr_history_nse,
)


def main(
    database_url: str,
    usd_history: list,
    days: int = 365,
    currencies: list = ["USD", "AED", "INR"],
    metalsdev_key: str = "",
) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    summary = {"currencies": {}, "errors": []}
    print("=== Step 2: AED and INR historical prices ===")

    usd_dates = {e["date"] for e in usd_history}

    if "AED" in currencies:
        try:
            rows_to_upsert = []
            aed_source = None

            try:
                kt_data = fetch_khaleejtimes_history("uae", days)
                for date, carats in kt_data.items():
                    if date not in usd_dates or "24K" not in carats:
                        continue
                    rows_to_upsert.extend(build_rows(
                        date, "AED", carats["24K"], None, None, None,
                        "khaleejtimes", "local", supplied_carats=carats))
                if rows_to_upsert:
                    aed_source = "khaleejtimes"
            except Exception as e:
                print(f"KhaleejTimes AED history failed: {e}")

            if not rows_to_upsert:
                fx = get_fx_rate("AED")
                for entry in usd_history:
                    rows_to_upsert.extend(build_rows(
                        entry["date"], "AED",
                        entry["price"] * fx,
                        entry["open"] * fx if entry["open"] else None,
                        entry["high"] * fx if entry["high"] else None,
                        entry["low"] * fx if entry["low"] else None,
                        "usd_conversion", "converted"))
                aed_source = "usd_conversion"

            with engine.begin() as conn:
                for row in rows_to_upsert:
                    conn.execute(UPSERT_SQL, row)
            summary["currencies"]["AED"] = {"source": aed_source, "rows": len(rows_to_upsert)}
            print(f"AED: upserted {len(rows_to_upsert)} rows via {aed_source}")
        except Exception as e:
            msg = f"AED failed: {e}"
            print(msg)
            summary["errors"].append(msg)

    if "INR" in currencies:
        try:
            rows_to_upsert = []
            inr_source = None

            try:
                from datetime import datetime, timedelta
                to_date = datetime.today().strftime("%Y-%m-%d")
                from_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
                nse_data = fetch_inr_history_nse(from_date, to_date)
                for date, price in nse_data.items():
                    # if date not in usd_dates:
                    #     continue
                    rows_to_upsert.extend(build_rows(date, "INR", price, None, None, None, "nse", "local"))
                if rows_to_upsert:
                    inr_source = "nse"
                    print(f"NSE INR history: {len(rows_to_upsert)} rows fetched")
            except Exception as e:
                print(f"NSE INR history failed: {e}")

            if not rows_to_upsert:
                try:
                    kt_data = fetch_khaleejtimes_history("india", days)
                    for date, carats in kt_data.items():
                        if date not in usd_dates or "24K" not in carats:
                            continue
                        rows_to_upsert.extend(build_rows(
                            date, "INR", carats["24K"], None, None, None,
                            "khaleejtimes", "local", supplied_carats=carats))
                    if rows_to_upsert:
                        inr_source = "khaleejtimes"
                except Exception as e:
                    print(f"KhaleejTimes INR history failed: {e}")

            if not rows_to_upsert and metalsdev_key:
                try:
                    inr_hist = fetch_inr_history_metalsdev(metalsdev_key, list(usd_dates))
                    for date, price, open_, high, low in inr_hist:
                        rows_to_upsert.extend(build_rows(date, "INR", price, open_, high, low, "metalsdev_inr", "local"))
                    if rows_to_upsert:
                        inr_source = "metalsdev_inr"
                except Exception as e:
                    print(f"Metals.dev INR history failed: {e}")

            if not rows_to_upsert:
                fx = get_fx_rate("INR")
                for entry in usd_history:
                    rows_to_upsert.extend(build_rows(
                        entry["date"], "INR",
                        entry["price"] * fx,
                        entry["open"] * fx if entry["open"] else None,
                        entry["high"] * fx if entry["high"] else None,
                        entry["low"] * fx if entry["low"] else None,
                        "usd_conversion", "converted"))
                inr_source = "usd_conversion"

            with engine.begin() as conn:
                for row in rows_to_upsert:
                    conn.execute(UPSERT_SQL, row)
            summary["currencies"]["INR"] = {"source": inr_source, "rows": len(rows_to_upsert)}
            print(f"INR: upserted {len(rows_to_upsert)} rows via {inr_source}")
        except Exception as e:
            msg = f"INR failed: {e}"
            print(msg)
            summary["errors"].append(msg)

    return summary
