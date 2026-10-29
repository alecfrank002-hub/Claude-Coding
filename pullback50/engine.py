"""Signal detection and trade simulation for the 50-day undercut-and-reclaim study.

Signal (day i):  low < prior low  AND  low < SMA50  AND  close > prior low  AND  close > SMA50

Every simulation reads plain numpy arrays for one ticker and walks forward day
by day, using only information available at each point. Fill rules:

* Entry A: next day's open.
* Entry B: buy stop at signal-day high + $0.01, valid the 3 trading days after
  the signal. A day that opens above the stop fills at the open.
* Stops are fixed at entry. A day that opens through the stop fills at the
  open; otherwise the stop fills at the stop price.
* If the stop and the target are both reached on the same day, the stop wins.
* On a buy-stop entry day the stop is checked against the whole day's low
  (we can't know whether the low came before or after the fill).
* The 24% target fills at the target price, even on a gap above it.
* "Close below the 20 EMA" exits at the next day's open.
* The no-stop version exits at the close of its 20th trading day.
* Every buy and every sell pays 0.1% slippage.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

SLIPPAGE = 0.001
ACCOUNT = 100_000.0
RISK_PCT = 0.01
MAX_POSITION_PCT = 0.25
NO_STOP_POSITION_PCT = RISK_PCT / 0.08  # 12.5%: sized like the 8% stop
TARGET_PCT = 0.24
TIME_EXIT_DAYS = 20
LOOKAHEAD_DAYS = 60
B_VALID_DAYS = 3
B_TICK = 0.01

ENTRIES = ("A", "B")
STOPS = ("pct7", "pct8", "siglow", "atr15", "none")
EXITS = ("target24", "ema20")
STOP_LABELS = {"pct7": "7%", "pct8": "8%", "siglow": "Signal-day low", "atr15": "1.5x ATR(14)", "none": "None (20-day time exit)"}
EXIT_LABELS = {"target24": "24% target", "ema20": "Close < 20 EMA"}
ENTRY_LABELS = {"A": "A: next-day open", "B": "B: buy stop above signal high"}


def add_indicators(df):
    """SMA50, EMA20 and Wilder ATR(14) on daily OHLC (columns Open, High, Low, Close)."""
    out = df.copy()
    out["sma50"] = out["Close"].rolling(50, min_periods=50).mean()
    out["ema20"] = out["Close"].ewm(span=20, adjust=False, min_periods=20).mean()
    prev_close = out["Close"].shift(1)
    tr = pd.concat([out["High"] - out["Low"], (out["High"] - prev_close).abs(), (out["Low"] - prev_close).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return out


def signal_mask(df):
    """True on days that meet all four signal conditions."""
    prev_low = df["Low"].shift(1)
    return (
        (df["Low"] < prev_low)
        & (df["Low"] < df["sma50"])
        & (df["Close"] > prev_low)
        & (df["Close"] > df["sma50"])
    ).fillna(False)


@dataclass
class Bars:
    """One ticker's arrays, aligned by trading day."""
    dates: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    ema20: np.ndarray
    atr14: np.ndarray

    @classmethod
    def from_frame(cls, df):
        return cls(df.index.values, *(df[c].to_numpy(float) for c in ("Open", "High", "Low", "Close", "ema20", "atr14")))

    def __len__(self):
        return len(self.close)


def find_entry(b, i, entry):
    """Return (entry day index, fill price incl. slippage, gapped) or None if no fill."""
    n = len(b)
    if entry == "A":
        if i + 1 >= n:
            return None
        return i + 1, b.open[i + 1] * (1 + SLIPPAGE), False
    trigger = b.high[i] + B_TICK
    for j in range(i + 1, min(i + 1 + B_VALID_DAYS, n)):
        if b.open[j] >= trigger:
            return j, b.open[j] * (1 + SLIPPAGE), True
        if b.high[j] >= trigger:
            return j, trigger * (1 + SLIPPAGE), False
    return None


def stop_level(stop, entry_px, sig_low, atr):
    if stop == "pct7":
        return entry_px * 0.93
    if stop == "pct8":
        return entry_px * 0.92
    if stop == "siglow":
        return sig_low
    if stop == "atr15":
        return entry_px - 1.5 * atr
    return None


def size_position(stop, entry_px, stop_px):
    """Whole shares risking 1% of the account, capped at 25% of the account.

    The no-stop version uses a fixed 12.5% position (the 8% stop's size), and its
    "risk" for R purposes is 8% of that position.
    """
    if stop == "none":
        shares = int(ACCOUNT * NO_STOP_POSITION_PCT // entry_px)
        return shares, entry_px * 0.08
    risk_ps = entry_px - stop_px
    shares = int(min(ACCOUNT * RISK_PCT / risk_ps, ACCOUNT * MAX_POSITION_PCT / entry_px))
    return shares, risk_ps


def first_hit(b, j0, entry_px, stop_px, target_px, entry_kind, last=None):
    """Which of the stop and target levels price reaches first within the
    lookahead window from the entry day (stop wins ties). Returns
    (label, day index or None)."""
    end = min(j0 + LOOKAHEAD_DAYS, len(b)) if last is None else last
    for j in range(j0, end):
        if stop_px is not None and b.low[j] <= stop_px and not (j == j0 and entry_kind == "A" and b.open[j] <= stop_px):
            return "stop", j
        if b.high[j] >= target_px:
            return "target", j
    return "neither", None


def simulate(b, i, entry, stop, exit_mode, sig_low, atr):
    """Simulate one trade from signal day i.

    Returns ("trade", dict) or ("skip", reason) with reason in
    {"no_fill", "stop_above_entry", "no_data"}.
    """
    found = find_entry(b, i, entry)
    if found is None:
        return ("skip", "no_fill") if entry == "B" and i + 1 < len(b) else ("skip", "no_data")
    j0, entry_px, gapped = found
    stop_px = stop_level(stop, entry_px, sig_low, atr)
    if stop_px is not None and (not np.isfinite(stop_px) or stop_px >= entry_px):
        return ("skip", "stop_above_entry")
    shares, risk_ps = size_position(stop, entry_px, stop_px)
    if shares < 1:
        return ("skip", "no_data")
    target_px = entry_px * (1 + TARGET_PCT)

    n = len(b)
    pending_ema = False
    exit_j = exit_raw = None
    reason = None
    lo, hi = np.inf, -np.inf
    for j in range(j0, n):
        if j > j0 and pending_ema:
            exit_j, exit_raw, reason = j, b.open[j], "ema20"
            lo, hi = min(lo, b.open[j]), max(hi, b.open[j])
            break
        # Stop first (conservative).
        if stop_px is not None:
            if j > j0 and b.open[j] <= stop_px:
                exit_j, exit_raw, reason = j, b.open[j], "stop_gap"
                lo, hi = min(lo, b.open[j]), max(hi, b.open[j])
                break
            if b.low[j] <= stop_px:
                exit_j, exit_raw, reason = j, stop_px, "stop"
                lo, hi = min(lo, stop_px), max(hi, b.high[j] if j == j0 else b.open[j])
                break
        if exit_mode == "target24" and b.high[j] >= target_px:
            exit_j, exit_raw, reason = j, target_px, "target"
            lo, hi = min(lo, b.low[j]), max(hi, target_px)
            break
        lo, hi = min(lo, b.low[j]), max(hi, b.high[j])
        if stop == "none" and j - j0 + 1 >= TIME_EXIT_DAYS:
            exit_j, exit_raw, reason = j, b.close[j], "time"
            break
        if exit_mode == "ema20" and np.isfinite(b.ema20[j]) and b.close[j] < b.ema20[j]:
            pending_ema = True
    if exit_j is None:
        exit_j, exit_raw, reason = n - 1, b.close[n - 1], "open_at_end"

    exit_px = exit_raw * (1 - SLIPPAGE)
    pnl = shares * (exit_px - entry_px)
    risk_dollars = shares * risk_ps
    # Levels used for "which hit first": the trade's stop (8% for the no-stop version) and +24%.
    ref_stop = stop_px if stop_px is not None else entry_px * 0.92
    hit, hit_j = first_hit(b, j0, entry_px, ref_stop, target_px, entry)
    later_target = None
    if reason in ("stop", "stop_gap"):
        end = min(j0 + LOOKAHEAD_DAYS, n)
        later_target = bool(exit_j + 1 < end and np.nanmax(b.high[exit_j + 1:end]) >= target_px)
    return ("trade", {
        "entry_date": b.dates[j0], "entry_price": round(entry_px, 4), "entry_gap_fill": gapped,
        "stop_price": None if stop_px is None else round(stop_px, 4),
        "target_price": round(target_px, 4) if exit_mode == "target24" else None,
        "shares": shares, "position_value": round(shares * entry_px, 2), "risk_dollars": round(risk_dollars, 2),
        "exit_date": b.dates[exit_j], "exit_price": round(exit_px, 4), "exit_reason": reason,
        "days_held": exit_j - j0 + 1, "pnl": round(pnl, 2), "r_multiple": round(pnl / risk_dollars, 4),
        "mae_pct": round(lo / entry_px - 1, 4), "mfe_pct": round(hi / entry_px - 1, 4),
        "first_hit_60d": hit, "stopped_then_target_60d": later_target,
        "_entry_idx": j0, "_exit_idx": exit_j,
    })


def signal_excursions(b, i):
    """Signal-level stats from an Entry A fill, over the next 60 trading days.

    Returns dict with the worst drawdown, whether it breached -7% / -8%, and
    whether +24% was reached on a later day than each breach.
    """
    if i + 1 >= len(b):
        return None
    j0 = i + 1
    entry = b.open[j0] * (1 + SLIPPAGE)
    end = min(j0 + LOOKAHEAD_DAYS, len(b))
    lows, highs = b.low[j0:end], b.high[j0:end]
    out = {"mae60_pct": float(lows.min() / entry - 1), "mfe60_pct": float(highs.max() / entry - 1),
           "hit24_60d": bool((highs >= entry * (1 + TARGET_PCT)).any())}
    for lvl in (7, 8):
        breach = np.nonzero(lows <= entry * (1 - lvl / 100))[0]
        out[f"breach{lvl}"] = bool(len(breach))
        if len(breach):
            k = breach[0]
            out[f"breach{lvl}_then24"] = bool((highs[k + 1:] >= entry * (1 + TARGET_PCT)).any())
        else:
            out[f"breach{lvl}_then24"] = None
    return out


def run_ticker(ticker, df, spy_regime, rs):
    """All signals and all 20 versions for one ticker.

    Returns (trades list, skipped-signal rows, signal rows list). Skip reasons:
    overlap, no_fill (entry B), stop_above_entry, no_data.
    One open position per stock per version: a signal is skipped while that
    version still holds the stock or has a buy-stop order working.
    """
    df = add_indicators(df)
    sig = signal_mask(df)
    b = Bars.from_frame(df)
    idx = np.nonzero(sig.to_numpy())[0]
    trades, skips, signals = [], [], []
    for i in idx:
        d = df.index[i]
        exc = signal_excursions(b, i)
        signals.append({"ticker": ticker, "signal_date": d, "regime": spy_regime.get(d, "unknown"),
                        "rs_proxy": rs.get(d, np.nan), **(exc or {})})
    for entry in ENTRIES:
        for stop in STOPS:
            for exit_mode in EXITS:
                busy_until = -1
                for i in idx:
                    if i <= busy_until:
                        skips.append((entry, stop, exit_mode, ticker, df.index[i], "overlap"))
                        continue
                    kind, res = simulate(b, i, entry, stop, exit_mode, b.low[i], b.atr14[i])
                    if kind == "skip":
                        skips.append((entry, stop, exit_mode, ticker, df.index[i], res))
                        if res == "no_fill":
                            busy_until = i + B_VALID_DAYS
                        continue
                    busy_until = res["_exit_idx"] - 1  # a signal on the exit day can be taken
                    d = df.index[i]
                    trades.append({"entry_type": entry, "stop_type": stop, "exit_type": exit_mode, "ticker": ticker,
                                   "signal_date": d, "regime": spy_regime.get(d, "unknown"),
                                   "rs_proxy": rs.get(d, np.nan), "atr14_signal": round(b.atr14[i], 4),
                                   "signal_low": b.low[i], "signal_high": b.high[i], **res})
    return trades, skips, signals
