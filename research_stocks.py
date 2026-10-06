"""Which stock setups lead to good swing trades? Study forward returns for every
stock-day in the broad basket, grouped by RS rating, moving-average setup,
pullback depth and market environment.

Each row answers: "on days a stock looked like this at the close, what did it do
over the next 10 and 20 trading days, and did it beat SPY?"

    python research_stocks.py
"""

import numpy as np
import pandas as pd

from trading import data
from trading.baskets import BASKETS
from trading.indicators import ema, rs_rating, stacked
from trading.strategy import sma

START = "2006-01-01"


def build(prices, spy):
    """One row per stock per day with features at the close and forward returns."""
    e10, e20 = ema(prices, 10), ema(prices, 20)
    s50, s100, s200 = sma(prices, 50), sma(prices, 100), sma(prices, 200)
    rs = rs_rating(prices)
    spy_s50, spy_s200 = sma(spy, 50), sma(spy, 200)
    regime = pd.Series(
        np.select([(spy > spy_s200) & (spy_s50 > spy_s200), spy > spy_s200], ["Uptrend", "Mixed"], "Downtrend"),
        index=spy.index,
    )

    feats = {
        "rs": rs,
        "stacked": (e10 > e20) & (e20 > s50) & (s50 > s100) & (s100 > s200),
        "above50": prices > s50,
        "above200": prices > s200,
        "dist20": prices / e20 - 1,
        "dist50": prices / s50 - 1,
        "fwd10": prices.shift(-10) / prices - 1,
        "fwd20": prices.shift(-20) / prices - 1,
    }
    long = pd.concat({k: v.loc[START:].stack(future_stack=True) for k, v in feats.items()}, axis=1)
    long.index.names = ["date", "ticker"]
    long = long.dropna(subset=["rs", "fwd20"])
    spy_fwd10 = (spy.shift(-10) / spy - 1).reindex(long.index.get_level_values("date")).to_numpy()
    spy_fwd20 = (spy.shift(-20) / spy - 1).reindex(long.index.get_level_values("date")).to_numpy()
    long["xs10"] = long["fwd10"] - spy_fwd10
    long["xs20"] = long["fwd20"] - spy_fwd20
    long["regime"] = regime.reindex(long.index.get_level_values("date")).to_numpy()
    long["rs_bucket"] = pd.cut(long["rs"], [0, 50, 70, 80, 90, 100], labels=["<50", "50-69", "70-79", "80-89", "90+"], right=False)
    long["pullback"] = pd.cut(long["dist20"], [-1, -0.03, 0, 0.03, 0.08, 10],
                              labels=["> 3% under 20e", "0-3% under 20e", "0-3% over 20e", "3-8% over 20e", "> 8% over 20e"])
    return long


def table(df, by, title):
    g = df.groupby(by, observed=True)
    t = pd.DataFrame({
        "share": g.size() / len(df),
        "fwd20": g["fwd20"].mean(),
        "xs20": g["xs20"].mean(),
        "beat_spy": g["xs20"].apply(lambda x: (x > 0).mean()),
        "win20": g["fwd20"].apply(lambda x: (x > 0).mean()),
        "bad20": g["fwd20"].apply(lambda x: (x < -0.10).mean()),
    })
    print(f"\n--- {title} ---")
    print(f"  {'Group':38}{'% rows':>8}{'Fwd 20d':>9}{'vs SPY':>8}{'Beat SPY':>10}{'Up':>6}{'Lost >10%':>11}")
    for key, r in t.iterrows():
        name = " / ".join(map(str, key)) if isinstance(key, tuple) else str(key)
        print(f"  {name:38}{r.share:>8.1%}{r.fwd20:>9.2%}{r.xs20:>8.2%}{r.beat_spy:>10.0%}{r.win20:>6.0%}{r.bad20:>11.1%}")


def main():
    tickers = BASKETS["broad"]["tickers"]
    prices = pd.DataFrame({t: data.download(t, "2003-01-01") for t in tickers})
    spy = data.download("SPY", "1998-01-01").reindex(prices.index)
    df = build(prices, spy)
    print(f"{len(df):,} stock-days, {df.index.get_level_values('ticker').nunique()} stocks, {START[:4]}-today")
    print("Forward returns are measured from the close; 'vs SPY' is the stock's 20-day return minus SPY's.")

    table(df, "rs_bucket", "RS rating (IBD-style, ranked within this basket)")
    table(df, "stacked", "All 5 MAs stacked (10e > 20e > 50 > 100 > 200)")
    table(df, "pullback", "Distance from the 20 EMA (all stocks)")

    strong = df[(df["rs"] >= 70) & df["above50"]]
    table(strong, "pullback", "RS 70+ and above 50 SMA: by distance from 20 EMA")
    table(strong, "stacked", "RS 70+ and above 50 SMA: stacked or not")
    table(df[df["rs"] >= 70], "regime", "RS 70+ stocks by market regime (SPY 200 SMA / 50 vs 200)")
    table(df[df["rs"] < 50], "regime", "RS under 50 by market regime")

    setup = df[(df["rs"] >= 70) & df["stacked"] & (df["dist20"].between(-0.03, 0.03))]
    table(setup, "regime", "SETUP: RS 70+, stacked, within 3% of 20 EMA - by regime")
    chase = df[(df["rs"] >= 70) & (df["dist50"] > 0.15)]
    table(chase, "regime", "CHASE: RS 70+ but > 15% above the 50 SMA - by regime")


if __name__ == "__main__":
    main()
