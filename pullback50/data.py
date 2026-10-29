"""Universe (S&P 500 + Nasdaq-100) and daily OHLCV downloads, cached under pullback50/cache/."""

import io
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).resolve().parent / "cache"
PRICES = CACHE / "prices"
SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
NDX_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
START = "2015-01-01"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research script)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def yahoo_symbol(sym):
    """BRK.B -> BRK-B (Yahoo's spelling)."""
    return sym.strip().upper().replace(".", "-")


def universe(refresh=False):
    """Today's S&P 500 and Nasdaq-100 members, deduplicated. Cached as JSON."""
    path = CACHE / "universe.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    sp = pd.read_csv(io.StringIO(_get(SP500_URL)))["Symbol"].map(yahoo_symbol).tolist()
    tables = pd.read_html(io.StringIO(_get(NDX_URL)))
    ndx_table = next(t for t in tables if ("Ticker" in t.columns or "Symbol" in t.columns) and len(t) > 80)
    col = "Ticker" if "Ticker" in ndx_table.columns else "Symbol"
    ndx = ndx_table[col].astype(str).map(yahoo_symbol).tolist()
    out = {"sp500": sorted(set(sp)), "ndx100": sorted(set(ndx)), "all": sorted(set(sp) | set(ndx))}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out


def download(tickers, start=START, refresh=False, batch=80):
    """Daily split/dividend-adjusted OHLCV per ticker, one CSV each in cache/prices/."""
    import yfinance as yf

    PRICES.mkdir(parents=True, exist_ok=True)
    todo = [t for t in tickers if refresh or not (PRICES / f"{t}.csv").exists()]
    for k in range(0, len(todo), batch):
        chunk = todo[k:k + batch]
        raw = yf.download(chunk, start=start, auto_adjust=True, group_by="ticker", progress=False, threads=True)
        for t in chunk:
            if t not in raw.columns.get_level_values(0):
                continue
            df = raw[t][["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "High", "Low", "Close"])
            if len(df) > 60:
                df.index.name = "Date"
                df.to_csv(PRICES / f"{t}.csv")
        print(f"  downloaded {min(k + batch, len(todo))}/{len(todo)}", flush=True)
        time.sleep(1.0)


def load(ticker):
    path = PRICES / f"{ticker}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
