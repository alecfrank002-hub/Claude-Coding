"""Combine stock selection (RS rating, MA setups, exits) with market-environment
exposure rules, on the broad ~110-stock basket.

    python research_portfolio.py
"""

import pandas as pd

from research_environment import exposure_rules
from trading import data
from trading.backtest import _stats
from trading.baskets import BASKETS
from trading.indicators import breadth
from trading.portfolio import Settings, equal_weight, run_rotation

START = "2006-01-01"


def main():
    prices = pd.DataFrame({t: data.download(t, "2003-01-01") for t in BASKETS["broad"]["tickers"]})
    spy = data.download("SPY", "1998-01-01")
    qqq = data.download("QQQ", "1998-01-01")
    cash = data.cash_rate("1998-01-01")
    market = pd.DataFrame({"SPY": spy, "QQQ": qqq})
    env = {k: pd.Series(v, index=spy.index, dtype=float) for k, v in exposure_rules(spy, qqq, breadth(prices)).items()}
    base = dict(slots=10, rank_by="rs_rating", min_rs_rating=70)

    tests = {
        "A. Stock selection (no market rule)": [
            ("RS 70+, above 50 SMA, exit 3 closes < 50 SMA", Settings(**base), None),
            ("RS 90+, above 50 SMA, exit 3 closes < 50 SMA", Settings(**base | {"min_rs_rating": 90}), None),
            ("RS 70+, all MAs stacked, exit 3 < 50 SMA", Settings(**base, entry="stacked"), None),
            ("RS 70+, stacked pullback to 20 EMA, exit 3 < 50", Settings(**base, entry="pullback"), None),
            ("RS 70+, above 50, exit 3 closes < 20 EMA", Settings(**base, exit_ma="ema20"), None),
            ("RS 70+, above 50, exit 3 closes < 10 EMA", Settings(**base, exit_ma="ema10"), None),
            ("RS vs SPY (old method), above 50, exit 3 < 50", Settings(slots=10), None),
        ],
        "B. RS 70+, above 50, exit 3 < 50 SMA, plus a market rule": [
            ("Your gate (SPY & QQQ < 3 under 50d), sell losers", Settings(**base, market_filter=True), None),
            ("Your gate, pause buying only", Settings(**base, market_filter=True, market_sell="none"), None),
            ("In if SPY above 200 SMA", Settings(**base), env["In if SPY above 200 SMA"]),
            ("In if SPY 50 SMA > 200 SMA", Settings(**base), env["In if SPY 50 SMA > 200 SMA"]),
            ("In unless SPY < 200 SMA and 50 SMA falling", Settings(**base), env["In unless below 200 SMA AND 50 SMA falling"]),
            ("Scaled by SPY+QQQ MA score (100/50/0%)", Settings(**base), env["Score scaled: >=8 100%, 4-7 50%, <=3 cash"]),
            ("Above 200 SMA & breadth > 40%", Settings(**base), env["Above 200 SMA & breadth > 40%"]),
        ],
    }

    index = spy.loc[START:].index
    print(f"Broad basket ({prices.shape[1]} stocks), top 10 slots, {START[:4]}-today, cash earns T-bills, 5 bps costs")
    bench = {
        "SPY buy & hold": spy.reindex(index).pct_change().fillna(0),
        "QQQ buy & hold": qqq.reindex(index).pct_change().fillna(0),
        "Basket equal weight": equal_weight(prices, index),
    }
    header = f"  {'Strategy':50}{'CAGR':>7}{'MaxDD':>8}{'Sharpe':>8}{'Invest':>8}{'2006-15':>9}{'2016-':>8}"

    def line(name, rets, invested=1.0):
        m = _stats(rets)
        a, b = _stats(rets[:"2015"])["cagr"], _stats(rets["2016":])["cagr"]
        print(f"  {name:50}{m['cagr']:>7.1%}{m['max_drawdown']:>8.1%}{m['sharpe']:>8.2f}{invested:>8.0%}{a:>9.1%}{b:>8.1%}")

    print("\n--- Benchmarks ---\n" + header)
    for name, r in bench.items():
        line(name, r)
    for section, rows in tests.items():
        print(f"\n--- {section} ---\n" + header)
        for name, settings, exposure in rows:
            rets, m, holdings = run_rotation(prices, spy, settings, cash, START, market, exposure)
            line(name, rets, m["invested"])
    rets, m, holdings = run_rotation(prices, spy, Settings(**base), cash, START, market, env["In if SPY above 200 SMA"])
    today = holdings.iloc[-1]
    print(f"\nHolding today (RS 70+, above 50, SPY > 200 SMA rule): {', '.join(today[today > 0].sort_values(ascending=False).index)}")


if __name__ == "__main__":
    main()
