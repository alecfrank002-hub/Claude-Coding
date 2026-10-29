# Findings

Generated from the backtest outputs. Expectancy is per trade in R (1R = the dollars risked on that trade). Universe is today's index members, so results are flattered by survivorship bias, more so the further back you go.

## Best and worst versions (all years, by expectancy in R)
- **B · 1.5x ATR(14) · 24% target**: +0.39R per trade ($318), win rate 20.9%, 11,960 trades, avg hold 35 days; 2023-24 +0.53R, 2025-26 +0.09R.
- **B · 8% · 24% target**: +0.39R per trade ($390), win rate 36.6%, 8,755 trades, avg hold 70 days; 2023-24 +0.52R, 2025-26 +0.23R.
- **A · 8% · 24% target**: +0.39R per trade ($386), win rate 36.6%, 9,833 trades, avg hold 69 days; 2023-24 +0.48R, 2025-26 +0.20R.
- …
- **A · None (20-day time exit) · Close < 20 EMA**: +0.02R per trade ($22), win rate 35.4%, 23,244 trades, avg hold 7 days; 2023-24 +0.04R, 2025-26 -0.00R.
- **A · Signal-day low · Close < 20 EMA**: -0.01R per trade ($46), win rate 28.9%, 24,775 trades, avg hold 7 days; 2023-24 +0.10R, 2025-26 -0.07R.

- 19 of 20 versions are positive over all years; 17 are positive in all three columns.
- 20 of 20 versions earned less per trade in 2025-26 than in 2023-24.

## Return per unit of time (R per 20 trading days held)
Target versions earn more R per trade but hold far longer, so compare them per day of capital tied up:
- A · Signal-day low · 24% target: +0.253R per 20 days held (+0.31R per trade over 24 days)
- B · Signal-day low · 24% target: +0.238R per 20 days held (+0.36R per trade over 30 days)
- B · 1.5x ATR(14) · 24% target: +0.221R per 20 days held (+0.39R per trade over 35 days)
- In the 24%-target versions, 8% of trades were held more than 120 trading days (longest 968). 1560 are still open and marked to the last close, most from 2025-26, so recent target results are less settled.

## Consistency of the top version
- B · 1.5x ATR(14) · 24% target: positive in 10 of 12 calendar years (worst -0.40R in 2015, best +1.30R in 2016).

## Market regime (SPY vs its 50-day SMA on the signal date)
- Signals taken while **SPY was below its 50-day did better in 19 of 20 versions** (top version: +0.48R below vs +0.35R above).
- Across all signals: +24% within 60 days 13.8% with SPY below vs 10.7% above; a drop of more than 8% 48% vs 44%. A stock reclaiming its 50-day while the market is weak tends to bounce harder.
- 28% of all signals fired with SPY below its 50-day.

## RS proxy (12-month return percentile vs the universe): data only, not a filter
- The relationship is U-shaped, not "higher is better". +24% within 60 days by RS quintile: 0-20 18%, 20-40 10%, 40-60 8%, 60-80 8%, 80-100 17%; drop of more than 8%: 0-20 52%, 20-40 42%, 40-60 39%, 60-80 41%, 80-100 50%.
- Both extremes move more in both directions, so in large caps this RS proxy mostly measures volatility. Test it as a filter only together with a volatility control.
- Top version by RS quintile: RS 0-20 +0.31R, RS 20-40 +0.52R, RS 40-60 +0.65R, RS 60-80 +0.40R, RS 80-100 +0.39R.

## Drawdown after entry, all signals (Entry A, next 60 trading days)
- All years: 50.5% of signals fell more than 7% (only 5.3% of those reached +24% afterwards); 45.2% fell more than 8% (4.8% reached +24% afterwards). Base rate of reaching +24% within 60 days: 11.5%.
- 2023-2024: 49.4% of signals fell more than 7% (only 4.5% of those reached +24% afterwards); 44.7% fell more than 8% (4.2% reached +24% afterwards). Base rate of reaching +24% within 60 days: 11.8%.
- 2025-2026: 55.9% of signals fell more than 7% (only 6.7% of those reached +24% afterwards); 50.3% fell more than 8% (6.1% reached +24% afterwards). Base rate of reaching +24% within 60 days: 14.4%.
- A setup that has already fallen 7-8% rarely recovers to the target, which supports using a hard stop in that range.

## Entries and exits
- Entry B never filled on 20% of eligible signals (price never cleared the signal-day high within 3 days).
- Those unfilled signals were weaker: 56% fell more than 8% within 60 days (vs 43% for the rest) and 8.9% reached +24% (vs 12.0%). The buy stop screens out some losers.
- Close-below-20-EMA versions: 34% of trades were out within 2 days, because right after a 50-day undercut the 20 EMA usually sits overhead. That exit cuts most trades before they can work; the 24% target versions earn far more per trade.
- Signal-day-low stops are tight (median 2.3% below entry) and sometimes almost zero: 2.8% of those trades had a stop less than 0.5% away (e.g. Entry A opening a cent above the signal low). Then a normal small loss is a huge R (worst -299R on a $25 loss), so **R averages for signal-day-low versions are distorted; compare them in dollars**, or add a minimum stop distance. 5% of these trades gapped through the stop.
- 2025-26 results include 2,440 trades still open (marked to the last close) and trades from the last few months that haven't had time to reach a +24% target, so 2025-26 is partly unfinished, especially for the target versions.
