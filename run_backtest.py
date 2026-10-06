"""Backtest the 50-day moving average filter: trade a stock only while it's above its 50-day SMA.

Examples:
    python run_backtest.py SPY AAPL MSFT
    python run_backtest.py NVDA --start 2018-01-01 --window 50 --cost-bps 5
    python run_backtest.py --csv my_prices.csv
    python run_backtest.py --demo        # synthetic prices, no internet needed
"""

import argparse
from pathlib import Path

from trading import data, report, strategy
from trading.backtest import run


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*", default=["SPY"], help="ticker symbols (default: SPY)")
    p.add_argument("--start", default="2015-01-01", help="first date, YYYY-MM-DD")
    p.add_argument("--end", default=None, help="last date, YYYY-MM-DD (default: today)")
    p.add_argument("--window", type=int, default=50, help="moving average length in days")
    p.add_argument("--cost-bps", type=float, default=5.0, help="cost per buy or sell in basis points")
    p.add_argument("--csv", help="use prices from this CSV (Date, Close columns) instead of downloading")
    p.add_argument("--demo", action="store_true", help="use synthetic prices")
    p.add_argument("--no-plot", action="store_true", help="skip saving charts")
    p.add_argument("--trades", action="store_true", help="print every trade")
    args = p.parse_args()

    if args.demo:
        series = {"DEMO": data.synthetic()}
    elif args.csv:
        series = {Path(args.csv).stem.upper(): data.load_csv(args.csv)}
    else:
        series = {t.upper(): data.download(t, args.start, args.end) for t in args.tickers}

    for ticker, close in series.items():
        position = strategy.above_sma(close, args.window)
        result = run(close, position, args.cost_bps)
        print(report.summary(ticker, result, args.window))
        if args.trades:
            print(result.trades.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        if not args.no_plot:
            path = report.plot(ticker, result, strategy.sma(close, args.window), args.window)
            print(f"  Chart saved to {path}")


if __name__ == "__main__":
    main()
