# requirements:
# sqlalchemy
# requests
# beautifulsoup4
# yfinance
# psycopg2-binary

from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

from f.gold.gold_utils import get_fx_rate, build_rows, UPSERT_SQL
from f.gold.gold_price_provider import (
    fetch_usd_history,
    fetch_khaleejtimes_history,
    fetch_inr_history_metalsdev,
)


def _weekday_dates_in_window(history_days: int) -> set[str]:
    today = datetime.today().date()
    return {
        (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(1, history_days + 1)
        if (today - timedelta(days=i)).weekday() < 5
    }


def _existing_dates(engine, currency: str, history_days: int) -> set[str]:
    cutoff = (datetime.today() - timedelta(days=history_days)).strftime("%Y-%m-%d")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT date FROM gold_prices WHERE currency=:c AND carat='24K' AND date >= :d"),
            {"c": currency, "d": cutoff},
        ).fetchall()
    return {r[0] for r in rows}


def _kt_range_days(missing_dates: set) -> int:
    min_date = datetime.strptime(min(missing_dates), "%Y-%m-%d").date()
    return (datetime.today().date() - min_date).days + 2


def main(
    database_url: str,
    history_days: int = 5,
    currencies: list = ["USD", "AED", "INR"],
    freegoldapi_key: str = "",
    metalsdev_key: str = "",
    goldapi_key: str = "",
) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    summary = {"currencies": {}, "errors": []}
    usd_history = []

    print(f"=== Step 2: History gap fill (last {history_days} days) ===")

    expected = _weekday_dates_in_window(history_days)

    missing_usd = expected - _existing_dates(engine, "USD", history_days) if "USD" in currencies else set()
    missing_aed = expected - _existing_dates(engine, "AED", history_days) if "AED" in currencies else set()
    missing_inr = expected - _existing_dates(engine, "INR", history_days) if "INR" in currencies else set()

    print(f"Missing dates — USD: {len(missing_usd)}, AED: {len(missing_aed)}, INR: {len(missing_inr)}")

    if "USD" in currencies:
        if not missing_usd:
            print("USD history: up to date, skipping")
            summary["currencies"]["USD"] = {"source": "cached", "rows": 0}
        else:
            try:
                usd_history, hist_source = fetch_usd_history(missing_usd, freegoldapi_key, metalsdev_key, goldapi_key)
                rows_to_upsert = []
                for date, price, open_, high, low in usd_history:
                    rows_to_upsert.extend(build_rows(date, "USD", price, open_, high, low, hist_source, "local"))
                with engine.begin() as conn:
                    for row in rows_to_upsert:
                        conn.execute(UPSERT_SQL, row)
                summary["currencies"]["USD"] = {"source": hist_source, "rows": len(rows_to_upsert)}
                print(f"USD history: upserted {len(rows_to_upsert)} rows via {hist_source}")
            except Exception as e:
                msg = f"USD history gap fill failed: {e}"
                print(msg)
                summary["errors"].append(msg)

    if "AED" in currencies:
        if not missing_aed:
            print("AED history: up to date, skipping")
            summary["currencies"]["AED"] = {"source": "cached", "rows": 0}
        else:
            try:
                rows_to_upsert = []
                aed_source = None

                try:
                    kt_data = fetch_khaleejtimes_history("uae", _kt_range_days(missing_aed))
                    for date in missing_aed:
                        carats = kt_data.get(date)
                        if not carats or "24K" not in carats:
                            continue
                        rows_to_upsert.extend(build_rows(
                            date, "AED", carats["24K"], None, None, None,
                            "khaleejtimes", "local", supplied_carats=carats))
                    if rows_to_upsert:
                        aed_source = "khaleejtimes"
                except Exception as e:
                    print(f"KhaleejTimes AED history failed: {e}")

                if not rows_to_upsert:
                    if not usd_history:
                        usd_history, _ = fetch_usd_history(missing_aed, freegoldapi_key, metalsdev_key, goldapi_key)
                    fx = get_fx_rate("AED")
                    for date, price, open_, high, low in usd_history:
                        if date not in missing_aed:
                            continue
                        rows_to_upsert.extend(build_rows(
                            date, "AED", price * fx,
                            open_ * fx if open_ else None,
                            high * fx if high else None,
                            low * fx if low else None,
                            "usd_conversion", "converted"))
                    aed_source = "usd_conversion"

                with engine.begin() as conn:
                    for row in rows_to_upsert:
                        conn.execute(UPSERT_SQL, row)
                summary["currencies"]["AED"] = {"source": aed_source, "rows": len(rows_to_upsert)}
                print(f"AED history: upserted {len(rows_to_upsert)} rows via {aed_source}")
            except Exception as e:
                msg = f"AED history gap fill failed: {e}"
                print(msg)
                summary["errors"].append(msg)

    if "INR" in currencies:
        if not missing_inr:
            print("INR history: up to date, skipping")
            summary["currencies"]["INR"] = {"source": "cached", "rows": 0}
        else:
            try:
                rows_to_upsert = []
                inr_source = None

                try:
                    kt_data = fetch_khaleejtimes_history("india", _kt_range_days(missing_inr))
                    for date in missing_inr:
                        carats = kt_data.get(date)
                        if not carats or "24K" not in carats:
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
                        inr_hist = fetch_inr_history_metalsdev(metalsdev_key, list(missing_inr))
                        for date, price, open_, high, low in inr_hist:
                            rows_to_upsert.extend(build_rows(date, "INR", price, open_, high, low, "metalsdev_inr", "local"))
                        if rows_to_upsert:
                            inr_source = "metalsdev_inr"
                    except Exception as e:
                        print(f"Metals.dev INR history failed: {e}")

                if not rows_to_upsert:
                    if not usd_history:
                        usd_history, _ = fetch_usd_history(missing_inr, freegoldapi_key, metalsdev_key, goldapi_key)
                    fx = get_fx_rate("INR")
                    for date, price, open_, high, low in usd_history:
                        if date not in missing_inr:
                            continue
                        rows_to_upsert.extend(build_rows(
                            date, "INR", price * fx,
                            open_ * fx if open_ else None,
                            high * fx if high else None,
                            low * fx if low else None,
                            "usd_conversion", "converted"))
                    inr_source = "usd_conversion"

                with engine.begin() as conn:
                    for row in rows_to_upsert:
                        conn.execute(UPSERT_SQL, row)
                summary["currencies"]["INR"] = {"source": inr_source, "rows": len(rows_to_upsert)}
                print(f"INR history: upserted {len(rows_to_upsert)} rows via {inr_source}")
            except Exception as e:
                msg = f"INR history gap fill failed: {e}"
                print(msg)
                summary["errors"].append(msg)

    return summary
