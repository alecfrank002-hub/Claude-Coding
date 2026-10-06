# Claude-Coding

Swing-trading research toolkit (Python, pandas). The user is a swing trader
refining their edge and teaching Claude their rules.

- **Read `RULEBOOK.md` and `STRATEGY.md` first.** RULEBOOK.md is the one-page summary of the rules. It holds the user's trading rules and the backtest
  findings so far; update it whenever a rule is added, changed or tested.
- Run tests with `python -m pytest`. Price data comes from Yahoo Finance via
  yfinance and is cached in `data/` (not committed).
- Research scripts: `research_environment.py` (market conditions),
  `research_stocks.py` (stock setups), `research_portfolio.py` (combined system),
  `rotation.py` and `compare_rules.py` (earlier studies).
- Backtests must avoid look-ahead: decisions at the close earn the next day's
  return. Compare stock-basket results against holding the same basket, since the
  baskets carry survivorship bias.
