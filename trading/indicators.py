"""Indicators used by swing-trading research: moving averages, RS rating, environment score.

All functions work on a Series (one ticker) or a DataFrame (one column per ticker)
and only use data up to each day, so they're safe to use in backtests.
"""

import pandas as pd

from .strategy import sma


def ema(close, span):
    """Exponential moving average (weights recent closes more than an SMA does)."""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def moving_averages(close):
    """The five averages a swing trader watches: 10 EMA, 20 EMA, 50/100/200 SMA."""
    return {
        "ema10": ema(close, 10),
        "ema20": ema(close, 20),
        "sma50": sma(close, 50),
        "sma100": sma(close, 100),
        "sma200": sma(close, 200),
    }


def ma_score(close):
    """How many of the five averages the close is above (0 to 5)."""
    return sum((close > ma).astype(int) for ma in moving_averages(close).values())


def stacked(close):
    """True when the averages are in bullish order: 10 EMA > 20 EMA > 50 > 100 > 200 SMA."""
    m = moving_averages(close)
    return (m["ema10"] > m["ema20"]) & (m["ema20"] > m["sma50"]) & (m["sma50"] > m["sma100"]) & (m["sma100"] > m["sma200"])


def rs_rating(prices):
    """IBD-style relative strength rating, 1 to 99, ranked within `prices` columns.

    Weighted 12-month performance: the latest quarter counts double
    (40%, then 20% for each of the three quarters before it). Every day, each
    stock's score is converted to a percentile against the other stocks.
    IBD ranks against ~6,000 stocks; here it's only the basket, so treat 70+
    as "top 30% of this basket".
    """
    q = 63
    perf = (
        0.4 * (prices / prices.shift(q))
        + 0.2 * (prices.shift(q) / prices.shift(2 * q))
        + 0.2 * (prices.shift(2 * q) / prices.shift(3 * q))
        + 0.2 * (prices.shift(3 * q) / prices.shift(4 * q))
    )
    return (perf.rank(axis=1, pct=True) * 98 + 1).where(perf.notna())


def breadth(prices, window=50):
    """Share of stocks closing above their `window`-day SMA (0 to 1)."""
    above = prices > sma(prices, window)
    return above.sum(axis=1) / prices.notna().sum(axis=1)


def streak(flags):
    """Days in a row `flags` has been True; resets to 0 on False. Works per column."""
    if isinstance(flags, pd.DataFrame):
        return flags.apply(streak)
    flags = flags.astype(int)
    return flags.groupby((flags == 0).cumsum()).cumsum()
