"""The whole US stock market, screened point-in-time like a real daily scan.

Steps:
  1. `symbols()` lists every NASDAQ / NYSE / AMEX stock (from a public GitHub list,
     cached in data/universe/).
  2. `build()` downloads daily OHLCV + splits for all of them, in batches. Every
     stock's adjusted close is kept (to rank RS ratings against the whole market);
     full OHLCV is kept only for stocks that were ever liquid enough to matter.
  3. `load()` returns the panels, and `leader_screen()` applies the trader's scan
     on each past day using only data available that day.

Yahoo's "Close" and "Volume" are already split-adjusted, which would make old
prices look tiny (NVDA traded near $15 in 2010, not $0.40). We undo splits to
get the price and share volume a scanner would have shown at the time. Dollar
volume (price x shares) is the same either way.
"""

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from .data import CACHE_DIR

UNIVERSE_DIR = CACHE_DIR / "universe"
LIST_URL = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/{ex}/{ex}_full_tickers.json"
EXCHANGES = ("nasdaq", "nyse", "amex")
KEEP_IF_DOLLAR_VOLUME = 50e6  # keep full OHLCV for stocks whose 50-day dollar volume ever topped this


def symbols():
    """Every listed common stock / ADR symbol, with sector and industry."""
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for ex in EXCHANGES:
        path = UNIVERSE_DIR / f"{ex}.json"
        if not path.exists():
            urllib.request.urlretrieve(LIST_URL.format(ex=ex), path)
        for r in json.loads(path.read_text()):
            rows.append({"symbol": r["symbol"].strip(), "exchange": ex, "sector": r["sector"], "industry": r["industry"]})
    df = pd.DataFrame(rows).drop_duplicates("symbol")
    df = df[df["symbol"].str.fullmatch(r"[A-Z]{1,5}")]  # drop preferreds, warrants, units with odd symbols
    return df.set_index("symbol")


def split_factor(splits):
    """For each day, the product of all splits that happen *after* it.

    Multiply a split-adjusted price by this to get the price that day; divide
    split-adjusted volume by it to get the shares actually traded.
    """
    s = splits.replace(0, 1).fillna(1)
    return s[::-1].cumprod()[::-1].shift(-1).fillna(1)


def _process(df):
    df = df.dropna(subset=["Close"])
    if len(df) < 60:
        return None
    factor = split_factor(df["Stock Splits"])
    return pd.DataFrame({
        "adj": df["Adj Close"],
        "close": df["Close"] * factor,  # price as traded that day
        "high": df["High"],
        "low": df["Low"],
        "shares": df["Volume"] / factor,  # shares as traded that day
        "dollars": df["Close"] * df["Volume"],
    })


def build(start="2004-01-01", batch=150, pause=2.0):
    """Download the whole market. Safe to re-run: finished batches are skipped."""
    import yfinance as yf

    syms = symbols().index.tolist()
    parts = UNIVERSE_DIR / "parts"
    parts.mkdir(exist_ok=True)
    for b in range(0, len(syms), batch):
        out = parts / f"batch_{b // batch:03d}.pkl"
        if out.exists():
            continue
        chunk = syms[b:b + batch]
        raw = yf.download(chunk, start=start, auto_adjust=False, actions=True, group_by="ticker",
                          progress=False, threads=True)
        adj, ohlcv = {}, {}
        for t in chunk:
            if t not in raw.columns.get_level_values(0):
                continue
            p = _process(raw[t])
            if p is None:
                continue
            adj[t] = p["adj"]
            if p["dollars"].rolling(50).mean().max() >= KEEP_IF_DOLLAR_VOLUME:
                ohlcv[t] = p
        pd.to_pickle({"adj": adj, "ohlcv": ohlcv}, out)
        print(f"batch {b // batch + 1}/{-(-len(syms) // batch)}: {len(adj)} stocks, {len(ohlcv)} liquid", flush=True)
        time.sleep(pause)
    _combine(parts)


def _combine(parts):
    adj, fields = {}, {k: {} for k in ("close", "high", "low", "shares", "dollars", "adj")}
    for f in sorted(parts.glob("batch_*.pkl")):
        d = pd.read_pickle(f)
        adj.update(d["adj"])
        for t, p in d["ohlcv"].items():
            for k in fields:
                fields[k][t] = p[k]
    pd.DataFrame(adj).astype("float32").to_pickle(UNIVERSE_DIR / "all_adj.pkl")
    pd.to_pickle({k: pd.DataFrame(v).astype("float64") for k, v in fields.items()}, UNIVERSE_DIR / "liquid.pkl")


def load():
    """(adjusted closes for every stock, dict of OHLCV panels for liquid stocks)."""
    return pd.read_pickle(UNIVERSE_DIR / "all_adj.pkl"), pd.read_pickle(UNIVERSE_DIR / "liquid.pkl")


def adr_pct(high, low, days=20):
    """Average daily range in %: the 20-day average of (high / low - 1)."""
    return (high / low - 1).rolling(days).mean() * 100


def leader_screen(panels, min_price=10, min_shares=2e6, min_dollars=600e6, adr=(5, 8), avg_days=50):
    """True where a stock passed the leader scan at that day's close.

    Price >= $10, average shares traded >= 2M, average dollar volume >= $600M,
    and ADR between 5% and 8%. Volume averages are over `avg_days`. Market cap
    history isn't available, but $600M a day of trading only happens in
    companies far above $1B.
    """
    shares = panels["shares"].rolling(avg_days, min_periods=avg_days).mean()
    dollars = panels["dollars"].rolling(avg_days, min_periods=avg_days).mean()
    a = adr_pct(panels["high"], panels["low"])
    return (panels["close"] >= min_price) & (shares >= min_shares) & (dollars >= min_dollars) & (a >= adr[0]) & (a <= adr[1])


def rs_rating_market(all_adj, columns, min_price_adj=1.0):
    """RS rating (1-99) for `columns`, ranked against every stock in the market.

    Same IBD-style weighting as indicators.rs_rating, but the percentile is taken
    across all ~6,000 US stocks each day, which is how IBD does it.
    """
    q = 63
    p = all_adj.astype("float64")
    perf = (0.4 * (p / p.shift(q)) + 0.2 * (p.shift(q) / p.shift(2 * q))
            + 0.2 * (p.shift(2 * q) / p.shift(3 * q)) + 0.2 * (p.shift(3 * q) / p.shift(4 * q)))
    perf = perf.where(p >= min_price_adj).replace([np.inf, -np.inf], np.nan)
    rating = perf.rank(axis=1, pct=True) * 98 + 1
    return rating.reindex(columns=columns)


if __name__ == "__main__":
    build()
