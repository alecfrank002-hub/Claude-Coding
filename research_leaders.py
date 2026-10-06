"""Backtest on the trader's actual scan: liquid, fast-moving leaders.

Scan (checked every day using only data known that day):
  price >= $10, avg shares traded >= 2M, avg dollar volume >= $600M, ADR 5-8%.
RS ratings are ranked against the whole US market (~6,000 stocks), like IBD.

Run `python -m trading.universe` once first to download the market (~1 hour).

    python research_leaders.py          # the scan as specified ($600M+ dollar volume)
    python research_leaders.py 200      # same scan with $200M+ dollar volume
"""

import numpy as np
import pandas as pd

from research_environment import exposure_rules
from research_stocks import table
from trading import data
from trading.backtest import _stats
from trading.indicators import ema, stacked
from trading.portfolio import Settings, run_rotation
from trading.strategy import sma
from trading.indicators import ema as _ema
from trading.universe import leader_environment, leader_screen, load, rs_rating_market, symbols

START = "2006-01-01"


def scan_stats(scan, sectors):
    counts = scan.loc[START:].sum(axis=1)
    by_year = counts.groupby(counts.index.year).mean()
    print("Stocks passing the scan on an average day:")
    print("  " + "  ".join(f"{y}: {n:.0f}" for y, n in by_year.items()))
    today = scan.iloc[-1]
    names = today[today].index.tolist()
    print(f"\nPassing the scan today ({scan.index[-1].date()}): {len(names)} stocks")
    by_sector = pd.Series({n: sectors.get(n, "?") or "?" for n in names}).groupby(lambda n: sectors.get(n, "?") or "?").size()
    print("  " + ", ".join(sorted(names)))
    print("  By sector: " + ", ".join(f"{k} {v}" for k, v in by_sector.sort_values(ascending=False).items()))


def setup_study(panels, rs, scan, spy):
    """Forward returns for every stock-day that passed the scan."""
    adj = panels["adj"]
    e20, s50, s200 = ema(adj, 20), sma(adj, 50), sma(adj, 200)
    spy_s50, spy_s200 = sma(spy, 50), sma(spy, 200)
    regime = pd.Series(np.select([(spy > spy_s200) & (spy_s50 > spy_s200), spy > spy_s200], ["Uptrend", "Mixed"], "Downtrend"),
                       index=spy.index)
    feats = {
        "pass": scan,
        "rs": rs,
        "stacked": stacked(adj),
        "above50": adj > s50,
        "dist20": adj / e20 - 1,
        "dist50": adj / s50 - 1,
        "fwd20": adj.shift(-20) / adj - 1,
    }
    long = pd.concat({k: v.loc[START:].stack(future_stack=True) for k, v in feats.items()}, axis=1)
    long = long[long["pass"] == True].dropna(subset=["rs", "fwd20"])  # noqa: E712
    dates = long.index.get_level_values(0)
    long["xs20"] = long["fwd20"] - (spy.shift(-20) / spy - 1).reindex(dates).to_numpy()
    long["regime"] = regime.reindex(dates).to_numpy()
    long["rs_bucket"] = pd.cut(long["rs"], [0, 50, 70, 80, 90, 100], labels=["<50", "50-69", "70-79", "80-89", "90+"], right=False)
    long["pullback"] = pd.cut(long["dist20"], [-1, -0.05, 0, 0.05, 0.10, 0.20, 10],
                              labels=["> 5% under 20e", "0-5% under 20e", "0-5% over 20e", "5-10% over 20e",
                                      "10-20% over 20e", "> 20% over 20e"])
    long["ext50"] = pd.cut(long["dist50"], [-1, 0, 0.10, 0.20, 0.35, 10],
                           labels=["under 50 SMA", "0-10% over 50", "10-20% over 50", "20-35% over 50", "> 35% over 50"])
    print(f"\n{len(long):,} stock-days passed the scan ({long.index.get_level_values(1).nunique()} different stocks)")
    table(long, "rs_bucket", "Scan passers by RS rating (vs whole market)")
    table(long, "regime", "Scan passers by market regime")
    leaders = long[(long["rs"] >= 70) & long["above50"]]
    table(leaders, "regime", "RS 70+ and above 50 SMA, by market regime")
    up = leaders[leaders["regime"] == "Uptrend"]
    table(up, "pullback", "RS 70+, above 50, SPY uptrend: distance from 20 EMA")
    table(up, "ext50", "RS 70+, above 50, SPY uptrend: distance from 50 SMA")
    table(up, "stacked", "RS 70+, above 50, SPY uptrend: all MAs stacked?")


def leader_rules(panels, index):
    """Market rules measured on the leader group instead of SPY."""
    li, lb = leader_environment(panels)
    above50 = li > sma(li, 50)
    return {
        "leader index 10 EMA > 20 EMA": (_ema(li, 10) > _ema(li, 20)).astype(float),
        "leader breadth > 40% above 50d": (lb > 0.4).astype(float),
        "leader idx > 50 SMA 100%, else breadth > 40% 50%": pd.Series(np.select([above50, lb > 0.4], [1.0, 0.5], 0.0), index=index),
    }


def portfolio_tests(panels, rs, scan, spy, qqq, cash):
    adj = panels["adj"]
    market = pd.DataFrame({"SPY": spy, "QQQ": qqq})
    env = {k: pd.Series(v, index=spy.index, dtype=float) for k, v in exposure_rules(spy, qqq, pd.Series(0.5, index=spy.index)).items()}
    slow = env["In unless below 200 SMA AND 50 SMA falling"]
    lead = leader_rules(panels, spy.index)
    best = Settings(slots=10, rank_by="rs_rating", min_rs_rating=90, entry="stacked")
    base = dict(slots=10, rank_by="rs_rating", min_rs_rating=70)
    tests = [
        ("RS 70+, above 50, exit 3 < 50 SMA, no market rule", Settings(**base), None),
        ("  + your gate (SPY&QQQ 3 closes < 50d), sell losers", Settings(**base, market_filter=True), None),
        ("  + your gate, pause buying only", Settings(**base, market_filter=True, market_sell="none"), None),
        ("  + in unless SPY < 200 SMA & 50 SMA falling", Settings(**base), slow),
        ("  + in if SPY above 200 SMA", Settings(**base), env["In if SPY above 200 SMA"]),
        ("  + in if SPY 50 SMA > 200 SMA", Settings(**base), env["In if SPY 50 SMA > 200 SMA"]),
        ("Slow rule, exit 3 closes < 20 EMA", Settings(**base, exit_ma="ema20"), slow),
        ("Slow rule, exit 3 closes < 10 EMA", Settings(**base, exit_ma="ema10"), slow),
        ("Slow rule, entry needs all MAs stacked", Settings(**base, entry="stacked"), slow),
        ("Slow rule, RS 90+", Settings(**base | {"min_rs_rating": 90}), slow),
        ("Slow rule, top 5", Settings(**base | {"slots": 5}), slow),
        ("Slow rule, top 20", Settings(**base | {"slots": 20}), slow),
        ("RS 70+, exit 3 < 50, leader idx 10 EMA > 20 EMA", Settings(**base), lead["leader index 10 EMA > 20 EMA"]),
        ("RS 70+, exit 3 < 20 EMA, leader breadth > 40%", Settings(**base, exit_ma="ema20"), lead["leader breadth > 40% above 50d"]),
        ("RS 90+ stacked, leader idx/breadth scaled", best, lead["leader idx > 50 SMA 100%, else breadth > 40% 50%"]),
    ]
    idx = spy.loc[START:].index
    nxt = adj.pct_change().shift(-1)
    held_scan = scan.shift(1).reindex(idx).fillna(False).astype(bool)
    ew = adj.pct_change().reindex(idx).where(held_scan).mean(axis=1).fillna(0)  # hold every scan passer equally

    header = f"  {'Strategy':54}{'CAGR':>7}{'MaxDD':>8}{'Sharpe':>8}{'Invest':>8}{'Turn/yr':>9}{'2006-15':>9}{'2016-':>8}"

    def line(name, rets, m=None):
        st = _stats(rets)
        a, b = _stats(rets[:"2015"])["cagr"], _stats(rets["2016":])["cagr"]
        inv = m["invested"] if m else 1.0
        turn = f"{m['turnover']:.0f}x" if m else "-"
        print(f"  {name:54}{st['cagr']:>7.1%}{st['max_drawdown']:>8.1%}{st['sharpe']:>8.2f}{inv:>8.0%}{turn:>9}{a:>9.1%}{b:>8.1%}")

    print("\n--- Portfolio backtests on the scan (5 bps costs per trade, cash earns T-bills) ---\n" + header)
    line("SPY buy & hold", spy.reindex(idx).pct_change().fillna(0))
    line("QQQ buy & hold", qqq.reindex(idx).pct_change().fillna(0))
    line("Hold every scan passer, equal weight (no costs)", ew)
    last = None
    for name, settings, exposure in tests:
        rets, m, holdings = run_rotation(adj, spy, settings, cash, START, market, exposure, universe=scan, rs=rs)
        line(name, rets, m)
        if name.startswith("  + in unless"):
            last = holdings.iloc[-1]
    print(f"\nHolding today (RS 70+, above 50, slow market rule): {', '.join(last[last > 0].sort_values(ascending=False).index)}")


def main(min_dollars=600e6):
    all_adj, panels = load()
    spy = data.download("SPY", "1998-01-01")
    qqq = data.download("QQQ", "1998-01-01")
    cash = data.cash_rate("1998-01-01")
    idx = spy.loc["2004-01-01":].index
    panels = {k: v.reindex(idx) for k, v in panels.items()}
    all_adj = all_adj.reindex(idx)
    spy, qqq = spy.reindex(idx), qqq.reindex(idx)

    scan = leader_screen(panels, min_dollars=min_dollars)
    rs = rs_rating_market(all_adj, panels["adj"].columns)
    sectors = symbols()["sector"].to_dict()
    print(f"Universe: {all_adj.shape[1]:,} US stocks downloaded, {panels['adj'].shape[1]:,} ever liquid (> $50M/day)\n")
    scan_stats(scan, sectors)
    setup_study(panels, rs, scan, spy)
    portfolio_tests(panels, rs, scan, spy, qqq, cash)


if __name__ == "__main__":
    import sys

    main(float(sys.argv[1]) * 1e6 if len(sys.argv) > 1 else 600e6)  # e.g. `python research_leaders.py 200` for $200M
