"""Portfolio rotation backtest: hold the strongest stocks in a basket, rotate out of weakness.

Every trading day, at the close:
  1. Exit any holding that has closed below its 50-day SMA `exit_days` days in a row.
  2. On the weekly check (last trading day of the week), also exit holdings whose
     relative strength has dropped out of the top `2 * slots` of the basket.
  3. Fill any empty slots with the highest-RS names that qualify:
     above their 50-day SMA and beating the benchmark (RS > 0).

Optional market filter: the market is "on" while every index in `market`
(SPY and QQQ) has fewer than `market_days` closes in a row below its 50-day SMA.
When the market is "off", no new positions are opened and losing positions
(below their entry price) are sold. Winners are kept, still subject to step 1.

Each slot gets 1/slots of the portfolio. Empty slots sit in cash and earn
interest. Like the single-stock backtest, decisions made at today's close earn
tomorrow's returns, and every buy and sell pays `cost_bps`.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .backtest import TRADING_DAYS, _stats
from .indicators import ema, rs_rating, stacked
from .strategy import sma


@dataclass
class Settings:
    slots: int = 10  # how many names to hold at once
    window: int = 50  # moving average length
    exit_days: int = 3  # closes in a row below the SMA before selling
    rs_lookback: int = 63  # relative strength period in trading days (~3 months)
    require_rs: bool = True  # only buy names beating the benchmark
    market_filter: bool = False  # SPY/QQQ 50-day gate, see module docstring
    market_sell: str = "losers"  # when the market is off, sell: "losers", "all" or "none"
    market_days: int = 3  # closes in a row below the 50-day that turn the market off
    rank_by: str = "rs_vs_bench"  # "rs_vs_bench" (3-month return minus benchmark) or "rs_rating" (1-99)
    min_rs_rating: float = 0  # with rank_by="rs_rating": only buy names rated at least this
    entry: str = "above_ma"  # "above_ma", "stacked" (10e>20e>50>100>200) or "pullback" (stacked, within 3% of 20 EMA)
    exit_ma: str = "sma"  # average for the N-closes-below exit: "sma" (uses window), "ema20" or "ema10"
    cost_bps: float = 5.0


def _streak(flags):
    """Count how many days in a row `flags` has been True (resets to 0 on False)."""
    flags = flags.astype(int)
    return flags.groupby((flags == 0).cumsum()).cumsum()


def relative_strength(prices, benchmark, lookback=63):
    """Each stock's return over `lookback` days minus the benchmark's return."""
    stock_ret = prices / prices.shift(lookback) - 1
    bench_ret = benchmark / benchmark.shift(lookback) - 1
    return stock_ret.sub(bench_ret, axis=0)


def market_on(market, window=50, days=3):
    """True on days when every index has fewer than `days` closes in a row below its SMA."""
    streak = (market < sma(market, window)).apply(_streak)
    return (streak < days).all(axis=1)


def run_rotation(prices, benchmark, settings=Settings(), cash_rate=None, start=None, market=None, exposure=None):
    """Backtest the rotation strategy from `start`. `prices` has one column per ticker.

    Pass full price history: indicators are computed on all of it, so they're
    ready on day one instead of needing a warm-up period. `market` is a DataFrame
    of index closes (e.g. SPY and QQQ) used when `settings.market_filter` is on.
    `exposure` is an optional daily series from 0 to 1: the share of slots that may
    be filled. When it drops, the weakest holdings are sold to fit.
    """
    s = settings
    prices = prices.reindex(benchmark.index)

    avg = sma(prices, s.window)
    exit_line = {"sma": avg, "ema20": ema(prices, 20), "ema10": ema(prices, 10)}[s.exit_ma]
    below_streak = (prices < exit_line).apply(_streak)  # closes in a row below the exit average
    if s.rank_by == "rs_rating":
        rs = rs_rating(prices)
        eligible = (prices > avg) & (rs >= max(s.min_rs_rating, 1))
    else:
        rs = relative_strength(prices, benchmark, s.rs_lookback)
        eligible = (prices > avg) & rs.notna()
        if s.require_rs:
            eligible &= rs > 0
    if s.entry in ("stacked", "pullback"):
        eligible &= stacked(prices)
    if s.entry == "pullback":
        eligible &= (prices / ema(prices, 20) - 1).abs() <= 0.03
    rs_rank = rs.rank(axis=1, ascending=False)
    allowed = np.full(len(benchmark), s.slots) if exposure is None else \
        np.round(exposure.reindex(benchmark.index).ffill().fillna(1.0).to_numpy() * s.slots).astype(int)

    if s.market_filter:
        market_ok = market_on(market.reindex(benchmark.index).ffill(), s.window, s.market_days).to_numpy()
    else:
        market_ok = np.ones(len(benchmark), dtype=bool)

    keep = benchmark.index >= pd.Timestamp(start or benchmark.index[0])
    benchmark, prices = benchmark[keep], prices[keep]
    eligible, below_streak, rs, rs_rank = (x[keep] for x in (eligible, below_streak, rs, rs_rank))
    market_ok, allowed = market_ok[keep], allowed[keep]
    n_days, n_names = prices.shape

    week = benchmark.index.to_period("W")
    weekly = np.append(week[1:] != week[:-1], True)

    px = prices.to_numpy()
    rets = prices.pct_change().fillna(0.0).to_numpy()
    rate = np.zeros(n_days) if cash_rate is None else cash_rate.reindex(benchmark.index).ffill().fillna(0).to_numpy()
    elig, streak, score, rank = (x.to_numpy() for x in (eligible, below_streak, rs.fillna(-np.inf), rs_rank))

    w = np.zeros(n_names)  # fraction of the portfolio in each stock
    entry_px = np.full(n_names, np.nan)  # price each holding was bought at
    cash = 1.0
    daily_ret = np.zeros(n_days)
    names_held = np.zeros(n_days)
    weights = np.zeros((n_days, n_names))
    traded = 0.0
    cost = s.cost_bps / 10_000

    for t in range(n_days):
        # Overnight: holdings move with their prices, cash earns interest.
        if t > 0:
            w = w * (1 + rets[t])
            cash = cash * (1 + rate[t])
            total = w.sum() + cash
            daily_ret[t] = total - 1
            w, cash = w / total, cash / total

        # At the close: decide what to sell.
        held = w > 0
        sell = held & (streak[t] >= s.exit_days)
        if weekly[t]:
            sell |= held & (rank[t] > 2 * s.slots)
        if not market_ok[t]:
            if s.market_sell == "all":
                sell |= held
            elif s.market_sell == "losers":
                sell |= held & (px[t] < entry_px)
        extra = int((held & ~sell).sum()) - allowed[t]
        if extra > 0:  # exposure dropped: sell the weakest remaining holdings
            keepers = np.where(held & ~sell)[0]
            sell[keepers[np.argsort(score[t][keepers])][:extra]] = True
        if sell.any():
            cash += w[sell].sum() * (1 - cost)
            traded += w[sell].sum()
            w[sell] = 0.0

        # Then fill empty slots with the strongest qualifying names.
        open_slots = allowed[t] - int((w > 0).sum())
        if open_slots > 0 and market_ok[t]:
            candidates = np.where(elig[t] & (w == 0))[0]
            for i in candidates[np.argsort(-score[t][candidates])][:open_slots]:
                amount = min(1.0 / s.slots, cash)
                if amount < 0.25 / s.slots:
                    break
                w[i] = amount * (1 - cost)
                entry_px[i] = px[t, i]
                cash -= amount
                traded += amount

        names_held[t] = (w > 0).sum()
        weights[t] = w

    returns = pd.Series(daily_ret, index=benchmark.index)
    years = n_days / TRADING_DAYS
    metrics = _stats(returns) | {
        "avg_names": names_held.mean(),
        "invested": weights.sum(axis=1).mean(),
        "turnover": traded / years,  # portfolio traded per year (1.0 = 100%)
    }
    holdings = pd.DataFrame(weights, index=benchmark.index, columns=prices.columns)
    return returns, metrics, holdings


def equal_weight(prices, start_index, cost_bps=5.0):
    """Benchmark: hold every name in the basket in equal amounts, rebalanced monthly."""
    prices = prices.reindex(start_index)
    rets = prices.pct_change()
    month = start_index.to_period("M")
    rebalance = np.append(True, month[1:] != month[:-1])
    w = None
    out = np.zeros(len(start_index))
    r = rets.fillna(0).to_numpy()
    listed = prices.notna().to_numpy()
    for t in range(len(start_index)):
        if t > 0 and w is not None:
            w = w * (1 + r[t])
            out[t] = w.sum() - 1
            w = w / w.sum()
        if rebalance[t] and listed[t].any():
            target = listed[t] / listed[t].sum()
            if w is not None:
                out[t] -= np.abs(target - w).sum() * cost_bps / 10_000
            w = target.astype(float)
    return pd.Series(out, index=start_index)
