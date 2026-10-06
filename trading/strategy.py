"""Trading rules. Each rule turns a price series into a position series.

A position of 1 means "hold the stock", 0 means "stay in cash", and 2 means
"hold twice your money's worth" (borrowing the rest). The position on day t is
decided using information available at the close of day t.
"""

import numpy as np
import pandas as pd


def sma(close, window):
    """Simple moving average of the closing price."""
    return close.rolling(window, min_periods=window).mean()


def above_sma(close, window=50):
    """Hold the stock only while it closes above its moving average.

    Days before there is enough history for the average count as "don't trade".
    """
    return (close > sma(close, window)).astype(int).rename("Position")


def sma_buffer(close, window=50, band=0.02):
    """Like above_sma, but with a no-trade zone around the average.

    Buy when the close rises more than `band` above the SMA; sell only when it
    falls more than `band` below. Inside the zone, keep doing what you were doing.
    This filters out small wiggles across the line.
    """
    avg = sma(close, window)
    buy = close > avg * (1 + band)
    sell = close < avg * (1 - band)
    return _hold_until(buy, sell)


def sma_confirm(close, window=50, days=3):
    """Like above_sma, but the price must stay on the new side for `days` closes in a row
    before the position flips."""
    above = close > sma(close, window)
    below = close < sma(close, window)
    buy = above.rolling(days).sum() == days
    sell = below.rolling(days).sum() == days
    return _hold_until(buy, sell)


def sma_rising(close, window=50, lookback=10):
    """Hold only when the price is above the SMA *and* the SMA itself is higher than
    it was `lookback` days ago (the trend is pointing up)."""
    avg = sma(close, window)
    return ((close > avg) & (avg > avg.shift(lookback))).astype(int).rename("Position")


def golden_cross(close, fast=50, slow=200):
    """Hold while the 50-day average is above the 200-day average."""
    return (sma(close, fast) > sma(close, slow)).astype(int).rename("Position")


def trend_regime(close, window=50, slow=200):
    """Stay invested unless the price is below its 50-day *and* the 50-day is below
    the 200-day. In a long-term uptrend, dips under the 50-day are ignored."""
    s50, s200 = sma(close, window), sma(close, slow)
    out = (close < s50) & (s50 < s200)
    return (~out & s200.notna()).astype(int).rename("Position")


def weekly_check(close, window=50):
    """Apply above_sma only at Friday's close (the last trading day of each week),
    then hold that decision all next week. Fewer checks, fewer whipsaws."""
    daily = above_sma(close, window).astype(float)
    week = close.index.to_period("W")
    last_day = pd.Series(week, index=close.index) != pd.Series(week, index=close.index).shift(-1)
    return daily.where(last_day).ffill().fillna(0).astype(int).rename("Position")


def leveraged(position, multiple=2):
    """Scale any rule's position, e.g. 2x exposure when the rule says hold."""
    return (position * multiple).rename("Position")


def _hold_until(buy, sell):
    """Turn buy/sell trigger days into a position: in from a buy trigger until a sell trigger."""
    state = pd.Series(np.nan, index=buy.index)
    state[buy] = 1
    state[sell & ~buy] = 0
    return state.ffill().fillna(0).astype(int).rename("Position")


RULES = {
    "Above 50d (baseline)": lambda c: above_sma(c, 50),
    "50d with 2% buffer": lambda c: sma_buffer(c, 50, 0.02),
    "50d with 3% buffer": lambda c: sma_buffer(c, 50, 0.03),
    "50d, 3-day confirm": lambda c: sma_confirm(c, 50, 3),
    "50d, checked weekly": lambda c: weekly_check(c, 50),
    "Above 50d & 50d rising": lambda c: sma_rising(c, 50, 10),
    "50d > 200d (golden cross)": lambda c: golden_cross(c, 50, 200),
    "Exit only if <50d & 50d<200d": lambda c: trend_regime(c, 50, 200),
    "2x when above 50d": lambda c: leveraged(above_sma(c, 50), 2),
    "2x when 50d > 200d": lambda c: leveraged(golden_cross(c, 50, 200), 2),
}
