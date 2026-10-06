"""Compare every 50-day-based rule in trading/strategy.py against buy and hold.

Examples:
    python compare_rules.py SPY QQQ AAPL
    python compare_rules.py SPY --start 2000-01-01 --end 2015-01-01
    python compare_rules.py SPY --no-cash-interest
"""

import argparse
from pathlib import Path

import pandas as pd

from trading import data
from trading.backtest import run
from trading.strategy import RULES

COLUMNS = {
    "cagr": "CAGR",
    "total_return": "Total",
    "max_drawdown": "Max DD",
    "sharpe": "Sharpe",
    "time_in_market": "In mkt",
    "trades": "Trades",
}


def compare(close, cash, cost_bps):
    rows = {}
    for name, rule in RULES.items():
        r = run(close, rule(close), cost_bps, cash)
        rows[name] = r.metrics | {"equity": r.daily["Equity"]}
    rows["Buy & hold"] = r.benchmark | {"time_in_market": 1.0, "trades": 1, "equity": r.daily["BuyHold"]}
    table = pd.DataFrame(rows).T.sort_values("cagr", ascending=False)
    return table


def show(ticker, table, start, end):
    bh = table.loc["Buy & hold"]
    print(f"\n{ticker}: {start} to {end}   (sorted by annual return; * = beats buy & hold)")
    print(f"  {'Rule':30}{'CAGR':>8}{'Total':>10}{'Max DD':>9}{'Sharpe':>8}{'In mkt':>8}{'Trades':>8}")
    for name, row in table.iterrows():
        flags = ("*" if row.cagr > bh.cagr and name != "Buy & hold" else " ")
        print(
            f"{flags} {name:30}{row.cagr:>8.1%}{row.total_return:>10.0%}{row.max_drawdown:>9.1%}"
            f"{row.sharpe:>8.2f}{row.time_in_market:>8.0%}{int(row.trades):>8}"
        )


def plot(ticker, table, out_dir="charts"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6))
    top = [n for n in table.index if n != "Buy & hold"][:4]
    for name in top:
        ax.plot(table.loc[name, "equity"], label=name, linewidth=1.2)
    ax.plot(table.loc["Buy & hold", "equity"], label="Buy & hold", color="black", linewidth=1.6)
    ax.set_yscale("log")
    ax.set_title(f"{ticker}: growth of $1 (log scale), top 4 rules vs buy & hold")
    ax.legend(loc="upper left")
    fig.tight_layout()
    Path(out_dir).mkdir(exist_ok=True)
    path = Path(out_dir) / f"{ticker}_compare.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*", default=["SPY"])
    p.add_argument("--start", default="2000-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--cost-bps", type=float, default=5.0)
    p.add_argument("--no-cash-interest", action="store_true", help="cash earns 0%% instead of T-bill rates")
    p.add_argument("--no-plot", action="store_true")
    args = p.parse_args()

    cash = None if args.no_cash_interest else data.cash_rate(args.start, args.end)
    for ticker in args.tickers:
        close = data.download(ticker, args.start, args.end)
        table = compare(close, cash, args.cost_bps)
        show(ticker.upper(), table, close.index[0].date(), close.index[-1].date())
        if not args.no_plot:
            print(f"  Chart saved to {plot(ticker.upper(), table)}")


if __name__ == "__main__":
    main()
