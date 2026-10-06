"""One-screen daily dashboard: weekly MACD (6,20,9) risk switch + breadth.

Panels:
  1. SPY and QQQ weekly MACD (6,20,9): line, signal and histogram. Risk-on when
     the previous week's 6 EMA > 20 EMA (MACD line above zero) on both.
  2. Leader index with 10/20 EMA and 50 SMA (your stocks' own trend).
  3. Breadth: leader breadth and % of all liquid stocks above their 50 SMA.

    python daily_dashboard.py              # last 12 months -> charts/daily_dashboard.png
    python daily_dashboard.py 2021-01-01   # any start date

Needs the market download (`python -m trading.universe`).
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from plot_leader_index import AQUA, BLUE, CRIT, GOOD, GREEN, INK, INK2, ORANGE, SURFACE, WARN, shade, style
from trading import data
from trading.indicators import ema
from trading.risk import download_ohlcv, macd_risk_on, weekly_macd
from trading.strategy import sma
from trading.universe import leader_environment, load


def main(start=None):
    _, panels = load()
    spy_d = data.download("SPY", "1998-01-01")
    idx = spy_d.loc["2004-01-01":].index
    panels = {k: v.reindex(idx) for k, v in panels.items()}
    li, lb = leader_environment(panels)
    adj, close = panels["adj"], panels["close"]
    dollars = panels["dollars"].rolling(50, min_periods=50).mean()
    liquid = ((dollars >= 20e6) & (close >= 5)).astype(bool)
    market_breadth = ((adj > sma(adj, 50)) & liquid).sum(axis=1) / liquid.sum(axis=1).replace(0, np.nan)

    spy = download_ohlcv("SPY", "1998-01-01")["Close"]
    qqq = download_ohlcv("QQQ", "1999-03-10")["Close"]
    on_spy = macd_risk_on(spy, mode="zero").reindex(idx)
    on_qqq = macd_risk_on(qqq, mode="zero").reindex(idx)
    sig_spy = macd_risk_on(spy, mode="signal").reindex(idx)
    sig_qqq = macd_risk_on(qqq, mode="signal").reindex(idx)
    # 2 = both on (risk on), 1 = one on (caution), 0 = both off (risk off)
    state = (on_spy.astype(float) + on_qqq.astype(float)).where(on_spy.notna() & on_qqq.notna())

    start = pd.Timestamp(start) if start else idx[-1] - pd.DateOffset(months=12)
    view = slice(start, None)
    st = state[view].dropna().astype(int)

    fig, axes = plt.subplots(4, 1, figsize=(13, 12), sharex=True, height_ratios=[1.1, 1.1, 2, 1.2], facecolor=SURFACE)
    ax_s, ax_q, ax_l, ax_b = axes
    for ax in axes:
        style(ax)
        shade(ax, st)

    for ax, px, name in ((ax_s, spy, "SPY"), (ax_q, qqq, "QQQ")):
        line, sig = weekly_macd(px)
        line, sig = line.reindex(idx)[view], sig.reindex(idx)[view]
        hist = line - sig
        ax.bar(hist.index, hist, width=1.0, color=np.where(hist >= 0, GOOD, CRIT), alpha=0.35, lw=0)
        ax.plot(line, color=BLUE, lw=1.8, label="MACD line (6 EMA - 20 EMA)")
        ax.plot(sig, color=ORANGE, lw=1.2, label="Signal (9)")
        ax.axhline(0, color=INK2, lw=0.9)
        a = macd_risk_on(px, mode="zero").iloc[-1]
        b = macd_risk_on(px, mode="signal").iloc[-1]
        ax.set_title(f"{name} weekly MACD (6,20,9):  6 EMA {'>' if a else '<'} 20 EMA = {'RISK ON' if a else 'RISK OFF'}   |   "
                     f"MACD {'above' if b else 'below'} signal", loc="left", color=INK, fontsize=10, fontweight="bold")
        ax.legend(loc="upper left", frameon=False, fontsize=8, ncol=2, labelcolor=INK)

    li_v = li / li.loc["2006-01-03"]
    for s, c, w, ls, name in ((li_v, BLUE, 2.0, "-", "Leader index"), (ema(li_v, 10), ORANGE, 1.2, "-", "10 EMA"),
                              (ema(li_v, 20), AQUA, 1.2, "-", "20 EMA"), (sma(li_v, 50), GREEN, 1.6, "--", "50 SMA")):
        ax_l.plot(s[view], color=c, lw=w, ls=ls, label=name)
    ax_l.legend(loc="upper left", frameon=False, fontsize=9, ncol=4, labelcolor=INK)
    lead_up = li.iloc[-1] > sma(li, 50).iloc[-1]
    ax_l.set_title(f"Leader index (your kind of stocks): {'above' if lead_up else 'below'} its 50 SMA",
                   loc="left", color=INK, fontsize=10, fontweight="bold")

    ax_b.plot(lb[view] * 100, color=BLUE, lw=1.6, label="Leader breadth")
    ax_b.plot(market_breadth[view] * 100, color=INK2, lw=1.3, label="All liquid stocks")
    ax_b.axhline(50, color=INK2, lw=0.9, ls=":")
    ax_b.set_ylim(0, 100)
    ax_b.legend(loc="upper left", frameon=False, fontsize=9, ncol=2, labelcolor=INK)
    ax_b.set_title(f"Breadth: % above 50 SMA   leaders {lb.iloc[-1]:.0%}, all stocks {market_breadth.iloc[-1]:.0%}",
                   loc="left", color=INK, fontsize=10, fontweight="bold")
    ax_b.xaxis.set_major_locator(mdates.MonthLocator(interval=1 if (idx[-1] - start).days < 500 else 6))
    ax_b.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    verdict = {2: "RISK ON (SPY & QQQ 6 EMA > 20 EMA)", 1: "CAUTION (only one of SPY / QQQ on)", 0: "RISK OFF (both off)"}[int(state.iloc[-1])]
    fig.suptitle(f"Daily dashboard {idx[-1].date()}:  {verdict}", x=0.01, ha="left", color=INK, fontsize=13, fontweight="bold")
    fig.text(0.01, 0.005, "Background: green = SPY & QQQ weekly 6 EMA > 20 EMA, yellow = only one, red = neither. "
             "Weekly values use the last completed week. Data: Yahoo Finance.", color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.015, 0.98, 0.97))
    Path("charts").mkdir(exist_ok=True)
    out = Path("charts") / "daily_dashboard.png"
    fig.savefig(out, dpi=120, facecolor=SURFACE)

    print(f"Saved {out}\n\nDAILY DASHBOARD {idx[-1].date()}: {verdict}")
    print(f"  SPY weekly 6 EMA > 20 EMA: {'ON ' if on_spy.iloc[-1] else 'OFF'}   (MACD vs signal: {'above' if sig_spy.iloc[-1] else 'below'})")
    print(f"  QQQ weekly 6 EMA > 20 EMA: {'ON ' if on_qqq.iloc[-1] else 'OFF'}   (MACD vs signal: {'above' if sig_qqq.iloc[-1] else 'below'})")
    print(f"  Leader index vs 50 SMA:    {'above' if lead_up else 'below'}")
    print(f"  Leader breadth:            {lb.iloc[-1]:.0%}")
    print(f"  All-stock breadth:         {market_breadth.iloc[-1]:.0%}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
