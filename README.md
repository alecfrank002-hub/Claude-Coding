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
| `trading/strategy.py` | Trading rules (`above_sma`) |
| `trading/backtest.py` | Backtest engine, trade list, performance stats |
| `trading/report.py` | Text summary and charts |
| `tests/` | Unit tests (`python -m pytest`) |

## Running in a Claude Code cloud session

Yahoo Finance must be allowed by the environment's network policy. Add
`query1.finance.yahoo.com`, `query2.finance.yahoo.com` and `fc.yahoo.com` under
Network access → Allowed domains, or use `--demo` / `--csv` meanwhile.
