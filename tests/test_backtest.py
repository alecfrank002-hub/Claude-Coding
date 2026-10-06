import pandas as pd
import pytest

from trading import data, strategy
from trading.backtest import run


def prices(values):
    return pd.Series(values, index=pd.bdate_range("2020-01-01", periods=len(values)), dtype=float)


def test_no_position_until_sma_exists():
    close = prices(range(1, 61))
    pos = strategy.above_sma(close, 50)
    assert pos.iloc[:49].sum() == 0
    assert pos.iloc[49:].eq(1).all()  # rising prices sit above their average


def test_below_sma_means_no_trade():
    close = prices([10, 10, 10, 5, 5])
    assert strategy.above_sma(close, 3).tolist() == [0, 0, 0, 0, 0]


def test_return_earned_on_day_after_signal():
    # Signal turns on at day 2's close, so only the day 2 -> day 3 move counts.
    close = prices([100, 100, 110, 121])
    pos = pd.Series([0, 0, 1, 1], index=close.index)
    r = run(close, pos, cost_bps=0)
    assert r.daily["StrategyReturn"].tolist() == pytest.approx([0, 0, 0, 0.10])
    assert r.metrics["total_return"] == pytest.approx(0.10)


def test_costs_charged_on_entry_and_exit():
    close = prices([100] * 5)
    pos = pd.Series([0, 1, 1, 0, 0], index=close.index)
    r = run(close, pos, cost_bps=10)
    assert r.metrics["total_return"] == pytest.approx((1 - 0.001) ** 2 - 1)
    assert r.metrics["trades"] == 1


def test_trades_listed_including_open_one():
    close = prices([100, 101, 102, 103, 104, 105])
    pos = pd.Series([1, 1, 0, 0, 1, 1], index=close.index)
    t = run(close, pos, cost_bps=0).trades
    assert len(t) == 2
    assert t["Open"].tolist() == [False, True]


def test_synthetic_runs_end_to_end():
    close = data.synthetic(days=500)
    r = run(close, strategy.above_sma(close), cost_bps=5)
    assert 0 < r.metrics["time_in_market"] < 1
    assert r.daily["Equity"].notna().all()
