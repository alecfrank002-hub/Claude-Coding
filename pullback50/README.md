# 50-day undercut & reclaim backtest

Tests buying large caps that dip below their 50-day SMA intraday and close back above it.

**Signal (day t):** low < prior low · low < 50-day SMA · close > prior low · close > 50-day SMA

**Universe:** today's S&P 500 + Nasdaq-100 members (518 tickers), daily split/dividend-adjusted
OHLCV from Yahoo Finance, 2015 to today. Survivorship bias applies: stocks that left the indexes
or were delisted are missing.

## Versions tested (2 × 5 × 2 = 20)

| Entry | Stop | Exit |
| --- | --- | --- |
| A: next-day open | 7% below entry | 24% target |
| B: buy stop at signal-day high + $0.01, valid 3 days | 8% below entry | Close below the 20 EMA (sell next open) |
| | Signal-day low | |
| | 1.5 × ATR(14) as of the signal-day close, below entry | |
| | None, with a 20-day time exit (close of day 20) | |

## Rules

- **Fills:** Entry B fills at the open if the day opens above the buy stop. A stop gapped through
  fills at the open. Stop and target on the same day: stop first. On a buy-stop entry day the stop
  is checked against the whole day's low. Targets fill at the target price. 0.1% slippage on
  every buy and sell.
- **Sizing:** risk 1% of a $100k account, whole shares, max 25% of the account per position. The
  no-stop version uses a fixed 12.5% position (the 8% stop's size); its R uses 8% as the risk.
- **Independent trades:** every signal is traded, one open position per stock per version. A
  signal is skipped while that version holds the stock or has a buy stop working. Max concurrent
  positions is reported so finalists can be rerun on a shared account.
- **Skips logged:** overlap, Entry B no-fill, stop at or above entry (Entry A opening below the
  signal-day low with the signal-low stop).
- **Look-ahead:** each day only uses data up to that day; indicators use the signal-day close.

## Run

```bash
python -m pullback50.download    # first time (or --refresh to add new days), ~5 min
python -m pullback50.run         # ~30 s, writes pullback50/output/
python -m pytest tests/test_pullback50.py
```

## Outputs (`pullback50/output/`)

| File | Contents |
| --- | --- |
| `summary.md` / `summary.csv` | Per version × period (All years, 2023–2024, 2025–2026): trades, win rate, avg win/loss in $ and R, expectancy in $ and R, max drawdown (R and $), longest losing streak, % stopped then later hit +24%, avg days held, max concurrent positions, skip and no-fill counts |
| `findings.md` | Plain-English highlights computed from the tables |
| `trades.csv.gz` | Every trade: entry, exit, stop, target, shares, P&L, R, MAE, MFE, which of stop/+24% was hit first within 60 days, stopped-then-target flag, SPY regime, RS proxy |
| `regime.csv` | Per version × SPY above/below its 50-day SMA on the signal date |
| `rs_breakdown.csv` | Per version × RS-proxy quintile (12-month return percentile vs the universe) |
| `yearly.csv` | Per version × calendar year |
| `signal_mae.csv` | Across all signals (Entry A, 60 days): % with MAE worse than −7% / −8%, and of those % that later reached +24% |
| `signals.csv.gz`, `skipped.csv.gz` | One row per signal; one row per skipped signal per version |

`trades.csv`, `signals.csv` and `skipped.csv` are regenerated uncompressed by each run (git-ignored).

## Reading the results

- Drawdown and losing streaks are measured over trades in exit order. With hundreds of
  overlapping trades they show how losses cluster, not what one real account would see.
- Signal-day-low stops are sometimes only cents away, so a normal loss becomes a huge R.
  Compare those versions in dollars.
- 2025–2026 contains trades still open (marked to the last close) and recent trades that haven't
  had time to reach +24%.
