# requirements:
# sqlalchemy

from sqlalchemy import text

PURITY = {"24K": 1.0, "22K": 0.917, "21K": 0.875, "18K": 0.75}
TROY_OZ_TO_GRAM = 31.1035

_fx_cache: dict = {}

UPSERT_SQL = text("""
INSERT INTO gold_prices (date, currency, carat, price, open, high, low, source, price_type, calculated, updated_at)
VALUES (:date, :currency, :carat, :price, :open, :high, :low, :source, :price_type, :calculated, NOW())
ON CONFLICT (date, currency, carat) DO UPDATE SET
  price=EXCLUDED.price, source=EXCLUDED.source, price_type=EXCLUDED.price_type,
  calculated=EXCLUDED.calculated, open=EXCLUDED.open, high=EXCLUDED.high,
  low=EXCLUDED.low, updated_at=NOW()
""")

UPSERT_INDICATOR_SQL = text("""
INSERT INTO gold_indicators (date, ma7, ma30, ma90, rsi14, updated_at)
VALUES (:date, :ma7, :ma30, :ma90, :rsi14, NOW())
ON CONFLICT (date) DO UPDATE SET
  ma7=EXCLUDED.ma7, ma30=EXCLUDED.ma30, ma90=EXCLUDED.ma90,
  rsi14=EXCLUDED.rsi14, updated_at=NOW()
""")


def get_fx_rate(target: str) -> float:
    import requests
    import yfinance as yf
    if target in _fx_cache:
        return _fx_cache[target]
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        r.raise_for_status()
        rate = r.json()["rates"][target]
        _fx_cache[target] = rate
        return rate
    except Exception:
        pass
    try:
        ticker = yf.Ticker(f"USD{target}=X")
        rate = ticker.fast_info["last_price"]
        _fx_cache[target] = rate
        return rate
    except Exception:
        raise RuntimeError(f"Could not fetch FX rate for USD/{target}")


def build_rows(date: str, currency: str, price_24k: float, open_24k, high_24k, low_24k,
               source: str, price_type: str, supplied_carats: dict = None) -> list:
    rows = []
    for carat, purity in PURITY.items():
        if supplied_carats and carat in supplied_carats:
            p = supplied_carats[carat]
            calculated = False
        else:
            p = price_24k * purity
            calculated = carat != "24K"
        o = open_24k * purity if open_24k else None
        h = high_24k * purity if high_24k else None
        l = low_24k * purity if low_24k else None
        rows.append({
            "date": date, "currency": currency, "carat": carat,
            "price": p, "open": o, "high": h, "low": l,
            "source": source, "price_type": price_type, "calculated": calculated,
        })
    return rows


def _compute_ma(prices: list, n: int, idx: int):
    if idx < n - 1:
        return None
    return sum(prices[idx - n + 1: idx + 1]) / n


def _compute_rsi14(prices: list) -> list:
    rsi_values = [None] * len(prices)
    if len(prices) < 15:
        return rsi_values
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:14]) / 14
    avg_loss = sum(losses[:14]) / 14
    if avg_loss == 0:
        rsi_values[14] = 100.0
    else:
        rsi_values[14] = 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(15, len(prices)):
        avg_gain = (avg_gain * 13 + gains[i - 1]) / 14
        avg_loss = (avg_loss * 13 + losses[i - 1]) / 14
        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rsi_values[i] = 100 - (100 / (1 + avg_gain / avg_loss))
    return rsi_values


def compute_indicators(rows: list) -> list:
    """rows: list of (date, price) sorted ascending. Returns list of indicator dicts."""
    prices = [r[1] for r in rows]
    rsi_vals = _compute_rsi14(prices)
    result = []
    for i, (date, price) in enumerate(rows):
        ma7 = _compute_ma(prices, 7, i)
        ma30 = _compute_ma(prices, 30, i)
        ma90 = _compute_ma(prices, 90, i)
        rsi14 = rsi_vals[i]
        if any(v is not None for v in [ma7, ma30, ma90, rsi14]):
            result.append({"date": date, "ma7": ma7, "ma30": ma30, "ma90": ma90, "rsi14": rsi14})
    return result


def main():
    pass
