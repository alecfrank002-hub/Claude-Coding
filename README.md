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

## Relative-strength rotation (baskets)

```bash
python rotation.py                      # every basket in trading/baskets.py
python rotation.py sectors large_caps   # just these baskets
```

Holds the top N names in a basket that are above their 50-day SMA and beating
the market (return over the last 3 months minus SPY's or QQQ's). A holding is
sold after **3 closes in a row below its 50-day**, or at the weekly check if its
relative strength falls out of the basket's top 2N, and the slot rotates into
the next strongest qualifying name.

**Market gate** (`market_filter=True`): new positions are opened only while SPY
*and* QQQ both have fewer than 3 closes in a row below their 50-day. When
either one reaches 3, nothing new is bought and losing positions (below their
entry price) are sold; winners are kept. `market_sell` can be set to `"all"` or
`"none"` to compare. Results are compared with SPY, QQQ and an
equal-weight hold of the same basket. Settings live in `trading/portfolio.py`
(`Settings`); baskets live in `trading/baskets.py`.

## Swing-trading research

See `STRATEGY.md` for the trader's rules and the findings.

```bash
python research_environment.py   # SPY/QQQ returns under MA, extension and breadth conditions; exposure rules
python research_stocks.py        # forward returns by RS rating, MA stack, pullback and market regime
python research_portfolio.py     # RS-rating rotation combined with market exposure rules
python -m trading.universe       # one-time: download the whole US market (~15 min, ~800MB in data/universe/)
python research_leaders.py       # the leader scan: scan stats, setups and portfolio tests ($600M dollar volume)
python research_leaders.py 200   # same with $200M+ dollar volume
python plot_leader_index.py      # chart the leader index, breadth and environment (last 18 months; pass a start date for more)
python research_risk.py          # build/test the risk-on/off gauge (train 2008-18, test 2019+)
python plot_risk_gauge.py        # daily risk gauge chart + checklist -> charts/risk_gauge.png
python research_macd.py          # test the weekly MACD (6,20,9) risk switch
python daily_dashboard.py        # one-screen dashboard: SPY/QQQ weekly MACD, leader index, breadth
```

`trading/indicators.py` has the 10/20 EMA, 50/100/200 SMA, an IBD-style RS rating
(1-99, ranked within the basket), MA score/stack and breadth.

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
| `compare_rules.py` | Runs all single-ticker rules side by side |
| `rotation.py` | Relative-strength rotation across baskets |
| `trading/portfolio.py` | Rotation engine and equal-weight benchmark |
| `trading/baskets.py` | Ticker baskets |
| `trading/indicators.py` | EMAs/SMAs, RS rating, MA score, breadth |
| `trading/risk.py` | Risk gauge components (incl. weekly MACD, VIX, credit, breadth) and the leader gauge |
| `trading/universe.py` | Whole-market download, leader scan, market-wide RS rating, leader environment |
| `research_*.py` | Environment, stock-setup and combined-system studies |
| `STRATEGY.md` | The trader's rules and findings |
| `trading/strategy.py` | Trading rules and the `RULES` list |
| `trading/backtest.py` | Backtest engine, trade list, performance stats |
| `trading/report.py` | Text summary and charts |
| `tests/` | Unit tests (`python -m pytest`) |

## Running in a Claude Code cloud session

Yahoo Finance must be allowed by the environment's network policy. Add
`query1.finance.yahoo.com`, `query2.finance.yahoo.com` and `fc.yahoo.com` under
Network access → Allowed domains, or use `--demo` / `--csv` meanwhile.
