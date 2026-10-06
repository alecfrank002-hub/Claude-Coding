"""Test the weekly MACD (6, 20, 9) risk-on / risk-off switch.

Rule A ("zero"):   previous week's 6 EMA > 20 EMA (weekly)       -> risk on
Rule B ("signal"): previous week's MACD line > its 9-week signal -> risk on

Applied to SPY, QQQ, both, either, and the leader index; tested on the leader
index, QQQ and the leader strategy. Train 2008-2018, test 2019-today.

    python research_macd.py
"""

import numpy as np
import pandas as pd

from research_risk import START, TEST_START, fmt, switch_test
from trading import data
from trading.backtest import _stats
from trading.portfolio import Settings, run_rotation
from trading.risk import LEADER_SIGNALS, components, download_ohlcv, macd_risk_on
from trading.universe import leader_environment, leader_screen, load, rs_rating_market


def main():
    all_adj, panels = load()
    spy_d = data.download("SPY", "1998-01-01")
    cash = data.cash_rate("1998-01-01")
    idx = spy_d.loc["2004-01-01":].index
    panels = {k: v.reindex(idx) for k, v in panels.items()}
    spy = download_ohlcv("SPY", "1998-01-01")["Close"]
    qqq = download_ohlcv("QQQ", "1999-03-10")["Close"]
    li, lb = leader_environment(panels)
    comp = components(panels, idx)
    n_lead = comp[LEADER_SIGNALS].sum(axis=1)
    leader_gauge = pd.Series(np.select([n_lead >= 3, n_lead >= 1], [1.0, 0.5], 0.0), index=idx)

    def on(close, mode, fast=6, slow=20):
        return macd_risk_on(close, fast, slow, 9, mode).reindex(idx)

    rules = {"Always invested": pd.Series(1.0, index=idx)}
    for mode, tag in (("zero", "A: 6 EMA > 20 EMA"), ("signal", "B: MACD > signal")):
        s, q, l = on(spy, mode), on(qqq, mode), on(li, mode)
        rules[f"{tag} on SPY"] = s.astype(float)
        rules[f"{tag} on QQQ"] = q.astype(float)
        rules[f"{tag} on SPY AND QQQ"] = (s & q).astype(float)
        rules[f"{tag} on SPY OR QQQ"] = (s | q).astype(float)
        rules[f"{tag} on leader index"] = l.astype(float)
    rules["Old: MACD 12/26/9 > signal, SPY AND QQQ"] = (on(spy, "signal", 12, 26) & on(qqq, "signal", 12, 26)).astype(float)
    rules["Leader gauge (3 leader signals)"] = leader_gauge
    a_both = rules["A: 6 EMA > 20 EMA on SPY AND QQQ"]
    rules["A on SPY AND QQQ, half size if leader breadth < 50%"] = a_both * np.where(lb.reindex(idx) < 0.5, 0.5, 1.0)
    rules["A on leader index, half size if leader breadth < 50%"] = rules["A: 6 EMA > 20 EMA on leader index"] * np.where(lb.reindex(idx) < 0.5, 0.5, 1.0)

    print("Exposure switches (1 = in, 0.5 = half, 0 = cash), 5 bps per change, cash earns T-bills.\n")
    print(f"  {'Rule':52}{'LEADER INDEX train':>22} |{'test':>21}{'QQQ train':>22}{'QQQ test':>22}{'% on':>6}{'flips/yr':>9}")
    for name, e in rules.items():
        e = e.reindex(idx)
        l, q = switch_test(li, e.fillna(1.0), cash), switch_test(qqq.reindex(idx), e.fillna(1.0), cash)
        part = e.loc[START:]
        flips = (part.diff().abs() > 0).sum() / (len(part) / 252)
        print(f"  {name:52}{fmt(l['train']):>22} |{fmt(l['test']):>21}{fmt(q['train']):>22}{fmt(q['test']):>22}"
              f"{(part > 0).mean():>6.0%}{flips:>9.1f}")

    scan = leader_screen(panels, min_dollars=200e6)
    rs = rs_rating_market(all_adj.reindex(idx), panels["adj"].columns)
    strat = Settings(slots=10, rank_by="rs_rating", min_rs_rating=90, entry="stacked")
    print("\nLeader strategy ($200M scan, RS 90+, stacked, top 10, exit 3 < 50 SMA), 2019-today:")
    for name in ("Always invested", "A: 6 EMA > 20 EMA on SPY AND QQQ", "A: 6 EMA > 20 EMA on QQQ",
                 "B: MACD > signal on SPY AND QQQ", "A: 6 EMA > 20 EMA on leader index", "Leader gauge (3 leader signals)",
                 "A on SPY AND QQQ, half size if leader breadth < 50%"):
        r, m, _ = run_rotation(panels["adj"], spy_d.reindex(idx), strat, cash, TEST_START, None, rules[name].fillna(1.0),
                               universe=scan, rs=rs)
        print(f"  {name:52}{fmt(_stats(r))}")

    line_s = macd_risk_on(spy, mode="zero").iloc[-1]
    line_q = macd_risk_on(qqq, mode="zero").iloc[-1]
    sig_s = macd_risk_on(spy, mode="signal").iloc[-1]
    sig_q = macd_risk_on(qqq, mode="signal").iloc[-1]
    print(f"\nToday ({idx[-1].date()}, using last completed week):")
    print(f"  Rule A (6 EMA > 20 EMA):  SPY {'ON' if line_s else 'OFF'}, QQQ {'ON' if line_q else 'OFF'}")
    print(f"  Rule B (MACD > signal):   SPY {'ON' if sig_s else 'OFF'}, QQQ {'ON' if sig_q else 'OFF'}")
    print(f"  Leader breadth: {lb.iloc[-1]:.0%}   Leader gauge: {int(n_lead.iloc[-1])}/3")


if __name__ == "__main__":
    main()
