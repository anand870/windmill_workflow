# Gold Workflow Context

This file is the entry point for any agent or developer working in this folder.
Read it before touching any script or flow — it avoids re-deriving the full picture from code.

## Purpose

Track gold spot prices in USD, AED, and INR, store them per-gram across four carats, and compute
technical indicators. Two flows cover the two main use cases: daily refresh and historical backfill.

---

## Database Schema

### `gold_prices`
Primary key: `(date, currency, carat)`

| Column | Type | Notes |
|---|---|---|
| date | DATE | Trading date |
| currency | VARCHAR | `USD`, `AED`, `INR` |
| carat | VARCHAR | `24K`, `22K`, `21K`, `18K` |
| price | FLOAT | Per gram in target currency |
| open / high / low | FLOAT | OHLC — nullable |
| source | VARCHAR | Provider name (e.g. `goldapi`, `khaleejtimes`, `nse`, `usd_conversion`) |
| price_type | VARCHAR | `local` = native-currency source; `converted` = derived via USD×FX |
| calculated | BOOLEAN | `False` if supplier gave this carat directly; `True` if computed from 24K×purity |
| updated_at | TIMESTAMP | |

### `gold_indicators`
Primary key: `date`. USD 24K prices only.

| Column | Type |
|---|---|
| date | DATE |
| ma7, ma30, ma90 | FLOAT |
| rsi14 | FLOAT |
| updated_at | TIMESTAMP |

---

## Shared Modules

### `gold_utils.py`
- `PURITY` — `{"24K": 1.0, "22K": 0.917, "21K": 0.875, "18K": 0.75}`
- `TROY_OZ_TO_GRAM = 31.1035` — used when providers return troy-oz prices
- `build_rows(date, currency, price_24k, open, high, low, source, price_type, supplied_carats=None) -> list[dict]`
  Generates 4 dicts (one per carat). Uses `supplied_carats` dict when available (sets `calculated=False`);
  otherwise computes lower carats from 24K × purity (`calculated=True`).
- `get_fx_rate(target: str) -> float` — open.er-api.com first, yfinance `USD{target}=X` fallback; cached per session
- `compute_indicators(rows: list[(date, price)]) -> list[dict]` — input must be sorted ascending; returns MA7/30/90 and RSI14
- `UPSERT_SQL` — ON CONFLICT (date, currency, carat) DO UPDATE
- `UPSERT_INDICATOR_SQL` — ON CONFLICT (date) DO UPDATE

### `gold_price_provider.py`
All price fetching lives here, grouped into current and historical functions per currency.
Add new providers here; call them from flow steps.

---

## Provider Fallback Chains

All functions stop at the first successful provider. On failure they print and try the next.

### Current prices (today only)

| Currency | Function | Priority |
|---|---|---|
| USD | `fetch_usd_current(freegoldapi_key, metalsdev_key, goldapi_key)` | GoldAPI → Metals.dev → FreeGoldAPI → YFinance (`GC=F`) |
| AED | `fetch_aed_current(usd_price, ...)` | iGold scrape → DCOG API → USD×FX |
| INR | `fetch_inr_current(usd_price, metalsdev_key)` | KhaleejTimes → Metals.dev → USD×FX |

### Historical prices

| Currency | Function | Priority |
|---|---|---|
| USD | `fetch_usd_history(missing_dates, ...)` | YFinance → FreeGoldAPI → (raises) |
| AED | `fetch_khaleejtimes_history("uae", days)` | KhaleejTimes → USD×FX (fallback in caller) |
| INR | `fetch_inr_history_nse(from_date, to_date)` | NSE India (GOLD1G) → KhaleejTimes → Metals.dev → USD×FX |
| INR (Metals.dev) | `fetch_inr_history_metalsdev(key, dates)` | Per-date API loop |
| AED+INR | `fetch_khaleejtimes_history(country, days)` | `country="uae"` or `"india"` |

**NSE India note:** `fetch_inr_history_nse` returns `{date: price}` (SpotPrice2 preferred, SpotPrice1 fallback).
Data is published ~1 day late — never use for current prices. Date format in response: `DD-MON-YYYY`.

---

## Flows

### `daily_refresh__flow`

**Purpose:** Runs daily. Keeps the database current and fills small weekday gaps.

**Input schema:**
- `database_url` (required)
- `currencies` — default `["USD", "AED", "INR"]`
- `history_days` — default `5` (weekdays to gap-fill)
- `freegoldapi_key`, `metalsdev_key`, `goldapi_key` — optional

**Steps:**

| Step | File | What it does |
|---|---|---|
| `step1_current_prices` | `step1_current_prices.py` | Fetches today's price for each currency; upserts 4 carat rows per currency |
| `step2_history_gap_fill` | `step2_history_gap_fill.py` | Finds weekday dates in last `history_days` missing from DB; fetches and upserts them |
| `step3_indicators` | `step3_indicators.py` | Queries last 200 USD 24K rows; upserts **today's** indicator only |

Step outputs are independent — no result is wired between steps.

---

### `historical_backfill__flow`

**Purpose:** One-off or periodic bulk backfill. Re-runnable (all upserts).

**Input schema:**
- `database_url` (required)
- `days` — default `365`
- `currencies` — default `["USD", "AED", "INR"]`
- `freegoldapi_key`, `metalsdev_key`, `goldapi_key` — optional

**Steps:**

| Step | File | What it does |
|---|---|---|
| `step1_usd_history` | `step1_usd_history.py` | Fetches `days` of USD history; upserts; **returns `usd_history` list for step 2** |
| `step2_aed_inr_history` | `step2_aed_inr_history.py` | Receives `usd_history` via `results.step1_usd_history.usd_history`; fetches AED/INR for those dates; upserts |
| `step3_indicators` | `step3_indicators.py` | Queries last 200 USD 24K rows; upserts **all** computed indicators (unlike daily flow) |

**Key wiring:** step2 uses `usd_dates` as the master date set — only upserts INR/AED rows where a USD price exists.

---

## Key Invariants

- All prices stored **per gram**. Providers returning troy-oz prices must divide by `TROY_OZ_TO_GRAM`.
- Every price produces **4 rows** (24K, 22K, 21K, 18K) via `build_rows()`.
- `calculated=True` for lower carats unless the source explicitly supplied them.
- Gap-fill targets **weekdays only** — weekends are never expected in the DB.
- Indicators use **USD 24K only**; computed over a 200-row window.
- Daily flow writes today's indicator; backfill writes the full window.

---

## Tests

Located at `f/gold/tests/`. Run from the workspace root:

```
python -m pytest f/gold/tests/ -v
```

| File | What it covers |
|---|---|
| `test_gold_utils.py` | `build_rows` (purity math, supplied carats, OHLC, `calculated` flag), `_compute_ma` (boundary/sliding window), `_compute_rsi14` (RSI bounds, all-gain/all-loss, Wilder smoothing), `compute_indicators` (end-to-end, MA/RSI availability thresholds) |
| `test_gold_provider.py` | Provider-level parsing (`_fetch_usd_current_goldapi`, `_fetch_usd_current_metalsdev`), full fallback chains for `fetch_usd_current`, `fetch_aed_current`, `fetch_inr_current`; `fetch_khaleejtimes_history` parsing/error paths; `fetch_inr_history_nse` date parsing, SpotPrice2 preference, duplicate-date dedup |
| `test_step_logic.py` | `_weekday_dates_in_window` (no weekends, excludes today, zero-day edge case), `_kt_range_days` (buffer, recency), `get_fx_rate` (caching, yfinance fallback, error), `build_rows` integration (AED/INR conversion scaling) |
| `test_live_apis.py` | Live end-to-end tests hitting real external URLs — see table below |

### Live tests (`test_live_apis.py`)

All tests are marked `@pytest.mark.live` and run automatically alongside unit tests.
Disabled APIs are `@pytest.mark.skip`; key-gated tests use `@pytest.mark.skipif`.

| Provider | Status | Skip condition |
|---|---|---|
| open.er-api.com FX | **enabled** | — |
| YFinance (USD current + history) | **enabled** | — |
| iGold scrape (AED current) | **enabled** | — |
| DCOG API (AED current) | **enabled** | — |
| KhaleejTimes (AED + INR history, INR current) | **enabled** | — |
| NSE India (INR history) | **enabled** | — |
| GoldAPI (USD current) | key-gated | skipped unless `GOLDAPI_KEY` env var set |
| Metals.dev (USD/INR current + INR history) | **disabled** | `@pytest.mark.skip` — subscription not active |
| FreeGoldAPI (USD current + history) | **disabled** | `@pytest.mark.skip` — subscription not active |

To re-enable Metals.dev or FreeGoldAPI: remove the `@pytest.mark.skip` decorator and set the relevant env var (`METALSDEV_KEY` / `FREEGOLDAPI_KEY`).

**Mocking notes (unit tests):**
- `requests` and `yfinance` are lazy-imported inside `get_fx_rate` — patch `requests.get` / `yfinance.Ticker` directly (not `f.gold.gold_utils.requests`).
- `get_fx_rate` is imported into `gold_price_provider` at module load — patch `f.gold.gold_price_provider.get_fx_rate` (not `f.gold.gold_utils.get_fx_rate`) when testing provider fallbacks.

---

## Extension Points

**New currency:**
1. Add `fetch_<currency>_current()` and `fetch_<currency>_history_*()` to `gold_price_provider.py`
2. Add a currency block in `step1_current_prices.py` (daily flow) and `step2_aed_inr_history.py` (backfill)
3. Document the fallback chain in the table above

**New provider for existing currency:**
1. Add `_fetch_<currency>_<provider>()` in `gold_price_provider.py`
2. Insert it at the desired priority in the relevant `fetch_<currency>_current/history()` function
3. Update the fallback chain table above

**New flow:**
1. Create the flow under `f/gold/<name>__flow/`
2. Add a section to this file following the same format as the two flows above
