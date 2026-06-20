# requirements:
# sqlalchemy
# psycopg2-binary

from datetime import datetime
from sqlalchemy import create_engine, text

from f.gold.gold_utils import compute_indicators, UPSERT_INDICATOR_SQL

TODAY = datetime.today().strftime("%Y-%m-%d")


def main(database_url: str) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    print("=== Step 3: Indicators ===")

    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT date, price FROM gold_prices
            WHERE currency='USD' AND carat='24K'
            ORDER BY date DESC LIMIT 200
        """))
        rows = list(result)

    rows_asc = sorted(rows, key=lambda r: r[0])
    price_rows = [(r[0], r[1]) for r in rows_asc]
    all_indicators = compute_indicators(price_rows)

    today_ind = [ind for ind in all_indicators if ind["date"] == TODAY]
    if not today_ind and all_indicators:
        today_ind = [all_indicators[-1]]

    with engine.begin() as conn:
        for ind in today_ind:
            conn.execute(UPSERT_INDICATOR_SQL, ind)

    result_ind = today_ind[0] if today_ind else None
    print(f"Indicators for {TODAY}: {result_ind}")
    return {"indicator": result_ind, "total_computed": len(all_indicators)}
