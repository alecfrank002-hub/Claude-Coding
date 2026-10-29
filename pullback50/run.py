"""Run the 50-day undercut-and-reclaim backtest and write every output.

    python -m pullback50.run            # uses cached prices (download first: python -m pullback50.download)

Outputs in pullback50/output/:
    trades.csv          every simulated trade, all 20 versions
    skipped.csv         every skipped signal per version, with the reason
    signals.csv         one row per signal: Entry-A excursions over 60 days, regime, RS proxy
    summary.csv / .md   per version x period (All, 2023-2024, 2025-2026)
    regime.csv          per version x SPY regime (above/below its 50-day SMA), all years
    rs_breakdown.csv    per version x RS-proxy quintile, all years
    yearly.csv          per version x year: trades and expectancy in R
    signal_mae.csv      % of signals breaching -7% / -8% and how many still reached +24%
    findings.md         plain-English highlights, generated from the tables
"""

import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from . import engine as E

OUT = Path(__file__).resolve().parent / "output"
PERIODS = {"All years": (None, None), "2023-2024": ("2023-01-01", "2024-12-31"), "2025-2026": ("2025-01-01", "2026-12-31")}

_FRAMES, _REGIME, _RS = {}, {}, None


def _work(ticker):
    rs = _RS[ticker].dropna().to_dict() if ticker in _RS.columns else {}
    return E.run_ticker(ticker, _FRAMES[ticker], _REGIME, rs)


def spy_regime(spy):
    sma = spy["Close"].rolling(50, min_periods=50).mean()
    reg = np.where(spy["Close"] > sma, "SPY above 50d", "SPY below 50d")
    return dict(zip(spy.index, np.where(sma.isna(), "unknown", reg)))


def rs_proxy(frames):
    """12-month (252-day) return percentile (0-100) across the universe on each date."""
    closes = pd.DataFrame({t: f["Close"] for t, f in frames.items()})
    ret = closes / closes.shift(252) - 1
    return (ret.rank(axis=1, pct=True) * 100).round(1)


def in_period(dates, period):
    lo, hi = PERIODS[period]
    m = pd.Series(True, index=dates.index)
    if lo:
        m &= dates >= lo
    if hi:
        m &= dates <= hi
    return m


def max_concurrent(tr):
    if tr.empty:
        return 0
    ev = pd.concat([pd.Series(1, index=tr["entry_date"]), pd.Series(-1, index=tr["exit_date"] + pd.Timedelta(hours=12))])
    return int(ev.sort_index(kind="stable").cumsum().max())


def longest_losing_streak(pnl):
    best = cur = 0
    for v in pnl:
        cur = cur + 1 if v <= 0 else 0
        best = max(best, cur)
    return best


def stats(tr):
    """Headline stats for one set of trades (one version, one slice)."""
    if tr.empty:
        return {"trades": 0}
    tr = tr.sort_values("exit_date", kind="stable")
    pnl, r = tr["pnl"], tr["r_multiple"]
    win, loss = pnl > 0, pnl <= 0
    equity = E.ACCOUNT + pnl.cumsum()
    peak = np.maximum.accumulate(np.r_[E.ACCOUNT, equity.to_numpy()])[1:]
    dd = equity.to_numpy() - peak
    cum_r = r.cumsum().to_numpy()
    dd_r = cum_r - np.maximum.accumulate(np.r_[0.0, cum_r])[1:]
    stopped = tr["exit_reason"].isin(["stop", "stop_gap"])
    gross_loss = -pnl[loss].sum()
    return {
        "trades": len(tr),
        "win_rate": win.mean(),
        "avg_win_$": pnl[win].mean() if win.any() else np.nan,
        "avg_loss_$": pnl[loss].mean() if loss.any() else np.nan,
        "avg_win_R": r[win].mean() if win.any() else np.nan,
        "avg_loss_R": r[loss].mean() if loss.any() else np.nan,
        "expectancy_$": pnl.mean(),
        "expectancy_R": r.mean(),
        "total_pnl_$": pnl.sum(),
        "profit_factor": pnl[win].sum() / gross_loss if gross_loss > 0 else np.nan,
        "max_drawdown_R": dd_r.min(),
        "max_drawdown_$": dd.min(),
        "longest_losing_streak": longest_losing_streak(pnl.to_numpy()),
        "stopped_%": stopped.mean(),
        "stopped_then_target_%": tr.loc[stopped, "stopped_then_target_60d"].astype(float).mean() if stopped.any() else np.nan,
        "target_hit_%": (tr["exit_reason"] == "target").mean(),
        "avg_days_held": tr["days_held"].mean(),
        "max_concurrent_positions": max_concurrent(tr),
        "gap_stop_%": (tr["exit_reason"] == "stop_gap").mean(),
        "worst_trade_R": r.min(),
        "still_open": int((tr["exit_reason"] == "open_at_end").sum()),
    }


def version_label(entry, stop, exit_mode):
    return f"{entry} · {E.STOP_LABELS[stop]} · {E.EXIT_LABELS[exit_mode]}"


def main(argv=None):
    global _FRAMES, _REGIME, _RS
    u = data.universe()
    spy = data.load("SPY")
    if spy is None:
        sys.exit("No price data. Run: python -m pullback50.download")
    frames = {t: f for t in u["all"] if (f := data.load(t)) is not None and len(f) > 260}
    print(f"Universe: {len(u['all'])} tickers ({len(u['sp500'])} S&P 500, {len(u['ndx100'])} Nasdaq-100); "
          f"{len(frames)} with data; {spy.index[0].date()} to {spy.index[-1].date()}")
    _FRAMES, _REGIME, _RS = frames, spy_regime(spy), rs_proxy(frames)

    with Pool(4) as pool:
        results = pool.map(_work, sorted(frames), chunksize=8)
    trades = pd.DataFrame([t for res in results for t in res[0]])
    skipped = pd.DataFrame([s for res in results for s in res[1]],
                           columns=["entry_type", "stop_type", "exit_type", "ticker", "signal_date", "reason"])
    signals = pd.DataFrame([s for res in results for s in res[2]])
    trades = trades.drop(columns=["_entry_idx", "_exit_idx"])
    for c in ("signal_date", "entry_date", "exit_date"):
        trades[c] = pd.to_datetime(trades[c])
    print(f"{len(signals):,} signals, {len(trades):,} simulated trades across 20 versions")

    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUT / "trades.csv", index=False)
    skipped.to_csv(OUT / "skipped.csv", index=False)
    signals.to_csv(OUT / "signals.csv", index=False)

    versions = [(e, s, x) for e in E.ENTRIES for s in E.STOPS for x in E.EXITS]
    rows = []
    for e, s, x in versions:
        tv = trades[(trades.entry_type == e) & (trades.stop_type == s) & (trades.exit_type == x)]
        sv = skipped[(skipped.entry_type == e) & (skipped.stop_type == s) & (skipped.exit_type == x)]
        for period in PERIODS:
            t = tv[in_period(tv["signal_date"], period)]
            k = sv[in_period(sv["signal_date"], period)]
            sig_n = int(in_period(signals["signal_date"], period).sum())
            rows.append({"version": version_label(e, s, x), "entry": e, "stop": s, "exit": x, "period": period,
                         "signals": sig_n, "skipped_overlap": int((k.reason == "overlap").sum()),
                         "skipped_stop_above_entry": int((k.reason == "stop_above_entry").sum()),
                         "no_fill": int((k.reason == "no_fill").sum()), **stats(t)})
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "summary.csv", index=False)

    regime = []
    for e, s, x in versions:
        tv = trades[(trades.entry_type == e) & (trades.stop_type == s) & (trades.exit_type == x)]
        for reg, t in tv.groupby("regime"):
            st = stats(t)
            regime.append({"version": version_label(e, s, x), "regime": reg, **{k: st.get(k) for k in
                           ("trades", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "expectancy_$", "max_drawdown_$")}})
    regime = pd.DataFrame(regime)
    regime.to_csv(OUT / "regime.csv", index=False)

    trades["rs_quintile"] = pd.cut(trades["rs_proxy"], [0, 20, 40, 60, 80, 100.01], right=False,
                                   labels=["RS 0-20", "RS 20-40", "RS 40-60", "RS 60-80", "RS 80-100"])
    rsb = (trades.dropna(subset=["rs_quintile"]).groupby(["entry_type", "stop_type", "exit_type", "rs_quintile"], observed=True)
           .agg(trades=("pnl", "size"), win_rate=("pnl", lambda p: (p > 0).mean()), expectancy_R=("r_multiple", "mean"))
           .reset_index())
    rsb.insert(0, "version", [version_label(e, s, x) for e, s, x in zip(rsb.entry_type, rsb.stop_type, rsb.exit_type)])
    rsb.to_csv(OUT / "rs_breakdown.csv", index=False)

    trades["year"] = trades["signal_date"].dt.year
    yearly = (trades.groupby(["entry_type", "stop_type", "exit_type", "year"])
              .agg(trades=("pnl", "size"), expectancy_R=("r_multiple", "mean"), total_pnl=("pnl", "sum")).reset_index())
    yearly.insert(0, "version", [version_label(e, s, x) for e, s, x in zip(yearly.entry_type, yearly.stop_type, yearly.exit_type)])
    yearly.to_csv(OUT / "yearly.csv", index=False)

    mae_rows = []
    for period in PERIODS:
        sg = signals[in_period(signals["signal_date"], period)].dropna(subset=["mae60_pct"])
        row = {"period": period, "signals": len(sg), "hit_24pct_within_60d_%": sg["hit24_60d"].mean()}
        for lvl in (7, 8):
            br = sg[sg[f"breach{lvl}"] == True]  # noqa: E712
            row[f"mae_worse_than_-{lvl}%_%"] = len(br) / len(sg) if len(sg) else np.nan
            row[f"of_those_later_hit_24%_%"] = br[f"breach{lvl}_then24"].astype(float).mean() if len(br) else np.nan
            row = {k if k != "of_those_later_hit_24%_%" else f"breach{lvl}_later_hit_24%_%": v for k, v in row.items()}
        mae_rows.append(row)
    signal_mae = pd.DataFrame(mae_rows)
    signal_mae.to_csv(OUT / "signal_mae.csv", index=False)

    write_markdown(summary, regime, rsb, yearly, signal_mae, signals, trades, spy)
    print(f"Wrote outputs to {OUT}")


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return {"pct": f"{v:.1%}", "R": f"{v:+.2f}R", "$": f"${v:,.0f}", "int": f"{int(v):,}", "f": f"{v:.1f}"}[kind]


def write_markdown(summary, regime, rsb, yearly, signal_mae, signals, trades, spy):
    cols = [("trades", "Trades", "int"), ("win_rate", "Win %", "pct"), ("avg_win_$", "Avg win $", "$"),
            ("avg_loss_$", "Avg loss $", "$"), ("avg_win_R", "Avg win", "R"), ("avg_loss_R", "Avg loss", "R"),
            ("expectancy_$", "Exp. $", "$"), ("expectancy_R", "Exp. R", "R"), ("max_drawdown_R", "Max DD (R)", "f"),
            ("longest_losing_streak", "Lose streak", "int"), ("stopped_then_target_%", "Stopped→24%", "pct"),
            ("avg_days_held", "Avg days", "f"),
            ("max_concurrent_positions", "Max open", "int"), ("skipped_stop_above_entry", "Skip: stop>entry", "int"),
            ("no_fill", "B no-fill", "int"), ("skipped_overlap", "Skip: overlap", "int")]
    lines = ["# 50-day undercut & reclaim: backtest summary", "",
             f"Data: {spy.index[0].date()} to {spy.index[-1].date()}, today's S&P 500 + Nasdaq-100 members "
             "(survivorship bias: stocks that left the indexes are missing). Independent trades, each sized to risk 1% "
             "of $100k (max 25% of the account per position; no-stop version uses a fixed 12.5%). 0.1% slippage per side.", "",
             "Every signal is taken (one position per stock), so many trades overlap: \"Max open\" shows the most held at once. "
             "Drawdown is therefore shown in R (the worst peak-to-trough run of cumulative R across trades in exit order); "
             "the dollar figure in summary.csv adds up all overlapping trades and is not a realistic account drawdown. "
             "\"Stopped→24%\" = share of stopped-out trades whose price still reached the +24% target within 60 trading days of entry. "
             "Trades still open at the end of the data are marked to the last close.", ""]
    for period in PERIODS:
        lines += [f"## {period}", "", "| Version | " + " | ".join(c[1] for c in cols) + " |",
                  "|---|" + "---:|" * len(cols)]
        for _, r in summary[summary.period == period].iterrows():
            lines.append(f"| {r.version} | " + " | ".join(_fmt(r.get(k), f) for k, _, f in cols) + " |")
        lines.append("")
    lines += ["## By market regime (all years)", "", "| Version | Regime | Trades | Win % | Exp. R | Exp. $ |", "|---|---|---:|---:|---:|---:|"]
    for _, r in regime[regime.regime != "unknown"].iterrows():
        lines.append(f"| {r.version} | {r.regime} | {_fmt(r.trades, 'int')} | {_fmt(r.win_rate, 'pct')} | {_fmt(r.expectancy_R, 'R')} | {_fmt(r['expectancy_$'], '$')} |")
    lines += ["", "## All signals: drawdown after entry (Entry A, next 60 trading days)", "",
              "| Period | Signals | Reached +24% | MAE worse than −7% | …then +24% later | MAE worse than −8% | …then +24% later |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for _, r in signal_mae.iterrows():
        lines.append(f"| {r.period} | {_fmt(r.signals, 'int')} | {_fmt(r['hit_24pct_within_60d_%'], 'pct')} | "
                     f"{_fmt(r['mae_worse_than_-7%_%'], 'pct')} | {_fmt(r['breach7_later_hit_24%_%'], 'pct')} | "
                     f"{_fmt(r['mae_worse_than_-8%_%'], 'pct')} | {_fmt(r['breach8_later_hit_24%_%'], 'pct')} |")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    write_findings(summary, regime, rsb, yearly, signal_mae, signals, trades)


def write_findings(summary, regime, rsb, yearly, signal_mae, signals, trades):
    """Short, data-driven highlights. Every number here is computed from the outputs."""
    allp = summary[summary.period == "All years"].set_index("version")
    a23 = summary[summary.period == "2023-2024"].set_index("version")
    a25 = summary[summary.period == "2025-2026"].set_index("version")
    top = allp.sort_values("expectancy_R", ascending=False)
    L = ["# Findings", "",
         "Generated from the backtest outputs. Expectancy is per trade in R (1R = the dollars risked on that trade). "
         "Universe is today's index members, so results are flattered by survivorship bias, more so the further back you go.", ""]

    L.append("## Best and worst versions (all years, by expectancy in R)")
    for name in list(top.index[:3]) + ["…"] + list(top.index[-2:]):
        if name == "…":
            L.append("- …")
            continue
        r = top.loc[name]
        L.append(f"- **{name}**: {_fmt(r.expectancy_R, 'R')} per trade ({_fmt(r['expectancy_$'], '$')}), win rate {_fmt(r.win_rate, 'pct')}, "
                 f"{_fmt(r.trades, 'int')} trades, avg hold {r.avg_days_held:.0f} days; "
                 f"2023-24 {_fmt(a23.loc[name, 'expectancy_R'], 'R')}, 2025-26 {_fmt(a25.loc[name, 'expectancy_R'], 'R')}.")
    pos_all = allp[allp.expectancy_R > 0].index
    both = [v for v in pos_all if a23.loc[v, "expectancy_R"] > 0 and a25.loc[v, "expectancy_R"] > 0]
    L += ["", f"- {len(pos_all)} of 20 versions are positive over all years; {len(both)} are positive in all three columns."]
    weaker = int((a25.expectancy_R < a23.expectancy_R).sum())
    L.append(f"- {weaker} of 20 versions earned less per trade in 2025-26 than in 2023-24.")

    per20 = (allp.expectancy_R / allp.avg_days_held * 20).sort_values(ascending=False)
    L += ["", "## Return per unit of time (R per 20 trading days held)",
          "Target versions earn more R per trade but hold far longer, so compare them per day of capital tied up:"]
    for name in per20.index[:3]:
        L.append(f"- {name}: {per20[name]:+.3f}R per 20 days held ({_fmt(allp.loc[name, 'expectancy_R'], 'R')} per trade over {allp.loc[name, 'avg_days_held']:.0f} days)")
    tgt = trades[trades.exit_type == "target24"]
    L.append(f"- In the 24%-target versions, {(tgt.days_held > 120).mean():.0%} of trades were held more than 120 trading days "
             f"(longest {int(tgt.days_held.max())}). {int((tgt.exit_reason == 'open_at_end').sum())} are still open and marked to the last close, "
             "most from 2025-26, so recent target results are less settled.")

    yr = yearly.pivot_table(index="version", columns="year", values="expectancy_R")
    best = top.index[0]
    L += ["", "## Consistency of the top version", f"- {best}: positive in {int((yr.loc[best] > 0).sum())} of {yr.shape[1]} calendar years "
          f"(worst {_fmt(yr.loc[best].min(), 'R')} in {int(yr.loc[best].idxmin())}, best {_fmt(yr.loc[best].max(), 'R')} in {int(yr.loc[best].idxmax())})."]

    L += ["", "## Market regime (SPY vs its 50-day SMA on the signal date)"]
    rg = regime[regime.regime != "unknown"].pivot_table(index="version", columns="regime", values="expectancy_R")
    sg = signals.dropna(subset=["mae60_pct"])
    if {"SPY above 50d", "SPY below 50d"} <= set(rg.columns):
        below_better = int((rg["SPY below 50d"] > rg["SPY above 50d"]).sum())
        r = rg.loc[best]
        g = sg.groupby("regime")[["hit24_60d", "breach8"]].mean()
        L.append(f"- Signals taken while **SPY was below its 50-day did better in {below_better} of 20 versions** "
                 f"(top version: {_fmt(r['SPY below 50d'], 'R')} below vs {_fmt(r['SPY above 50d'], 'R')} above).")
        L.append(f"- Across all signals: +24% within 60 days {g.loc['SPY below 50d', 'hit24_60d']:.1%} with SPY below vs "
                 f"{g.loc['SPY above 50d', 'hit24_60d']:.1%} above; a drop of more than 8% {g.loc['SPY below 50d', 'breach8']:.0%} vs "
                 f"{g.loc['SPY above 50d', 'breach8']:.0%}. A stock reclaiming its 50-day while the market is weak tends to bounce harder.")
        L.append(f"- {(signals.regime == 'SPY below 50d').mean():.0%} of all signals fired with SPY below its 50-day.")

    L += ["", "## RS proxy (12-month return percentile vs the universe): data only, not a filter"]
    sg = sg.assign(q=pd.cut(sg.rs_proxy, [0, 20, 40, 60, 80, 100.01], right=False, labels=["0-20", "20-40", "40-60", "60-80", "80-100"]))
    gq = sg.groupby("q", observed=True)[["hit24_60d", "breach8"]].mean()
    L.append("- The relationship is U-shaped, not \"higher is better\". +24% within 60 days by RS quintile: "
             + ", ".join(f"{q} {gq.loc[q, 'hit24_60d']:.0%}" for q in gq.index) + "; "
             "drop of more than 8%: " + ", ".join(f"{q} {gq.loc[q, 'breach8']:.0%}" for q in gq.index) + ".")
    L.append("- Both extremes move more in both directions, so in large caps this RS proxy mostly measures volatility. "
             "Test it as a filter only together with a volatility control.")
    rq = rsb.pivot_table(index="version", columns="rs_quintile", values="expectancy_R", observed=True)
    if best in rq.index:
        L.append(f"- Top version by RS quintile: " + ", ".join(f"{c} {_fmt(rq.loc[best, c], 'R')}" for c in rq.columns) + ".")

    L += ["", "## Drawdown after entry, all signals (Entry A, next 60 trading days)"]
    for _, r in signal_mae.iterrows():
        L.append(f"- {r.period}: {_fmt(r['mae_worse_than_-7%_%'], 'pct')} of signals fell more than 7% "
                 f"(only {_fmt(r['breach7_later_hit_24%_%'], 'pct')} of those reached +24% afterwards); "
                 f"{_fmt(r['mae_worse_than_-8%_%'], 'pct')} fell more than 8% ({_fmt(r['breach8_later_hit_24%_%'], 'pct')} reached +24% afterwards). "
                 f"Base rate of reaching +24% within 60 days: {_fmt(r['hit_24pct_within_60d_%'], 'pct')}.")
    L.append("- A setup that has already fallen 7-8% rarely recovers to the target, which supports using a hard stop in that range.")

    L += ["", "## Entries and exits"]
    b = summary[(summary.period == "All years") & (summary.entry == "B") & (summary.stop == "pct8") & (summary.exit == "ema20")]
    if len(b):
        r = b.iloc[0]
        eligible = r.signals - r.skipped_overlap
        L.append(f"- Entry B never filled on {r.no_fill / eligible:.0%} of eligible signals (price never cleared the signal-day high within 3 days).")
        sk = pd.read_csv(OUT / "skipped.csv", parse_dates=["signal_date"])
        nf = sk[(sk.entry_type == "B") & (sk.stop_type == "pct8") & (sk.exit_type == "ema20") & (sk.reason == "no_fill")]
        m = signals.merge(nf[["ticker", "signal_date"]].assign(nofill=True), on=["ticker", "signal_date"], how="left")
        m["nofill"] = m["nofill"].fillna(False).astype(bool)
        g = m.dropna(subset=["mae60_pct"]).groupby("nofill")[["hit24_60d", "breach8"]].mean()
        if True in g.index and False in g.index:
            L.append(f"- Those unfilled signals were weaker: {g.loc[True, 'breach8']:.0%} fell more than 8% within 60 days "
                     f"(vs {g.loc[False, 'breach8']:.0%} for the rest) and {g.loc[True, 'hit24_60d']:.1%} reached +24% "
                     f"(vs {g.loc[False, 'hit24_60d']:.1%}). The buy stop screens out some losers.")
    ema = trades[trades.exit_type == "ema20"]
    quick = (ema["exit_reason"] == "ema20") & (ema["days_held"] <= 2)
    L.append(f"- Close-below-20-EMA versions: {quick.mean():.0%} of trades were out within 2 days, because right after a 50-day undercut "
             "the 20 EMA usually sits overhead. That exit cuts most trades before they can work; the 24% target versions earn far more per trade.")
    sl = trades[trades.stop_type == "siglow"]
    gap = sl.exit_reason == "stop_gap"
    risk = (sl.entry_price - sl.stop_price) / sl.entry_price
    L.append(f"- Signal-day-low stops are tight (median {risk.median():.1%} below entry) and sometimes almost zero: {(risk < 0.005).mean():.1%} of those "
             f"trades had a stop less than 0.5% away (e.g. Entry A opening a cent above the signal low). Then a normal small loss is a huge R "
             f"(worst {sl.r_multiple.min():+.0f}R on a ${-sl.loc[sl.r_multiple.idxmin(), 'pnl']:.0f} loss), so **R averages for signal-day-low "
             f"versions are distorted; compare them in dollars**, or add a minimum stop distance. {gap.mean():.0%} of these trades gapped through the stop.")
    open_late = trades[(trades.exit_reason == "open_at_end")]
    L.append(f"- 2025-26 results include {len(open_late):,} trades still open (marked to the last close) and trades from the last few months "
             "that haven't had time to reach a +24% target, so 2025-26 is partly unfinished, especially for the target versions.")
    (OUT / "findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
