# Trading Rulebook

The rules in one place, with what the backtests say each one does. Details and the
full research history are in `STRATEGY.md`. Numbers come from tests on 2006–2026
daily data (Yahoo Finance), with 5 bps costs and cash earning T-bill rates.
"Worst drop" = maximum drawdown (largest fall from a peak).

## Daily routine (~2 minutes)

1. Run `python daily_dashboard.py` (or `python plot_risk_gauge.py`).
2. Check the **season**: SPY & QQQ weekly MACD (6,20,9).
3. Check **your stocks**: leader index and leader breadth.
4. Set size from the table below, then trade the top RS names from the scan.

| SPY & QQQ weekly MACD | Leader index / breadth | Action |
| --- | --- | --- |
| Both on | Strong (3/3 leader signals) | Full size |
| Both on | Weak (1–2 signals) | Half size, A+ setups only |
| One or both off | Strong | Half size, be picky |
| Off | Weak (0 signals) | Cash, no new swing trades |

## Layer 1: When to trade (market environment)

| # | Rule | Effect | Evidence |
| --- | --- | --- | --- |
| 1 | **Weekly MACD (6,20,9) on SPY & QQQ:** previous week's 6 EMA > 20 EMA = risk on; < = risk off. After a down cross, wait for the first weekly close with a MACD up cross. | Cuts index drawdowns; does not predict higher returns | QQQ 2019–26: worst drop −35% → −20%, Sharpe 1.01 → 1.09; 2008–18: −49% → −28%. ~2 switches/yr |
| 2 | **Leader index & breadth** (stocks with $100M+/day, ADR 4%+): index > 50 SMA, 10 EMA > 20 EMA, breadth > 50%. 3/3 = full, 1–2 = half, 0 = cash | Cuts drawdowns on *your* stocks, which the MACD can't see | Leader strategy 2019–26: worst drop −34% → −27%, Sharpe 1.04 → 1.09. Caught the 2021–23 leader crash while SPY rose |
| 3 | **Don't open new positions when the index is stretched** (SPY 6–10%+ above its 50 SMA, QQQ 10%+) | Predicts weak returns | SPY 6–10% above 50 SMA: −27% annualized afterwards; QQQ >10%: −54% |

Market signals mainly predict **volatility** (about 2x higher in risk-off), not
returns. Their job is keeping you out of crashes.

## Layer 2: What to trade (stock selection)

| # | Rule | Effect | Evidence |
| --- | --- | --- | --- |
| 4 | **Leader scan:** price $10+, 2M+ shares/day, **$200M+** dollar volume ($500–600M+ for options/intraday), ADR 5–8% | Tradable, fast names. Not an edge by itself | Holding every passer lost 95%+ |
| 5 | **RS rating 90+** (vs whole market, IBD-style) | Predicts returns: the core edge | RS 90+: +3.5% vs SPY per 20 days; RS 50–89 ≈ 0 |
| 6 | **Above 50 SMA, ideally all MAs stacked** (10e > 20e > 50 > 100 > 200) | Predicts returns, fewer blow-ups | Stacked +3.5% vs +2.1% unstacked per 20 days |
| 7 | **Avoid names > 5% below the 20 EMA.** Extension above the MAs is fine for leaders | Predicts returns | > 5% under 20 EMA: −1.7% vs SPY; 20–35% above 50 SMA kept outperforming |

## Layer 3: When to get out (exits)

| # | Rule | Effect | Evidence |
| --- | --- | --- | --- |
| 8 | **Sell after 3 closes in a row below the 50 SMA** | Improves returns by avoiding shakeouts | ~+1–1.5%/yr vs first close below; beat 10 EMA exits, ≈ 20 EMA |
| 9 | **Rotate** freed capital into the next-strongest RS name | Keeps money in leaders | Part of the combined result |

## Combined system (top 10 names, 2019–2026)

| | Yearly return | Worst drop | Sharpe |
| --- | --- | --- | --- |
| QQQ buy & hold | 21% | −35% | 0.90 |
| Rules above | ~28–38% | ~−27 to −32% | ~1.1–1.3 |

These are likely **overstated**: Yahoo has no delisted stocks, and fills are assumed
at the close. Read them as "the rules have an edge," not a forecast.

## Tested and dropped

- Selling losers when the market turns off (pausing buys was better)
- SPY/QQQ "3 closes under the 50-day" gate (~6 false alarms a year)
- VIX, credit spreads, XLY/XLP, distribution days (worked in 2008, failed after 2019)
- Weekly MACD as a hard filter for leader stocks (too slow for high-ADR names)

## Still to add

- Entry triggers (breakouts, volume, pullbacks, opening-range breaks for intraday)
- Trade management: stop placement (e.g. ADR-based), partial profits, position sizing
- Paper-trade 1–3 months and compare to the backtest before risking money
