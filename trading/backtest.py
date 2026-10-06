"""Backtest engine: apply a position series to prices and measure the results."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class Result:
    daily: pd.DataFrame  # Close, Position, returns and equity curves
    trades: pd.DataFrame  # one row per round trip
    metrics: dict  # strategy stats
    benchmark: dict  # buy-and-hold stats over the same period


def run(close, position, cost_bps=5.0, cash_rate=None, borrow_spread=0.01):
    """Simulate trading `close` with `position` (1 = hold, 0 = cash, 2 = 2x leverage).

    Signals are computed at the close and filled at that same close, so the
    position decided on day t earns the return from day t to day t+1.
    `cost_bps` is charged on every buy and every sell (5 bps = 0.05%).
    `cash_rate` is an optional series of daily interest rates: uninvested money
    earns it, and borrowed money (position above 1) pays it plus `borrow_spread`
    per year.
    """
    df = pd.DataFrame({"Close": close, "Position": position}).dropna()
    df["Return"] = df["Close"].pct_change().fillna(0.0)
    held = df["Position"].shift(1).fillna(0)
    turnover = df["Position"].diff().abs().fillna(df["Position"].iloc[0])
    rate = 0.0 if cash_rate is None else cash_rate.reindex(df.index).ffill().fillna(0.0)
    cash = 1 - held  # negative when borrowing
    financing = np.where(cash >= 0, cash * rate, cash * (rate + borrow_spread / TRADING_DAYS))
    financing[0] = 0.0  # no time has passed on the first day
    df["StrategyReturn"] = held * df["Return"] + financing - turnover * cost_bps / 10_000
    df["Equity"] = (1 + df["StrategyReturn"]).cumprod()
    df["BuyHold"] = (1 + df["Return"]).cumprod()

    trades = _trades(df)
    metrics = _stats(df["StrategyReturn"])
    metrics.update(
        time_in_market=(held > 0).mean(),
        trades=len(trades),
        win_rate=(trades["Return"] > 0).mean() if len(trades) else np.nan,
        avg_trade=trades["Return"].mean() if len(trades) else np.nan,
    )
    return Result(df, trades, metrics, _stats(df["Return"]))


def _trades(df):
    """List each entry/exit pair with its return after costs."""
    pos = df["Position"].to_numpy()
    rows, entry = [], None
    for i in range(len(df)):
        if pos[i] > 0 and entry is None:
            entry = i
        elif pos[i] == 0 and entry is not None:
            rows.append(_trade_row(df, entry, i, closed=True))
            entry = None
    if entry is not None:
        rows.append(_trade_row(df, entry, len(df) - 1, closed=False))
    return pd.DataFrame(rows, columns=["Entry", "Exit", "EntryPrice", "ExitPrice", "Days", "Return", "Open"])


def _trade_row(df, i, j, closed):
    ret = (1 + df["StrategyReturn"].iloc[i : j + 1]).prod() - 1
    return [df.index[i].date(), df.index[j].date(), df["Close"].iloc[i], df["Close"].iloc[j], j - i, ret, not closed]


def _stats(returns):
    equity = (1 + returns).cumprod()
    years = len(returns) / TRADING_DAYS
    vol = returns.std() * np.sqrt(TRADING_DAYS)
    return {
        "total_return": equity.iloc[-1] - 1,
        "cagr": equity.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan,
        "volatility": vol,
        "sharpe": returns.mean() * TRADING_DAYS / vol if vol > 0 else np.nan,
        "max_drawdown": (equity / equity.cummax() - 1).min(),
    }
