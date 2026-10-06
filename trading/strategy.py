"""Trading rules. Each rule turns a price series into a position series.

A position of 1 means "hold the stock", 0 means "stay in cash". The position
on day t is decided using information available at the close of day t.
"""

import pandas as pd


def sma(close, window):
    """Simple moving average of the closing price."""
    return close.rolling(window, min_periods=window).mean()


def above_sma(close, window=50):
    """Hold the stock only while it closes above its moving average.

    Days before there is enough history for the average count as "don't trade".
    """
    return (close > sma(close, window)).astype(int).rename("Position")
