"""Relative-strength rotation backtest across baskets of stocks.

Hold the top N names in a basket that are above their 50-day SMA and beating
the market (SPY or QQQ) over the last 3 months. Sell after 3 closes in a row
below the 50-day, and rotate into the next strongest name.

Market gate: open new positions only while SPY and QQQ both have fewer than 3
closes in a row below their 50-day. Otherwise, buy nothing and sell losers.

Examples:
    python rotation.py                      # every basket in trading/baskets.py
    python rotation.py sectors large_caps   # just these baskets
"""

import argparse
from pathlib import Path

import pandas as pd

from trading import data
from trading.backtest import _stats
from trading.baskets import BASKETS
from trading.portfolio import Settings, equal_weight, run_rotation


def variants(n_names):
    """Strategies to compare, and the label of the main one."""
    small, big = (3, 5) if n_names < 15 else (5, 10)
    gate = dict(market_filter=True)
    main = f"Top {big}, market gate, sell losers"
    return main, {
        f"Top {big}, no market gate": ("SPY", Settings(slots=big)),
        main: ("SPY", Settings(slots=big, **gate)),
        f"Top {big}, market gate, sell all": ("SPY", Settings(slots=big, **gate, market_sell="all")),
        f"Top {big}, market gate, sell nothing": ("SPY", Settings(slots=big, **gate, market_sell="none")),
        f"Top {small}, market gate, sell losers": ("SPY", Settings(slots=small, **gate)),
        f"Top {big}, RS vs QQQ, market gate, sell losers": ("QQQ", Settings(slots=big, **gate)),
    }


def warmup_start(start):
    return (pd.Timestamp(start) - pd.DateOffset(years=2)).strftime("%Y-%m-%d")


def load(tickers, start):
    closes = {}
    for t in tickers:
        try:
            closes[t] = data.download(t, start)
        except RuntimeError as e:
            print(f"  skipping {t}: {e}")
    return pd.DataFrame(closes)


def evaluate(name, cfg, cash):
    fetch = warmup_start(cfg["start"])
    prices = load(cfg["tickers"], fetch)
    bench = {b: data.download(b, fetch) for b in ("SPY", "QQQ")}
    index = bench["SPY"].loc[cfg["start"]:].index

    market = pd.DataFrame(bench)
    main, strategies = variants(prices.shape[1])
    results = {}
    for label, (bname, settings) in strategies.items():
        rets, metrics, holdings = run_rotation(prices, bench[bname], settings, cash, cfg["start"], market)
        results[label] = metrics | {"returns": rets}
        if label == main:
            latest = (label, holdings.iloc[-1])
    for b in ("SPY", "QQQ"):
        rets = bench[b].reindex(index).pct_change().fillna(0)
        results[f"{b} buy & hold"] = _stats(rets) | {"avg_names": 1, "invested": 1, "turnover": 0, "returns": rets}
    ew = equal_weight(prices, index)
    results["Basket, equal weight hold"] = _stats(ew) | {"avg_names": prices.shape[1], "invested": 1, "turnover": None, "returns": ew}
    return pd.DataFrame(results).T.sort_values("cagr", ascending=False), latest


def split_cagr(rets):
    half = len(rets) // 2
    return [_stats(part)["cagr"] for part in (rets.iloc[:half], rets.iloc[half:])]


def show(name, cfg, table):
    idx = table.iloc[0]["returns"].index
    mid = idx[len(idx) // 2].year
    print(f"\n=== {name} ({len(cfg['tickers'])} names): {idx[0].date()} to {idx[-1].date()} ===")
    print(f"  {'Strategy':48}{'CAGR':>7}{'MaxDD':>8}{'Sharpe':>8}{'Names':>7}{'Invest':>8}"
          f"{'to ' + str(mid):>9}{'after':>8}")
    for label, row in table.iterrows():
        first, second = split_cagr(row["returns"])
        print(f"  {label:48}{row.cagr:>7.1%}{row.max_drawdown:>8.1%}{row.sharpe:>8.2f}"
              f"{row.avg_names:>7.1f}{row.invested:>8.0%}{first:>9.1%}{second:>8.1%}")


def plot(name, table, out_dir="charts"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6))
    strategies = [n for n in table.index if "hold" not in n][:3]
    for label in strategies:
        ax.plot((1 + table.loc[label, "returns"]).cumprod(), label=label, linewidth=1.2)
    styles = {"SPY buy & hold": "black", "QQQ buy & hold": "#777777", "Basket, equal weight hold": "#b5651d"}
    for label, color in styles.items():
        ax.plot((1 + table.loc[label, "returns"]).cumprod(), label=label, color=color, linewidth=1.4, linestyle="--")
    ax.set_yscale("log")
    ax.set_title(f"{name}: growth of $1 (log scale), top 3 strategies vs benchmarks")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    Path(out_dir).mkdir(exist_ok=True)
    path = Path(out_dir) / f"rotation_{name}.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("baskets", nargs="*", default=list(BASKETS), help=f"choose from: {', '.join(BASKETS)}")
    p.add_argument("--no-plot", action="store_true")
    args = p.parse_args()

    cash = data.cash_rate("1998-01-01")
    for name in args.baskets:
        cfg = BASKETS[name]
        table, (label, latest) = evaluate(name, cfg, cash)
        show(name, cfg, table)
        held = latest[latest > 0].sort_values(ascending=False)
        print(f"  Holding today under '{label}': {', '.join(held.index) or 'all cash'}")
        if not args.no_plot:
            print(f"  Chart saved to {plot(name, table)}")


if __name__ == "__main__":
    main()
