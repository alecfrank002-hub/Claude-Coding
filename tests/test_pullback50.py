"""Fill-rule tests for the 50-day undercut-and-reclaim backtest (pullback50/engine.py)."""

import numpy as np
import pandas as pd
import pytest

from pullback50 import engine as E


def bars(rows, ema=None, atr=1.0):
    """rows: list of (open, high, low, close)."""
    a = np.array(rows, dtype=float)
    n = len(a)
    return E.Bars(
        dates=pd.bdate_range("2024-01-01", periods=n).values,
        open=a[:, 0], high=a[:, 1], low=a[:, 2], close=a[:, 3],
        ema20=np.full(n, np.nan) if ema is None else np.asarray(ema, float),
        atr14=np.full(n, atr),
    )


def test_signal_needs_all_four_conditions():
    idx = pd.bdate_range("2024-01-01", periods=3)
    df = pd.DataFrame({"Open": 100, "High": 102, "Close": [101, 101, 100.5], "Low": [99, 99, 98],
                       "sma50": [100, 100, 100]}, index=idx, dtype=float)
    # Day 3: low 98 < prior low 99, < SMA 100; close 100.5 > prior low and > SMA.
    assert E.signal_mask(df).tolist() == [False, False, True]
    df.loc[idx[2], "Close"] = 99.5  # closes below the SMA
    assert not E.signal_mask(df).iloc[2]


def test_entry_a_is_next_open_plus_slippage():
    b = bars([(100, 101, 95, 100), (102, 103, 101, 102)])
    j, px, gap = E.find_entry(b, 0, "A")
    assert j == 1 and px == pytest.approx(102 * 1.001)


def test_entry_b_gap_fills_at_open_and_expires_after_three_days():
    b = bars([(100, 105, 95, 100), (107, 108, 106, 107)])
    j, px, gap = E.find_entry(b, 0, "B")
    assert gap and px == pytest.approx(107 * 1.001)  # opened above 105.01
    b = bars([(100, 105, 95, 100), (101, 104, 99, 102), (101, 104, 99, 102), (101, 104, 99, 102), (101, 110, 99, 109)])
    assert E.find_entry(b, 0, "B") is None  # the day-4 breakout is outside the window


def test_stop_and_target_same_day_takes_stop():
    b = bars([(100, 101, 95, 100), (100, 101, 99, 100), (100, 130, 90, 100)])
    _, t = E.simulate(b, 0, "A", "pct8", "target24", 95, 1.0)
    assert t["exit_reason"] == "stop"
    assert t["exit_price"] == pytest.approx(100 * 1.001 * 0.92 * 0.999)


def test_gap_through_stop_fills_at_open():
    b = bars([(100, 101, 95, 100), (100, 101, 99, 100), (80, 85, 79, 84)])
    _, t = E.simulate(b, 0, "A", "pct8", "target24", 95, 1.0)
    assert t["exit_reason"] == "stop_gap" and t["exit_price"] == pytest.approx(80 * 0.999)


def test_target_fills_at_target_price():
    b = bars([(100, 101, 95, 100), (100, 101, 99, 100), (110, 140, 109, 135)])
    _, t = E.simulate(b, 0, "A", "pct7", "target24", 95, 1.0)
    assert t["exit_reason"] == "target"
    assert t["exit_price"] == pytest.approx(100 * 1.001 * 1.24 * 0.999)


def test_ema_exit_is_next_open():
    rows = [(100, 101, 95, 100), (100, 101, 99, 100), (100, 101, 97, 98), (96, 97, 95, 96)]
    b = bars(rows, ema=[99, 99, 99, 99])
    _, t = E.simulate(b, 0, "A", "pct8", "ema20", 95, 1.0)
    assert t["exit_reason"] == "ema20" and t["exit_price"] == pytest.approx(96 * 0.999)


def test_no_stop_exits_at_close_of_day_20_and_is_sized_like_8pct():
    rows = [(100, 101, 95, 100)] + [(100, 101, 60, 100)] * 25  # deep dips: no stop to hit
    b = bars(rows)
    _, t = E.simulate(b, 0, "A", "none", "target24", 95, 1.0)
    assert t["exit_reason"] == "time" and t["days_held"] == 20
    assert t["shares"] == int(12_500 // (100 * 1.001))


def test_entry_a_skipped_when_open_below_signal_low():
    b = bars([(100, 101, 95, 100), (94, 96, 93, 95)])
    assert E.simulate(b, 0, "A", "siglow", "target24", 95, 1.0) == ("skip", "stop_above_entry")


def test_position_capped_at_25_percent():
    shares, _ = E.size_position("siglow", 100.0, 99.5)  # 1% risk would need $200k
    assert shares == 250
