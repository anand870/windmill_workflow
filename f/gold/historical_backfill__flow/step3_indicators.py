# requirements:
# sqlalchemy
# psycopg2-binary

from sqlalchemy import create_engine, text

from f.gold.gold_utils import compute_indicators, UPSERT_INDICATOR_SQL


def main(database_url: str) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    print("=== Step 3: Indicators (last 200 days of USD 24K) ===")

    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT date, price FROM gold_prices
            WHERE currency='USD' AND carat='24K'
            ORDER BY date DESC LIMIT 200
        """))
        rows = list(result)

    rows_asc = sorted(rows, key=lambda r: r[0])
    price_rows = [(r[0], r[1]) for r in rows_asc]
    indicators = compute_indicators(price_rows)

    with engine.begin() as conn:
        for ind in indicators:
            conn.execute(UPSERT_INDICATOR_SQL, ind)

    print(f"Indicators: upserted {len(indicators)} rows")
    return {"indicators_upserted": len(indicators)}
