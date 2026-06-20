# requirements:
# sqlalchemy
# requests
# beautifulsoup4
# yfinance
# psycopg2-binary

from datetime import datetime
from sqlalchemy import create_engine

from f.gold.gold_utils import build_rows, UPSERT_SQL
from f.gold.gold_price_provider import fetch_usd_current, fetch_aed_current, fetch_inr_current

TODAY = datetime.today().strftime("%Y-%m-%d")


def main(
    database_url: str,
    currencies: list = ["USD", "AED", "INR"],
    freegoldapi_key: str = "",
    metalsdev_key: str = "",
    goldapi_key: str = "",
) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    summary = {"currencies": {}, "errors": [], "usd_price": None}
    usd_price_today = None

    print(f"=== Step 1: Current prices for {TODAY} ===")

    if "USD" in currencies:
        try:
            usd_price, usd_source = fetch_usd_current(freegoldapi_key, metalsdev_key, goldapi_key)
            usd_price_today = usd_price
            rows = build_rows(TODAY, "USD", usd_price, None, None, None, usd_source, "local")
            with engine.begin() as conn:
                for row in rows:
                    conn.execute(UPSERT_SQL, row)
            summary["currencies"]["USD"] = {"source": usd_source, "price_24k": usd_price}
            summary["usd_price"] = usd_price
            print(f"USD current: {usd_price:.4f}/g via {usd_source}")
        except Exception as e:
            msg = f"USD current failed: {e}"
            print(msg)
            summary["errors"].append(msg)

    if "AED" in currencies:
        try:
            if usd_price_today is None:
                usd_price_today, _ = fetch_usd_current(freegoldapi_key, metalsdev_key, goldapi_key)
            p24, supplied, aed_source, price_type = fetch_aed_current(
                usd_price_today, freegoldapi_key, metalsdev_key, goldapi_key)
            rows = build_rows(TODAY, "AED", p24, None, None, None, aed_source, price_type,
                              supplied_carats=supplied)
            with engine.begin() as conn:
                for row in rows:
                    conn.execute(UPSERT_SQL, row)
            summary["currencies"]["AED"] = {"source": aed_source, "price_24k": p24}
            print(f"AED current: {p24:.4f}/g via {aed_source}")
        except Exception as e:
            msg = f"AED current failed: {e}"
            print(msg)
            summary["errors"].append(msg)

    if "INR" in currencies:
        try:
            if usd_price_today is None:
                usd_price_today, _ = fetch_usd_current(freegoldapi_key, metalsdev_key, goldapi_key)
            inr_price, inr_source, price_type = fetch_inr_current(usd_price_today, metalsdev_key)
            rows = build_rows(TODAY, "INR", inr_price, None, None, None, inr_source, price_type)
            with engine.begin() as conn:
                for row in rows:
                    conn.execute(UPSERT_SQL, row)
            summary["currencies"]["INR"] = {"source": inr_source, "price_24k": inr_price}
            print(f"INR current: {inr_price:.4f}/g via {inr_source}")
        except Exception as e:
            msg = f"INR current failed: {e}"
            print(msg)
            summary["errors"].append(msg)

    return summary
