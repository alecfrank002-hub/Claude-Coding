# Claude-Coding

A stock backtesting toolkit. The first strategy is a **50-day moving average filter**:
a stock is only traded while it closes above its 50-day simple moving average (SMA).
When it closes below, the position is sold and held in cash.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python run_backtest.py SPY AAPL MSFT                # download and backtest these tickers
python run_backtest.py NVDA --start 2018-01-01      # choose the date range
python run_backtest.py SPY --window 20 --trades     # different SMA length; list every trade
python run_backtest.py --csv my_prices.csv          # your own data (Date, Close columns)
python run_backtest.py --demo                       # synthetic prices, no internet needed
```

Each run prints strategy stats next to buy-and-hold over the same period
(return, CAGR, volatility, Sharpe, max drawdown, time in market, trade count,
win rate) and saves a chart to `charts/`.

## Comparing rule variations

```bash
python compare_rules.py SPY QQQ AAPL                          # all rules, 2000 to today
python compare_rules.py SPY --start 2015-01-01                # a different period
python compare_rules.py SPY --no-cash-interest                # cash earns 0%
```

Runs every rule in `RULES` (`trading/strategy.py`) and prints a table sorted by
annual return, with buy & hold included and `*` marking rules that beat it. Rules:

| Rule | Holds the stock when |
| --- | --- |
| Above 50d (baseline) | close > 50-day SMA |
| 50d with 2% / 3% buffer | buys 2–3% above the SMA, sells only 2–3% below it |
| 50d, 3-day confirm | flips only after 3 closes in a row on the other side |
| 50d, checked weekly | above the SMA at Friday's close |
| Above 50d & 50d rising | close > SMA and the SMA is higher than 10 days ago |
| 50d > 200d (golden cross) | 50-day SMA > 200-day SMA |
| Exit only if <50d & 50d<200d | always, unless close < 50-day *and* 50-day < 200-day |
| 2x when ... | same as the named rule, but 2x exposure using borrowed money |

Cash earns the 13-week T-bill rate (`^IRX`). Borrowed money for 2x rules pays
that rate plus 1% a year.

## How the backtest works

- Prices are split- and dividend-adjusted daily closes from Yahoo Finance, cached in `data/`.
- At each close: if close > 50-day SMA, hold the stock; otherwise hold cash.
  The first 49 days, before the SMA exists, count as "don't trade".
- The trade fills at that same close, and the position earns the next day's return
  (no look-ahead into future prices).
- `--cost-bps` (default 5 = 0.05%) is charged on every buy and every sell.

## Project layout

| File | Purpose |
| --- | --- |
| `run_backtest.py` | Command-line entry point |
| `trading/data.py` | Downloading, caching, CSV loading, synthetic prices |
| `compare_rules.py` | Runs all rules side by side |
| `trading/strategy.py` | Trading rules and the `RULES` list |
| `trading/backtest.py` | Backtest engine, trade list, performance stats |
| `trading/report.py` | Text summary and charts |
| `tests/` | Unit tests (`python -m pytest`) |

## Running in a Claude Code cloud session

Yahoo Finance must be allowed by the environment's network policy. Add
`query1.finance.yahoo.com`, `query2.finance.yahoo.com` and `fc.yahoo.com` under
Network access → Allowed domains, or use `--demo` / `--csv` meanwhile.
