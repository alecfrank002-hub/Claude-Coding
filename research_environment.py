"""When is the market worth being in? Study SPY and QQQ returns under different
moving-average and breadth conditions, then backtest exposure rules built from them.

For every trading day we record the conditions at the close, then measure what
happened *afterwards*: the next day's return (annualized while the condition held),
the 10-day forward return, how often it was positive, and volatility. Conditions
with strong forward returns and low volatility are "all in" environments; weak or
volatile ones are "cash" environments.

    python research_environment.py
"""

import numpy as np
import pandas as pd

from trading import data
from trading.backtest import run, _stats
from trading.baskets import BASKETS
from trading.indicators import breadth, ma_score, moving_averages, stacked, streak

START = "2000-01-01"


def features(close, breadth_series):
    m = moving_averages(close)
    f = pd.DataFrame(index=close.index)
    f["MA score (# of 10e/20e/50/100/200 above)"] = ma_score(close)
    f["Above 10 EMA"] = close > m["ema10"]
    f["Above 20 EMA"] = close > m["ema20"]
    f["Above 50 SMA"] = close > m["sma50"]
    f["Above 100 SMA"] = close > m["sma100"]
    f["Above 200 SMA"] = close > m["sma200"]
    f["10 EMA > 20 EMA"] = m["ema10"] > m["ema20"]
    f["50 SMA > 200 SMA"] = m["sma50"] > m["sma200"]
    f["50 SMA rising (vs 10d ago)"] = m["sma50"] > m["sma50"].shift(10)
    f["All 5 MAs stacked"] = stacked(close)
    f["Under 50 SMA 3+ closes"] = streak(close < m["sma50"]) >= 3
    ext = close / m["sma50"] - 1
    f["Distance from 50 SMA"] = pd.cut(ext, [-1, -0.10, -0.05, 0, 0.03, 0.06, 0.10, 1],
                                       labels=["< -10%", "-10 to -5%", "-5 to 0%", "0 to 3%", "3 to 6%", "6 to 10%", "> +10%"])
    f["Breadth (% of stocks > 50d)"] = pd.cut(breadth_series.reindex(close.index), [0, 0.3, 0.5, 0.7, 1.0],
                                              labels=["< 30%", "30-50%", "50-70%", "> 70%"], include_lowest=True)
    return f


def outcomes(close):
    o = pd.DataFrame(index=close.index)
    o["next_day"] = close.pct_change().shift(-1)
    o["fwd10"] = close.shift(-10) / close - 1
    return o


def summarize(f, o):
    rows = []
    for col in f.columns:
        for value, idx in f.groupby(f[col], observed=True).groups.items():
            nd, f10 = o.loc[idx, "next_day"].dropna(), o.loc[idx, "fwd10"].dropna()
            if len(nd) < 60:
                continue
            rows.append({
                "factor": col, "state": str(value), "days": len(nd) / len(f.dropna(how="all")),
                "ann_return": nd.mean() * 252, "ann_vol": nd.std() * np.sqrt(252),
                "fwd10": f10.mean(), "win10": (f10 > 0).mean(),
            })
    return pd.DataFrame(rows)


def show_table(name, t):
    print(f"\n=== {name}: what happened after each condition ({START[:4]}-today) ===")
    print(f"  {'Condition':44}{'State':>12}{'% days':>8}{'Ann.ret':>9}{'Ann.vol':>9}{'Fwd 10d':>9}{'Win 10d':>9}")
    last = None
    for _, r in t.iterrows():
        label = r.factor if r.factor != last else ""
        last = r.factor
        print(f"  {label:44}{r.state:>12}{r.days:>8.0%}{r.ann_return:>9.1%}{r.ann_vol:>9.1%}{r.fwd10:>9.2%}{r.win10:>9.0%}")


def exposure_rules(spy, qqq, brd):
    """Each rule returns the fraction of money to have invested (0, 0.5 or 1)."""
    s_score, q_score = ma_score(spy), ma_score(qqq.reindex(spy.index))
    combined = s_score + q_score  # 0 to 10
    b = brd.reindex(spy.index)
    m = moving_averages(spy)
    gate = (streak(spy < m["sma50"]) < 3) & (streak(qqq < moving_averages(qqq)["sma50"]) < 3).reindex(spy.index)
    return {
        "Always in (buy & hold)": pd.Series(1.0, index=spy.index),
        "Your gate: SPY & QQQ < 3 closes under 50d": gate.astype(float),
        "In if SPY above 50 SMA": (spy > m["sma50"]).astype(float),
        "In if SPY above 200 SMA": (spy > m["sma200"]).astype(float),
        "In if SPY 50 SMA > 200 SMA": (m["sma50"] > m["sma200"]).astype(float),
        "In if SPY 10 EMA > 20 EMA": (m["ema10"] > m["ema20"]).astype(float),
        "Score: SPY+QQQ MAs >= 6 of 10 in, else cash": (combined >= 6).astype(float),
        "Score scaled: >=8 100%, 4-7 50%, <=3 cash": np.select([combined >= 8, combined >= 4], [1.0, 0.5], 0.0),
        "In unless below 200 SMA AND 50 SMA falling": (~((spy < m["sma200"]) & (m["sma50"] < m["sma50"].shift(10)))).astype(float),
        "Breadth > 50% in, else cash": (b > 0.5).astype(float),
        "Above 200 SMA & breadth > 40%": ((spy > m["sma200"]) & (b > 0.4)).astype(float),
    }


def backtest_rules(ticker, close, rules, cash, start):
    print(f"\n=== Exposure rules applied to {ticker} ({start[:4]}-today, cash earns T-bills, 5 bps costs) ===")
    print(f"  {'Rule':46}{'CAGR':>7}{'MaxDD':>8}{'Sharpe':>8}{'Invested':>10}{'Switches/yr':>13}")
    c = close.loc[start:]
    rows = []
    for name, pos in rules.items():
        pos = pd.Series(pos, index=rules["Always in (buy & hold)"].index).reindex(c.index).fillna(0)
        r = run(c, pos, 5.0, cash)
        switches = (pos.diff().abs() > 0).sum() / (len(c) / 252)
        rows.append((name, r.metrics, pos.mean(), switches))
    for name, m, inv, sw in sorted(rows, key=lambda x: -x[1]["sharpe"]):
        print(f"  {name:46}{m['cagr']:>7.1%}{m['max_drawdown']:>8.1%}{m['sharpe']:>8.2f}{inv:>10.0%}{sw:>13.1f}")


def main():
    spy = data.download("SPY", "1998-01-01")
    qqq = data.download("QQQ", "1998-01-01")
    universe = pd.DataFrame({t: data.download(t, "2003-01-01") for t in BASKETS["broad"]["tickers"]})
    brd = breadth(universe).loc["2004-06-01":]
    cash = data.cash_rate("1998-01-01")

    for name, close in (("SPY", spy), ("QQQ", qqq)):
        f = features(close, brd).loc[START:]
        o = outcomes(close).loc[START:]
        show_table(name, summarize(f, o))

    rules = exposure_rules(spy, qqq, brd)
    for start in ("2000-01-01", "2005-01-01"):
        backtest_rules("SPY", spy, {k: v for k, v in rules.items() if start != "2000-01-01" or "readth" not in k}, cash, start)
    backtest_rules("QQQ", qqq.reindex(spy.index), rules, cash, "2005-01-01")


if __name__ == "__main__":
    main()
