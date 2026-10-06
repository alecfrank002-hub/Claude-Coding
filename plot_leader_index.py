"""Chart the leader index (equal-weight index of liquid, fast stocks) and its breadth.

    python plot_leader_index.py            # last 18 months, saved to charts/leader_index.png
    python plot_leader_index.py 2006-01-01 # any start date

Needs the market download first: `python -m trading.universe`.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["text.usetex"] = False
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, NullFormatter
import numpy as np
import pandas as pd

from trading import data
from trading.indicators import ema
from trading.strategy import sma
from trading.universe import leader_environment, load

# Reference palette (light mode)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#1f1f1e", "#6b6a64", "#e6e5e0"
BLUE, ORANGE, AQUA, GREEN = "#2a78d6", "#eb6834", "#1baf7a", "#008300"
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"


def environment(index, breadth):
    """2 = all in (index above 50 SMA), 1 = half (breadth > 40%), 0 = cash."""
    return pd.Series(np.select([index > sma(index, 50), breadth > 0.4], [2, 1], 0), index=index.index)


def shade(ax, state):
    colors = {2: GOOD, 1: WARN, 0: CRIT}
    runs = (state != state.shift()).cumsum()
    for _, run in state.groupby(runs):
        end = state.index[min(state.index.get_loc(run.index[-1]) + 1, len(state) - 1)]
        ax.axvspan(run.index[0], end, color=colors[run.iloc[0]], alpha=0.10, lw=0)


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, lw=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)


def log_axis(ax, fmt):
    """Log scale with plain-number tick labels."""
    ax.set_yscale("log")
    lo, hi = ax.get_ylim()
    ticks = [t for t in (0.5, 1, 2, 3, 5, 10, 20, 50, 100, 200, 300, 500, 1000, 2000) if lo <= t <= hi]
    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt.format(v)))
    ax.yaxis.set_minor_formatter(NullFormatter())


def label_end(ax, series, text, color, dy=0):
    ax.annotate(text, (series.index[-1], series.iloc[-1]), xytext=(6, dy), textcoords="offset points",
                color=INK, fontsize=9, va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec=color, lw=1.2))


def main(start=None):
    _, panels = load()
    spy = data.download("SPY", "1998-01-01")
    idx = spy.loc["2004-01-01":].index
    panels = {k: v.reindex(idx) for k, v in panels.items()}
    li, lb = leader_environment(panels)
    li = li / li.loc["2006-01-03"]  # readable scale: 1.0 at the start of 2006
    lines = {"Leader index": li, "10 EMA": ema(li, 10), "20 EMA": ema(li, 20), "50 SMA": sma(li, 50)}
    state = environment(li, lb)

    start = pd.Timestamp(start) if start else idx[-1] - pd.DateOffset(months=18)
    view = slice(start, None)
    full = (idx[-1] - start).days > 1500

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 10), sharex=True, height_ratios=[3, 1.2, 1.3],
                                        facecolor=SURFACE)
    for ax in (ax1, ax2, ax3):
        style(ax)
        shade(ax, state[view])

    widths = {"Leader index": 2.0, "10 EMA": 1.2, "20 EMA": 1.2, "50 SMA": 1.6}
    colors = {"Leader index": BLUE, "10 EMA": ORANGE, "20 EMA": AQUA, "50 SMA": GREEN}
    for name, s in lines.items():
        ax1.plot(s[view], color=colors[name], lw=widths[name], label=name,
                 ls="--" if name == "50 SMA" else "-")
    if full:
        log_axis(ax1, "{:.1f}")
    last = li.index[-1]
    status = {2: "ALL IN (index above 50 SMA)", 1: "HALF (index below 50 SMA, breadth > 40%)", 0: "CASH"}[state.iloc[-1]]
    ax1.set_title(f"Leader index (equal weight: $100M+/day, ADR 4%+, $10+)   |   {last.date()}: {status}",
                  loc="left", color=INK, fontsize=12, fontweight="bold")
    ax1.legend(loc="upper left", frameon=False, fontsize=9, ncol=4, labelcolor=INK)
    label_end(ax1, li[view], f"{li.iloc[-1]:.2f}", BLUE)

    # Over long spans, smooth breadth (10-day average) so the trend is readable.
    shown = lb.rolling(10).mean() if full else lb
    ax2.plot(shown[view] * 100, color=BLUE, lw=1.4 if full else 1.6)
    for level, txt in ((50, "50%"), (40, "40%")):
        ax2.axhline(level, color=INK2, lw=0.9, ls=":")
        ax2.annotate(txt, (lb[view].index[0], level), xytext=(2, 3), textcoords="offset points", color=INK2, fontsize=8)
    ax2.set_ylim(0, 100)
    ax2.set_title(f"Leader breadth: % of the group above its 50 SMA{' (10-day average)' if full else ''}   (today {lb.iloc[-1]:.0%})",
                  loc="left", color=INK, fontsize=10)

    base = li[view].index[0]
    rel_l = li[view] / li[base] * 100
    rel_s = spy.reindex(idx)[view] / spy[base] * 100
    ax3.plot(rel_l, color=BLUE, lw=1.6, label="Leader index")
    ax3.plot(rel_s, color=INK2, lw=1.4, label="SPY")
    if full:
        log_axis(ax3, "{:.0f}")
    ax3.set_title(f"Leader index vs SPY, both = 100 on {base.date()}", loc="left", color=INK, fontsize=10)
    ax3.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK)
    above = rel_l.iloc[-1] > rel_s.iloc[-1]
    label_end(ax3, rel_l, f"Leaders {rel_l.iloc[-1]:.0f}", BLUE, dy=9 if above else -9)
    label_end(ax3, rel_s, f"SPY {rel_s.iloc[-1]:.0f}", INK2, dy=-9 if above else 9)

    ax3.xaxis.set_major_locator(mdates.YearLocator() if full else mdates.MonthLocator(interval=2))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y" if full else "%b %Y"))
    fig.text(0.01, 0.005, "Background: green = all in, yellow = half size, red = cash.  "
             "Daily closes from Yahoo Finance; group membership is decided each day using only data known that day.",
             color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.015, 0.97, 1))
    Path("charts").mkdir(exist_ok=True)
    out = Path("charts") / ("leader_index_full.png" if full else "leader_index.png")
    fig.savefig(out, dpi=120, facecolor=SURFACE)
    print(f"Saved {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
