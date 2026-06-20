You are implementing two self-contained Windmill pipeline scripts that collect gold price data from external sources and persist it into a shared PostgreSQL database. These scripts must be fully self-contained — no imports from any external project directory.

## Context

- Windmill runs in Docker at `/Users/rohitanand/workspace/personal/workflow/`
- The PostgreSQL database runs on the HOST machine at localhost:5432
- From inside Windmill Docker containers, the host is reachable at `host.docker.internal:5432`
- Database: `gold_db`, Writer role: `gold_writer` (INSERT/UPDATE/SELECT, no DDL)
- The schema (tables) is created and owned by a separate gold-mcp-v2 project — these scripts only write data, never create tables
- All scripts go under `/Users/rohitanand/workspace/personal/workflow/f/gold/`

## Existing Windmill Setup

docker-compose.yml at `/Users/rohitanand/workspace/personal/workflow/docker-compose.yml` defines:
- windmill_db (postgres:16-alpine) — Windmill's own DB, NOT the gold database
- windmill_redis, windmill_server, windmill_worker — all on bridge network `windmill`
- POSTGRES_PORT=5432 (windmill's postgres, ignore for gold — gold DB is on host)

wmill.yaml: workspace `rohit`, baseUrl http://localhost:8000/

## Database Schema (defined externally, do not CREATE — only INSERT/UPDATE/SELECT)

```sql
-- gold_prices
CREATE TABLE gold_prices (
  id         SERIAL PRIMARY KEY,
  date       VARCHAR(10) NOT NULL,        -- YYYY-MM-DD
  currency   VARCHAR(10) NOT NULL,        -- USD, AED, INR
  carat      VARCHAR(5)  NOT NULL,        -- 24K, 22K, 21K, 18K
  price      FLOAT       NOT NULL,        -- per gram
  open       FLOAT,
  high       FLOAT,
  low        FLOAT,
  source     VARCHAR(50) NOT NULL,        -- provider name
  price_type VARCHAR(20) NOT NULL,        -- 'local' or 'converted'
  calculated BOOLEAN     NOT NULL DEFAULT FALSE,  -- TRUE if derived from 24K purity ratio
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT uq_gold_prices_date_currency_carat UNIQUE (date, currency, carat)
);

-- gold_indicators (USD 24K only)
CREATE TABLE gold_indicators (
  id         SERIAL PRIMARY KEY,
  date       VARCHAR(10) NOT NULL,
  ma7        FLOAT,
  ma30       FLOAT,
  ma90       FLOAT,
  rsi14      FLOAT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT uq_gold_indicators_date UNIQUE (date)
);
```

## What to Build

### File 1: `/Users/rohitanand/workspace/personal/workflow/f/gold/historical_backfill.py`

Windmill one-time / manually-triggered script to populate historical gold prices.

```python
# requirements:
# sqlalchemy
# psycopg2-binary
# requests
# beautifulsoup4
# yfinance

def main(
    database_url: str,           # Windmill Variable: postgresql://gold_writer:...@host.docker.internal:5432/gold_db
    days: int = 365,
    currencies: list = ["USD", "AED", "INR"],
    freegoldapi_key: str = "",
    metalsdev_key: str = "",
    goldapi_key: str = "",
) -> dict:
```

Logic:
1. Connect to PostgreSQL using SQLAlchemy (psycopg2 driver), pool_pre_ping=True
2. For each currency in currencies:
   a. Fetch historical prices using the provider fallback chain (see below)
   b. For each date+price entry: upsert all 4 carats using ON CONFLICT DO UPDATE
   c. Log counts (inserted vs updated)
3. After all currencies: load last 200 days of USD 24K from DB → compute indicators → upsert into gold_indicators
4. Return summary dict

Upsert pattern (raw SQL or SQLAlchemy Core — no ORM needed):
```sql
INSERT INTO gold_prices (date, currency, carat, price, open, high, low, source, price_type, calculated, updated_at)
VALUES (:date, :currency, :carat, :price, :open, :high, :low, :source, :price_type, :calculated, NOW())
ON CONFLICT (date, currency, carat) DO UPDATE SET
  price=EXCLUDED.price, source=EXCLUDED.source, price_type=EXCLUDED.price_type,
  calculated=EXCLUDED.calculated, open=EXCLUDED.open, high=EXCLUDED.high,
  low=EXCLUDED.low, updated_at=NOW()
```

### File 2: `/Users/rohitanand/workspace/personal/workflow/f/gold/daily_refresh.py`

Windmill cron script — recommended schedule: `0 6 * * *` (6 AM daily).

```python
# requirements:
# sqlalchemy
# psycopg2-binary
# requests
# beautifulsoup4
# yfinance

def main(
    database_url: str,           # Windmill Variable
    history_days: int = 90,
    currencies: list = ["USD", "AED", "INR"],
    freegoldapi_key: str = "",
    metalsdev_key: str = "",
    goldapi_key: str = "",
) -> dict:
```

Three sequential steps:
1. **Current prices**: For each currency, fetch today's price from provider chain → upsert all 4 carats for today
2. **History gap fill**: For each currency, fetch last `history_days` days → upsert (fills weekends/gaps)
3. **Indicators**: Load last 200 days USD 24K from DB → compute MA7/MA30/MA90/RSI14 → upsert today's row

## Provider Logic (self-contained — implement directly in scripts, no external imports)

### Carat Purity Derivation
Purity ratios: 24K=1.0, 22K=0.917, 21K=0.875, 18K=0.75
If provider returns only 24K price, derive others: `price_Xk = price_24k * purity_ratio`
Mark derived carats as `calculated=True`, provider-supplied as `calculated=False`

### FX Rate Helper
Used when converting USD to AED or INR:
- Primary: GET `https://open.er-api.com/v6/latest/USD` → parse `rates.AED` or `rates.INR`
- Fallback: yfinance ticker `USDAED=X` or `USDINR=X`
- Cache in-memory for duration of the script run

### USD Providers (try in order, skip on exception)

1. **FreeGoldAPI** (requires freegoldapi_key):
   - GET `https://freegoldapi.com/api/XAU/USD` with header `x-access-token: {key}`
   - Use `price_gram_24k` field if present, else `price_troy_oz / 31.1035`

2. **Metals.dev** (requires metalsdev_key):
   - GET `https://api.metals.dev/v1/latest?api_key={key}&currency=USD&unit=g`
   - Parse `metals.gold` → already per-gram 24K

3. **GoldAPI** (requires goldapi_key):
   - GET `https://www.goldapi.io/api/XAU/USD` with header `x-access-token: {key}`
   - Use `price_gram_24k` or `price / 31.1035`

4. **Yahoo Finance** (no key — always available, use as final fallback):
   - `yfinance.Ticker("GC=F").fast_info["last_price"]` → divide by 31.1035

### AED Providers (current price only — try in order)

1. **iGold scraper** (no key):
   - GET `https://igold.ae/gold-rate/`
   - Parse HTML table with BeautifulSoup: find table rows, extract 24K/22K/21K/18K AED prices per gram
   - These are native prices (`price_type="local"`, `calculated=False`)

2. **Dubai City of Gold** (no key):
   - POST `https://dubaicityofgold.com/gold-rate-app/dcoggoldrate`
   - Body: `{"vendor_key": "DCOG_KEY_964592976"}`
   - Returns 24K/22K/21K/18K AED prices

3. **USD conversion** (fallback):
   - Fetch USD 24K price → multiply by FX rate (USD→AED)
   - `price_type="converted"`, `calculated=True` for non-24K carats

### INR Providers (current price only — try in order)

1. **Khaleejtimes** (no key):
   - GET `https://api.khaleejtimes.com/JoyalukkasGold_ajx/get_Gold_data_new_countries?country=india`
   - Returns morning/afternoon/evening prices for 24K/22K/21K/18K
   - Use latest non-zero update: evening > afternoon > morning

2. **Metals.dev INR** (requires metalsdev_key):
   - Same endpoint as USD variant: `?api_key={key}&currency=INR&unit=g`

3. **USD conversion** (fallback)

### Historical Fallback Order

- **USD**: yahoofinance → freegoldapi → metalsdev → goldapi
  - yahoofinance: `yfinance.Ticker("GC=F").history(period=f"{days}d")` → Open/High/Low/Close columns → divide by 31.1035
  - freegoldapi: GET `/XAU/USD/history?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
  - metalsdev: per-date call `?date=YYYY-MM-DD`
  - goldapi: per-date call `/XAU/USD/{YYYYMMDD}`

- **AED historical**: USD conversion only (iGold and DCOG have no history endpoint)
  - Fetch full USD history → multiply each date's price by current AED/USD FX rate

- **INR historical**: metalsdev_inr → USD conversion

### Indicator Computation (implement inline — no external library)

Input: list of (date, price) tuples for USD 24K, sorted ascending.

- **MA7/MA30/MA90**: Simple rolling mean. For date at index i, average the preceding N prices (inclusive). If fewer than N points available, skip (None).
- **RSI14**: 14-period RSI using Wilder's smoothing:
  1. Compute daily changes: `delta = price[i] - price[i-1]`
  2. Separate gains (delta > 0) and losses (delta < 0, use abs)
  3. Initial avg_gain and avg_loss = simple mean of first 14 changes
  4. For subsequent periods: `avg_gain = (prev_avg_gain * 13 + gain) / 14`
  5. `RSI = 100 - (100 / (1 + avg_gain / avg_loss))`; handle avg_loss == 0 → RSI = 100

## Windmill Variable Names (document in a comment at top of each script)

```python
# Windmill Variables to configure:
# u/rohit/gold_db_writer_url  →  postgresql://gold_writer:<pw>@host.docker.internal:5432/gold_db
# u/rohit/freegoldapi_key     →  <key>
# u/rohit/metalsdev_key       →  <key>
# u/rohit/goldapi_key         →  <key>
```

## What NOT to include

- No MCP tool definitions or MCP library imports
- No FastAPI / HTTP server code
- No buy-opportunity scoring or recommendation logic
- No SQLite engine, no `check_same_thread`
- No imports from gold-mcp source directory
- No `Base.metadata.create_all()` — schema is owned by gold-mcp-v2

## Error handling

- Wrap each currency's fetch in try/except — log the error, continue to next currency
- A failed currency should not abort the whole pipeline
- Return partial results with an `errors` key listing what failed