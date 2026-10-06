# Trading Strategy Notes

A living record of the trader's rules and what the backtests say about them.
Update it whenever a rule is added, changed, or tested.

## About the trader

- Swing trader (days to weeks); sometimes trades intraday with options and common stock.
- Goal: find and refine an edge, and teach these rules to Claude so the research builds on them.
- Entry and exit factors beyond the ones below are still to come from the trader.

## The trader's rules so far

| Rule | Detail | Where in code |
| --- | --- | --- |
| 50-day filter | Only trade stocks above their 50 SMA; don't trade those below | `entry="above_ma"` |
| Stock exit | Sell after **3 closes in a row** below the 50 SMA (not the first close) | `exit_days=3` |
| Relative strength | Trade stocks showing RS vs the market (SPY/QQQ); RS rating 70+ | `rank_by="rs_rating"`, `min_rs_rating=70` |
| Rotation | Rotate out of weakening names (losing the 50 SMA) into the strongest | `run_rotation` |
| Market gate | Only open new positions while SPY and QQQ both have fewer than 3 closes in a row below their 50 SMA; otherwise buy nothing and sell losers (below entry price) | `market_filter=True`, `market_sell="losers"` |
| Watched averages | 10 EMA, 20 EMA, 50 SMA, 100 SMA, 200 SMA | `trading/indicators.py` |
| Leader scan | Market cap $1B+, price $10+, 2M+ shares/day, $600M+ dollar volume/day, ADR 5–8% | `trading/universe.py` `leader_screen()` |

## What the backtests found (Oct 2026)

Data: daily adjusted closes from Yahoo Finance; costs 5 bps per trade; cash earns
T-bill rates. Stock baskets are picked from today's large caps, so they carry
survivorship bias: always compare against holding the same basket.

### Market environment (`research_environment.py`)
- **Fast averages (10/20 EMA, 50 SMA) on SPY/QQQ do not predict returns.** Days
  below them actually had *higher* average next-day returns, because sharp
  rebounds happen in weak markets. What they do predict is **volatility**:
  volatility roughly doubles below the 50/200 SMA.
- **Slow signals worked best as an "in or cash" switch:** SPY above its 200 SMA,
  50 SMA above 200 SMA, or "in unless SPY is below its 200 SMA *and* the 50 SMA is
  falling." They switch about 1–7 times a year and cut the worst drop from −55%
  to about −21% to −34%.
- **The 3-closes-under-50d gate switches about 11 times a year** and mostly sells
  dips that recover. Pausing new buys (without selling) beats selling losers.
- **Index extension matters:** SPY 6–10% above its 50 SMA and QQQ more than 10% above
  had weak or negative returns afterwards. Don't chase new positions when the index is
  stretched.
- Breadth (% of stocks above their 50d) under 30% came before strong 10-day
  bounces. It's a "look for longs" signal, not a "go to cash" signal.

### Stock setups (`research_stocks.py`, ~110 large caps 2006–2026)
- RS rating effects are small inside large caps; **RS 90+** stood out (+1.0% vs
  SPY per 20 days) but with more big losers (10% lost >10%).
- **Market regime decides whether RS works:** RS 70+ stocks beat SPY by 0.7% per
  20 days in an SPY uptrend and by 0% in a downtrend, where 11% lost more than 10%.
- "Stacked MA pullback to the 20 EMA" in a downtrend lost money; in an uptrend it was fine.
- Extended RS leaders (>15% above the 50 SMA) kept going in uptrends, but with fat
  tails (12% lost more than 10% within 20 days). Size them smaller.

### Best combined system so far (`research_portfolio.py`)
**RS rating 70+, above the 50 SMA, top 10 by RS, sell after 3 closes below the 50 SMA,
and stay invested unless SPY is below its 200 SMA with a falling 50 SMA.**

| | CAGR | Max DD | Sharpe |
| --- | --- | --- | --- |
| SPY buy & hold (2006–2026) | 11.2% | −55% | 0.65 |
| QQQ buy & hold | 16.0% | −53% | 0.79 |
| Equal-weight basket | 16.5% | −50% | 0.88 |
| **Best system** | **19.9%** | **−31%** | **0.95** |

It beat the basket in both 2006–15 and 2016–26. Fewer slots (5) raised return to
~26% but drawdown to −43%; 15–20 slots gave ~16% with −24%. On smaller baskets the
market rule still halved drawdowns, but RS selection added little.

Exits: 3 closes under the 50 SMA beat 3 under the 20 EMA (slightly) and the 10 EMA
(clearly) for this holding-period style. Requiring a full MA stack lowered drawdown
but also returns; waiting for a pullback to the 20 EMA hurt returns.

### The leader scan (`research_leaders.py`, whole US market, Oct 2026)
The scan is applied point-in-time to all ~6,200 Yahoo-listed US stocks (splits undone
so price/share filters use the price as traded). RS ratings are ranked against the
whole market, like IBD. Delisted stocks are missing from Yahoo, so failed names
(e.g. 2021 SPACs) are absent and results are flattered.

- **$600M+ dollar volume is very strict:** 0–3 names pass on a typical day before 2020,
  ~15 in 2020–22, ~34 in 2026. Full-period portfolio results are mostly cash; judge
  it on 2020+ or use $200M (~16/day since 2006, ~36/day since 2020).
- **The scan alone is not an edge.** Holding every passer lost money (−95% to −98%
  drawdowns): ADR 5–8% also catches collapsing stocks. RS and trend do the work.
- **RS 90+ (vs whole market) is the sweet spot:** +3.5% vs SPY per 20 days, against ≈0
  for RS 50–79. Stacked MAs helped (+3.5% vs +2.1%).
- **Don't fear extension in leaders:** in SPY uptrends, RS 70+ passers 20–35%+ above the
  50 SMA or 10–20%+ above the 20 EMA did *better* over 20 days than ones near the
  averages. More than 5% *under* the 20 EMA was the weak spot (−1.7% vs SPY).
- **SPY-based market rules fail for this group.** From Feb 2021 to Oct 2023 the portfolio
  fell 53% while SPY rose 11%: high-ADR growth crashed with SPY above its 200 SMA.
- **Measure the environment on the leaders themselves** (`leader_environment()`: an
  equal-weight index and breadth of stocks with $100M+/day and ADR 4%+):
  - Leader index 10 EMA > 20 EMA as the in/out switch cut max drawdown from −53% to −29%
    *and* raised return.
  - Best overall: **RS 90+, all MAs stacked, top 10, exit 3 closes < 50 SMA, 100% invested
    when the leader index is above its 50 SMA, 50% when only leader breadth > 40%, else
    cash.** $200M scan: 37.6% CAGR / −32% max DD / Sharpe 1.27 since 2020 (QQQ 21.2% /
    −35% / 0.90); 12.7% / −32% / 0.80 since 2006. $600M scan since 2020: 22.4% / −26% / 1.00.
- The 3-closes-under-50 exit vs 20 EMA exit was close; the 20 EMA exit did slightly better
  on the $200M scan since 2020 (40.7% vs 38.0% with the breadth rule).

## Open questions / next tests
- Trader's own entry triggers and exits (to come).
- Confirm the intended dollar-volume threshold ($600M as stated, or lower).
- Per-trade stops sized off ADR (high-ADR names need them; portfolio drawdowns are still ~30%).
- Survivorship-free data (delisted stocks) for the scan.
- Position sizing by volatility; leverage only in the "in" environment.
- Stops and profit targets at the trade level (these backtests use rule exits only).
- Intraday/options behavior can't be tested with daily data; needs intraday data.
