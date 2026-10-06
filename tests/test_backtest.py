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


def test_buffer_ignores_small_dips():
    # Price wiggles 1% under a flat average; a 2% buffer keeps holding.
    close = prices([100] * 5 + [103, 99.5, 101, 99.2, 100.5])
    plain = strategy.above_sma(close, 5)
    buffered = strategy.sma_buffer(close, 5, 0.02)
    assert plain.iloc[5:].tolist() != [1] * 5
    assert buffered.iloc[5:].tolist() == [1] * 5


def test_confirm_needs_consecutive_days():
    close = prices([100] * 5 + [110, 90, 110, 111, 112])
    pos = strategy.sma_confirm(close, 3, days=2)
    assert pos.iloc[5:7].tolist() == [0, 0]  # one up day then a drop: no entry yet
    assert pos.iloc[-1] == 1


def test_cash_earns_interest_and_leverage_pays_it():
    close = prices([100] * 3)
    rate = pd.Series(0.001, index=close.index)
    cash_only = run(close, pd.Series(0, index=close.index), cost_bps=0, cash_rate=rate)
    assert cash_only.metrics["total_return"] == pytest.approx(1.001**2 - 1)
    lev = run(close, pd.Series(2, index=close.index), cost_bps=0, cash_rate=rate, borrow_spread=0)
    assert lev.daily["StrategyReturn"].iloc[1:].tolist() == pytest.approx([-0.001, -0.001])


def test_all_rules_produce_valid_positions():
    from trading.strategy import RULES

    close = data.synthetic(days=600)
    for name, rule in RULES.items():
        pos = rule(close)
        assert pos.index.equals(close.index), name
        assert set(pos.unique()) <= {0, 1, 2}, name


def test_rotation_exits_after_three_closes_below_sma():
    from trading.portfolio import Settings, run_rotation

    idx = pd.bdate_range("2020-01-01", periods=12)
    up = [100 + i for i in range(8)]
    a = pd.Series(up + [90, 88, 86, 84], index=idx, dtype=float)  # falls below its 3-day SMA
    bench = pd.Series(100.0, index=idx)
    prices = pd.DataFrame({"A": a})
    settings = Settings(slots=1, window=3, rs_lookback=2, exit_days=3, cost_bps=0)
    _, _, holdings = run_rotation(prices, bench, settings)
    held = (holdings["A"] > 0).tolist()
    assert held[7] is True
    assert held[8] and held[9]  # first two closes below: still held
    assert not held[10]  # third close below: sold


def test_rotation_picks_strongest_name():
    from trading.portfolio import Settings, run_rotation

    idx = pd.bdate_range("2020-01-01", periods=10)
    prices = pd.DataFrame({
        "SLOW": [100 + i for i in range(10)],
        "FAST": [100 + 3 * i for i in range(10)],
    }, index=idx, dtype=float)
    bench = pd.Series(100.0, index=idx)
    _, _, holdings = run_rotation(prices, bench, Settings(slots=1, window=3, rs_lookback=2, cost_bps=0))
    assert holdings["FAST"].iloc[-1] > 0
    assert holdings["SLOW"].iloc[-1] == 0


def test_market_gate_needs_three_closes_below_on_either_index():
    from trading.portfolio import market_on

    idx = pd.bdate_range("2020-01-01", periods=10)
    spy = pd.Series([100 + i for i in range(6)] + [90, 88, 86, 84], index=idx, dtype=float)
    qqq = pd.Series([100 + i for i in range(10)], index=idx, dtype=float)
    on = market_on(pd.DataFrame({"SPY": spy, "QQQ": qqq}), window=3, days=3)
    assert on.iloc[6] and on.iloc[7]  # SPY one and two closes below: still on
    assert not on.iloc[8]  # third close below: off


def test_market_off_sells_losers_keeps_winners():
    from trading.portfolio import Settings, run_rotation

    idx = pd.bdate_range("2020-01-01", periods=8)
    prices = pd.DataFrame({
        "WIN": [100, 101, 102, 110, 120, 130, 140, 150],
        "LOSE": [100, 101, 102, 103, 101, 99, 98, 97],
    }, index=idx, dtype=float)
    bench = pd.Series(100.0, index=idx)
    market = pd.DataFrame({"SPY": [100, 101, 102, 103, 104, 50, 40, 30]}, index=idx, dtype=float)
    # exit_days=99 turns off the stock exit, so only the market rule can sell.
    settings = Settings(slots=2, window=2, rs_lookback=1, exit_days=99, cost_bps=0, market_filter=True)
    _, _, h = run_rotation(prices, bench, settings, market=market)
    assert h["WIN"].iloc[-1] > 0
    assert h["LOSE"].iloc[-1] == 0
