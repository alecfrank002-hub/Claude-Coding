"""Printing and charting backtest results."""

from pathlib import Path

PCT = {"total_return", "cagr", "volatility", "max_drawdown", "time_in_market", "win_rate", "avg_trade"}
LABELS = {
    "total_return": "Total return",
    "cagr": "Annual return (CAGR)",
    "volatility": "Volatility",
    "sharpe": "Sharpe ratio",
    "max_drawdown": "Max drawdown",
    "time_in_market": "Time in market",
    "trades": "Trades",
    "win_rate": "Win rate",
    "avg_trade": "Avg trade return",
}


def _fmt(key, value):
    if value is None or value != value:  # NaN
        return "-"
    if key in PCT:
        return f"{value:.1%}"
    if key == "trades":
        return str(int(value))
    return f"{value:.2f}"


def summary(ticker, result, window):
    d = result.daily
    lines = [
        f"\n{ticker}: {d.index[0].date()} to {d.index[-1].date()}  (rule: hold only above {window}-day SMA)",
        f"  {'':24}{'Strategy':>12}{'Buy & hold':>12}",
    ]
    for key, label in LABELS.items():
        bench = _fmt(key, result.benchmark[key]) if key in result.benchmark else ""
        lines.append(f"  {label:24}{_fmt(key, result.metrics[key]):>12}{bench:>12}")
    state = "ABOVE" if d["Position"].iloc[-1] else "BELOW"
    lines.append(f"  Latest close {d['Close'].iloc[-1]:.2f} is {state} its {window}-day SMA")
    return "\n".join(lines)


def plot(ticker, result, sma_series, window, out_dir="charts"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = result.daily
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[3, 2])

    ax1.plot(d.index, d["Close"], label="Close", color="#1f4e79", linewidth=1)
    ax1.plot(d.index, sma_series.reindex(d.index), label=f"{window}-day SMA", color="#e07b00", linewidth=1)
    ax1.fill_between(d.index, d["Close"].min(), d["Close"].max(), where=d["Position"] == 1,
                     color="#2e8b57", alpha=0.08, label="In the market")
    ax1.set_title(f"{ticker}: price and {window}-day SMA")
    ax1.legend(loc="upper left")

    ax2.plot(d.index, d["Equity"], label="Strategy", color="#2e8b57")
    ax2.plot(d.index, d["BuyHold"], label="Buy & hold", color="#888888")
    ax2.set_title("Growth of $1")
    ax2.legend(loc="upper left")

    fig.tight_layout()
    Path(out_dir).mkdir(exist_ok=True)
    path = Path(out_dir) / f"{ticker}_sma{window}.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
