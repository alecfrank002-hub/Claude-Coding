"""Loading daily price data.

Prices come from Yahoo Finance (via yfinance) and are cached as CSV files in
data/ so repeat runs don't re-download. You can also load your own CSV, or
generate synthetic prices for testing without internet access.
"""

from pathlib import Path

import numpy as np
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"


def load_csv(path):
    """Load a CSV with a Date column and a Close (or Adj Close) column."""
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    col = "Adj Close" if "Adj Close" in df.columns else "Close"
    if col not in df.columns:
        raise ValueError(f"{path} needs a 'Close' or 'Adj Close' column")
    return df[col].astype(float).dropna().sort_index().rename("Close")


def download(ticker, start, end=None, use_cache=True):
    """Return split- and dividend-adjusted daily closes for one ticker."""
    cache_file = CACHE_DIR / f"{ticker.upper()}_{start}_{end or 'latest'}.csv"
    if use_cache and cache_file.exists():
        return load_csv(cache_file)

    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise RuntimeError(
            f"No data for {ticker}. Check the ticker symbol and that your "
            "network allows query1.finance.yahoo.com and fc.yahoo.com."
        )
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):  # newer yfinance returns one column per ticker
        close = close.iloc[:, 0]
    close = close.dropna().rename("Close")
    close.index.name = "Date"

    CACHE_DIR.mkdir(exist_ok=True)
    close.to_frame().to_csv(cache_file)
    return close


def synthetic(days=2520, seed=0, start="2015-01-02"):
    """Random-walk prices with alternating bull and bear regimes, for demos and tests."""
    rng = np.random.default_rng(seed)
    regime_drift = np.repeat(rng.choice([0.0009, -0.0006], size=days // 120 + 1), 120)[:days]
    returns = regime_drift + rng.normal(0, 0.012, days)
    index = pd.bdate_range(start, periods=days, name="Date")
    return pd.Series(100 * np.cumprod(1 + returns), index=index, name="Close")
