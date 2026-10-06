"""Daily risk-on / risk-off chart and checklist.

Top: leader index with 10/20 EMA and 50 SMA, shaded by the leader gauge
(green = Risk-On 100%, yellow = Neutral 50%, red = Risk-Off cash).
Bottom: every risk component over the same period (green = on, yellow = mixed,
red = off), so you can see what's agreeing and what isn't.

    python plot_risk_gauge.py              # last 12 months -> charts/risk_gauge.png
    python plot_risk_gauge.py 2020-01-01   # any start date

Needs the market download (`python -m trading.universe`).
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np
import pandas as pd

from plot_leader_index import AQUA, BLUE, CRIT, GOOD, GREEN, INK, INK2, ORANGE, SURFACE, WARN, shade, style
from trading import data
from trading.indicators import ema
from trading.risk import LEADER_SIGNALS, components, leader_gauge
from trading.strategy import sma
from trading.universe import leader_environment, load


def main(start=None):
    _, panels = load()
    spy = data.download("SPY", "1998-01-01")
    idx = spy.loc["2004-01-01":].index
    panels = {k: v.reindex(idx) for k, v in panels.items()}
    li, _ = leader_environment(panels)
    comp = components(panels, idx)
    zones = leader_gauge(comp)

    start = pd.Timestamp(start) if start else idx[-1] - pd.DateOffset(months=12)
    view = slice(start, None)
    state = zones.map({"Risk-On": 2, "Neutral": 1, "Risk-Off": 0})

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 10), sharex=True, height_ratios=[2.2, 1.6], facecolor=SURFACE)
    style(ax1)
    shade(ax1, state[view].dropna().astype(int))
    li_v = li / li.loc["2006-01-03"]
    for s, c, w, ls, name in ((li_v, BLUE, 2.0, "-", "Leader index"), (ema(li_v, 10), ORANGE, 1.2, "-", "10 EMA"),
                              (ema(li_v, 20), AQUA, 1.2, "-", "20 EMA"), (sma(li_v, 50), GREEN, 1.6, "--", "50 SMA")):
        ax1.plot(s[view], color=c, lw=w, ls=ls, label=name)
    ax1.legend(loc="upper left", frameon=False, fontsize=9, ncol=4, labelcolor=INK)
    today = zones.iloc[-1]
    on = int(comp[LEADER_SIGNALS].iloc[-1].sum())
    ax1.set_title(f"Leader gauge {idx[-1].date()}: {today.upper()} ({on}/3 leader signals on)   "
                  f"green = 100%, yellow = 50%, red = cash", loc="left", color=INK, fontsize=12, fontweight="bold")

    # Component heat strip: rows = components, columns = days.
    order = LEADER_SIGNALS + [c for c in comp.columns if c not in LEADER_SIGNALS]
    strip = comp.loc[view, order].T
    dates = mdates.date2num(strip.columns.to_pydatetime())
    cmap = ListedColormap([CRIT, WARN, GOOD])
    ax2.imshow(strip.to_numpy() * 2, aspect="auto", cmap=cmap, vmin=0, vmax=2, interpolation="nearest",
               extent=(dates[0], dates[-1], len(order) - 0.5, -0.5))
    labels = [f"{'> ' if c in LEADER_SIGNALS else '   '}{c}" for c in order]
    ax2.set_yticks(range(len(order)))
    ax2.set_yticklabels(labels, fontsize=8.5, color=INK)
    for i, c in enumerate(order):
        v = comp[c].iloc[-1]
        txt = "ON" if v == 1 else ("MIX" if v == 0.5 else ("OFF" if v == 0 else "-"))
        ax2.annotate(txt, (1.005, 1 - (i + 0.5) / len(order)), xycoords="axes fraction", fontsize=8, va="center",
                     color=INK, fontweight="bold")
    ax2.axhline(len(LEADER_SIGNALS) - 0.5, color=SURFACE, lw=3)
    ax2.set_title("All risk components (rows marked > drive the gauge; the rest are context).  green = on, yellow = mixed, red = off",
                  loc="left", color=INK, fontsize=10)
    for side in ("top", "right", "left", "bottom"):
        ax2.spines[side].set_visible(False)
    ax2.tick_params(colors=INK2, labelsize=9, length=0)
    ax2.xaxis_date()
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=1 if (idx[-1] - start).days < 500 else 6))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.setp(ax2.get_xticklabels(), rotation=0)

    fig.text(0.01, 0.005, "Leader gauge = leader index > 50 SMA, leader index 10 EMA > 20 EMA, leader breadth > 50%. "
             "3 on = Risk-On, 1-2 = Neutral, 0 = Risk-Off. Daily closes from Yahoo Finance.", color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.015, 0.97, 1))
    Path("charts").mkdir(exist_ok=True)
    out = Path("charts") / "risk_gauge.png"
    fig.savefig(out, dpi=120, facecolor=SURFACE)

    print(f"Saved {out}\n\nRISK GAUGE {idx[-1].date()}: {today.upper()}  ({on}/3 leader signals)")
    for c in order:
        v = comp[c].iloc[-1]
        print(f"  {'>' if c in LEADER_SIGNALS else ' '} {'ON ' if v == 1 else ('MIX' if v == 0.5 else 'OFF')}  {c}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
