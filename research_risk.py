"""Build and test the risk-on / risk-off gauge.

The gauge answers "should I be trading leaders right now?", so it is tested on
the leader index itself (an always-available, equal-weight basket of liquid,
fast stocks) and on QQQ, then on the actual leader strategy.

1. Each component alone as an in/out switch.
2. Keep only components that helped in the TRAIN period (2008-2018).
3. Judge the combined gauge on the TEST period (2019-today), unseen when choosing.

    python research_risk.py
"""

import pandas as pd

from trading import data
from trading.backtest import _stats, run
from trading.portfolio import Settings, run_rotation
from trading.risk import components, gauge, smooth_zone, zone_exposure
from trading.universe import leader_environment, leader_screen, load, rs_rating_market

START, TRAIN_END, TEST_START = "2008-01-01", "2018-12-31", "2019-01-01"


def periods(rets):
    return {"train": _stats(rets[START:TRAIN_END]), "test": _stats(rets[TEST_START:])}


def fmt(s):
    return f"{s['cagr']:6.1%} {s['max_drawdown']:6.0%} {s['sharpe']:5.2f}"


def switch_test(close, exposure, cash):
    """Trade `close` with a 0 / 0.5 / 1 exposure series (5 bps per change)."""
    c = close.loc[START:]
    return periods(run(c, exposure.reindex(c.index).fillna(1.0), 5.0, cash).daily["StrategyReturn"])


def main():
    all_adj, panels = load()
    spy = data.download("SPY", "1998-01-01")
    qqq = data.download("QQQ", "1998-01-01")
    cash = data.cash_rate("1998-01-01")
    idx = spy.loc["2004-01-01":].index
    panels = {k: v.reindex(idx) for k, v in panels.items()}
    spy, qqq = spy.reindex(idx), qqq.reindex(idx)
    leader_index, _ = leader_environment(panels)
    comp = components(panels, idx)

    head = f"  {'':40}{'LEADER INDEX train | test (CAGR DD Sharpe)':^46}{'QQQ test':^22}{'% on':>6}"
    print("Each component alone decides exposure (1 = in, 0.5 = half, 0 = cash). Train 2008-18, test 2019-today.\n")
    print(head)
    always = pd.Series(1.0, index=idx)
    base_l, base_q = switch_test(leader_index, always, cash), switch_test(qqq, always, cash)
    print(f"  {'(always invested)':40}{fmt(base_l['train']):>22} |{fmt(base_l['test']):>21}{fmt(base_q['test']):>22}")
    scores = {}
    for name in comp.columns:
        e = comp[name].fillna(1.0)
        l, q = switch_test(leader_index, e, cash), switch_test(qqq, e, cash)
        scores[name] = l
        print(f"  {name:40}{fmt(l['train']):>22} |{fmt(l['test']):>21}{fmt(q['test']):>22}{comp[name].loc[START:].mean():>6.0%}")

    helpful = [n for n, st in scores.items() if st["train"]["sharpe"] > base_l["train"]["sharpe"] + 0.05]
    print(f"\nKept (improved TRAIN Sharpe on the leader index by > 0.05): {len(helpful)} of {len(comp.columns)}")
    for n in helpful:
        print(f"   - {n}")

    gauges = {"All components": gauge(comp), "Train-selected components": gauge(comp, helpful)}
    print("\nCombined gauge, smoothed (5-day avg; Risk-On >= 65 until < 55, Risk-Off < 35 until > 45):")
    print(head)
    zones = {}
    for name, g in gauges.items():
        z = smooth_zone(g)
        zones[name] = z
        e = zone_exposure(z)
        l, q = switch_test(leader_index, e, cash), switch_test(qqq, e, cash)
        changes = (z.loc[START:] != z.loc[START:].shift()).sum() / (len(z.loc[START:]) / 252)
        print(f"  {name:40}{fmt(l['train']):>22} |{fmt(l['test']):>21}{fmt(q['test']):>22}   {changes:.0f} changes/yr")

    final_name = "Train-selected components" if helpful else "All components"
    z = zones[final_name]
    fwd = leader_index.shift(-20) / leader_index - 1
    vol = leader_index.pct_change().rolling(20).std().shift(-20) * (252 ** 0.5)
    print(f"\nWhat happened next, by zone ({final_name}, 2008-today):")
    print(f"  {'Zone':10}{'% days':>8}{'Leader idx next 20d':>21}{'Up':>6}{'Next-20d vol':>14}")
    for name in ("Risk-On", "Neutral", "Risk-Off"):
        m = (z == name) & (z.index >= START)
        print(f"  {name:10}{m.mean() / (z.index >= START).mean():>8.0%}{fwd[m].mean():>21.2%}{(fwd[m] > 0).mean():>6.0%}{vol[m].mean():>14.0%}")

    # The actual leader strategy ($200M scan), test period.
    scan = leader_screen(panels, min_dollars=200e6)
    rs = rs_rating_market(all_adj.reindex(idx), panels["adj"].columns)
    strat = Settings(slots=10, rank_by="rs_rating", min_rs_rating=90, entry="stacked")
    print("\nLeader strategy ($200M scan, RS 90+, stacked, top 10, exit 3 < 50 SMA), 2019-today:")
    for name, e in (("No market rule", None), (f"Gauge zones ({final_name})", zone_exposure(z)),
                    ("Leader index > 50 SMA (previous best)", comp["Leader index > 50 SMA"].fillna(1.0))):
        r, m, _ = run_rotation(panels["adj"], spy, strat, cash, TEST_START, None, e, universe=scan, rs=rs)
        print(f"  {name:44}{fmt(_stats(r))}")

    g = gauges[final_name]
    print(f"\nToday ({idx[-1].date()}): gauge {g.iloc[-1]:.0f}/100, 5-day avg {g.rolling(5).mean().iloc[-1]:.0f} -> {z.iloc[-1]}")
    for name in comp.columns:
        v = comp[name].iloc[-1]
        mark = "ON " if v == 1 else ("MIX" if v == 0.5 else "OFF")
        print(f"   {'*' if name in helpful else ' '} [{mark}] {name}")
    print("   (* = in the final gauge)")
    out = comp.copy()
    out.insert(0, "zone", z)
    out.insert(0, "gauge", g)
    out.to_csv(data.CACHE_DIR / "risk_gauge.csv")


if __name__ == "__main__":
    main()
