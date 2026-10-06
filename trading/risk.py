"""Risk-on / risk-off gauge: many market-health signals combined into one 0-100 score.

Every component is computed at the daily close from data known that day, and
scores 1 (healthy), 0.5 (mixed) or 0 (unhealthy). The gauge is the average of the
components available on that day, times 100.

Components (see COMPONENTS for the exact rules):
  Leaders     leader index trend, leader breadth, breakout success rate
  Breadth     % of stocks above their 50 SMA, net new 52-week highs
  Index       weekly MACD on SPY and QQQ, distribution days on QQQ, SPY not overextended
  Fear        VIX below its 50-day average, VIX term structure (VIX < VIX3M)
  Appetite    junk bonds vs Treasuries (HYG/IEF), discretionary vs staples (XLY/XLP)
"""

import numpy as np
import pandas as pd

from . import data
from .indicators import ema
from .strategy import sma
from .universe import adr_pct, leader_environment

ZONES = {"Risk-On": 65, "Neutral": 40}  # >= 65 risk-on, 40-65 neutral, < 40 risk-off


def download_ohlcv(ticker, start="2004-01-01"):
    """Daily OHLCV for an ETF or index (cached in data/)."""
    path = data.CACHE_DIR / f"{ticker.replace('^', '_')}_ohlcv_{start}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    import yfinance as yf

    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    df.columns = df.columns.get_level_values(0)
    df.index.name = "Date"
    data.CACHE_DIR.mkdir(exist_ok=True)
    df.to_csv(path)
    return df


def weekly_macd_state(close, fast=12, slow=26, signal=9):
    """+1 when the weekly MACD line is above its signal line, -1 when below.

    Uses completed weeks only (Friday closes); each week's reading applies from
    that week's last trading day until the next week completes.
    """
    weekly = close.resample("W-FRI").last().dropna()
    line = ema(weekly, fast) - ema(weekly, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    state = np.sign(line - sig).where(sig.notna())
    return state.reindex(close.index.union(state.index)).ffill().reindex(close.index)


def distribution_days(ohlcv, window=25, min_drop=-0.002):
    """IBD-style distribution days: down 0.2%+ on higher volume than the day before."""
    c, v = ohlcv["Close"], ohlcv["Volume"]
    dd = (c.pct_change() <= min_drop) & (v > v.shift(1))
    return dd.rolling(window).sum()


def breakout_success(adj, group, lookback=20, hold=10, window=10):
    """Share of recent breakouts (new 20-day closing highs) still above the breakout
    price `hold` days later. Only breakouts that have had time to play out count."""
    event = (adj > adj.shift(1).rolling(lookback).max()) & group
    success = event & (adj.shift(-hold) > adj)
    wins = success.shift(hold).rolling(window).sum().sum(axis=1)
    tries = event.shift(hold).rolling(window).sum().sum(axis=1)
    return wins / tries.replace(0, np.nan)


def components(panels, index):
    """DataFrame of component scores (0 / 0.5 / 1) on `index` days."""
    adj, close = panels["adj"], panels["close"]
    dollars = panels["dollars"].rolling(50, min_periods=50).mean()
    liquid = ((dollars >= 20e6) & (close >= 5)).astype(bool)
    leaders = ((dollars >= 100e6) & (adr_pct(panels["high"], panels["low"]) >= 4) & (close >= 10)).astype(bool)

    li, lb = leader_environment(panels)
    above50 = ((adj > sma(adj, 50)) & liquid).sum(axis=1) / liquid.sum(axis=1).replace(0, np.nan)
    hi = (adj >= adj.rolling(252, min_periods=252).max()) & liquid
    lo = (adj <= adj.rolling(252, min_periods=252).min()) & liquid
    net_highs = ((hi.sum(axis=1) - lo.sum(axis=1)) / liquid.sum(axis=1).replace(0, np.nan)).rolling(10).mean()
    bo = breakout_success(adj, leaders)

    spy, qqq = download_ohlcv("SPY"), download_ohlcv("QQQ")
    macd = weekly_macd_state(spy["Close"]).reindex(index) + weekly_macd_state(qqq["Close"]).reindex(index)
    dist = distribution_days(qqq).reindex(index)
    spy_ext = (spy["Close"] / sma(spy["Close"], 50) - 1).reindex(index)

    def ratio_trend(a, b):
        r = download_ohlcv(a)["Close"] / download_ohlcv(b)["Close"]
        return (r > sma(r, 50)).where(sma(r, 50).notna())

    vix = download_ohlcv("^VIX")["Close"]
    vix3m = download_ohlcv("^VIX3M")["Close"].reindex(vix.index)

    def score(cond):
        return cond.astype(float).where(cond.notna()) if hasattr(cond, "notna") else cond

    comp = pd.DataFrame(index=index)
    comp["Leader index > 50 SMA"] = score((li > sma(li, 50)).where(sma(li, 50).notna()).reindex(index))
    comp["Leader index 10 EMA > 20 EMA"] = score((ema(li, 10) > ema(li, 20)).reindex(index))
    comp["Leader breadth > 50%"] = score((lb > 0.5).where(lb.notna()).reindex(index))
    comp["Breakout success > 50%"] = score((bo > 0.5).where(bo.notna()).reindex(index))
    comp["Stocks above 50 SMA > 50%"] = score((above50 > 0.5).where(above50.notna()).reindex(index))
    comp["Net new highs > 0"] = score((net_highs > 0).where(net_highs.notna()).reindex(index))
    comp["Weekly MACD SPY & QQQ bullish"] = (macd + 2) / 4  # both bull 1, mixed 0.5, both bear 0
    comp["QQQ distribution days <= 4"] = score((dist <= 4).where(dist.notna()))
    comp["SPY not > 8% above 50 SMA"] = score((spy_ext <= 0.08).where(spy_ext.notna()))
    comp["VIX below its 50-day avg"] = score((vix < sma(vix, 50)).where(sma(vix, 50).notna()).reindex(index))
    comp["VIX < VIX3M (calm term structure)"] = score((vix < vix3m).where(vix3m.notna()).reindex(index))
    comp["HYG/IEF above 50 SMA (credit)"] = score(ratio_trend("HYG", "IEF").reindex(index))
    comp["XLY/XLP above 50 SMA (appetite)"] = score(ratio_trend("XLY", "XLP").reindex(index))
    return comp


def gauge(comp, use=None):
    """0-100 score: the average of the chosen components available each day."""
    cols = list(use) if use is not None else list(comp.columns)
    return comp[cols].mean(axis=1, skipna=True) * 100


def smooth_zone(score, days=5, on=(65, 55), off=(35, 45)):
    """Zones with a 5-day average and buffers so the gauge doesn't flip on noise.

    Enter Risk-On at >= 65, stay until it drops below 55. Enter Risk-Off below 35,
    stay until it rises above 45. Otherwise Neutral.
    """
    avg = score.rolling(days, min_periods=1).mean()
    state, out = "Neutral", []
    for v in avg.to_numpy():
        if np.isnan(v):
            out.append(state)
            continue
        if state == "Risk-On":
            state = "Risk-On" if v >= on[1] else ("Risk-Off" if v < off[0] else "Neutral")
        elif state == "Risk-Off":
            state = "Risk-Off" if v <= off[1] else ("Risk-On" if v >= on[0] else "Neutral")
        else:
            state = "Risk-On" if v >= on[0] else ("Risk-Off" if v < off[0] else "Neutral")
        out.append(state)
    return pd.Series(out, index=score.index)


def zone_exposure(zones):
    return zones.map({"Risk-On": 1.0, "Neutral": 0.5, "Risk-Off": 0.0})


def zone(score):
    return pd.Series(np.select([score >= ZONES["Risk-On"], score >= ZONES["Neutral"]], ["Risk-On", "Neutral"], "Risk-Off"),
                     index=score.index)


def exposure(score):
    """Suggested exposure: 100% risk-on, 50% neutral, 0% risk-off."""
    return pd.Series(np.select([score >= ZONES["Risk-On"], score >= ZONES["Neutral"]], [1.0, 0.5], 0.0), index=score.index)


LEADER_SIGNALS = ["Leader index > 50 SMA", "Leader index 10 EMA > 20 EMA", "Leader breadth > 50%"]


def leader_gauge(comp):
    """The gauge that held up in both test periods: three leader-group signals.

    3 of 3 on = Risk-On (100%), 1-2 on = Neutral (50%), 0 on = Risk-Off (cash).
    """
    n = comp[LEADER_SIGNALS].sum(axis=1, min_count=1)
    return pd.Series(np.select([n >= 3, n >= 1], ["Risk-On", "Neutral"], "Risk-Off"), index=comp.index).where(n.notna())
