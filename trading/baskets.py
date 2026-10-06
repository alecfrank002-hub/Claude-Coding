"""Groups of tickers to run rotation strategies on.

Watch out for survivorship bias: a list of stocks picked today is full of
companies we already know did well. The sector ETFs don't have that problem
(they've existed since 1998), so trust their results most. The stock baskets
include some long-term laggards (GE, INTC, C, IBM, T...) to soften the bias, and
every result is also compared with simply holding the same basket.
"""

BASKETS = {
    # The nine original S&P 500 sector SPDRs, all trading since Dec 1998.
    "sectors": {
        "start": "2000-01-01",
        "tickers": ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"],
    },
    # 40 large US companies across sectors that were already big by the mid-2000s.
    "large_caps": {
        "start": "2005-01-01",
        "tickers": [
            "AAPL", "MSFT", "AMZN", "GOOGL", "INTC", "CSCO", "IBM", "ORCL", "QCOM", "TXN",
            "JPM", "BAC", "C", "WFC", "GS", "XOM", "CVX", "COP", "JNJ", "PFE",
            "MRK", "ABT", "AMGN", "UNH", "PG", "KO", "PEP", "WMT", "COST", "HD",
            "LOW", "MCD", "NKE", "DIS", "GE", "BA", "CAT", "MMM", "HON", "T",
        ],
    },
    # 25 Nasdaq growth names that were listed by 2011 (heavy survivorship bias).
    "nasdaq_growth": {
        "start": "2011-01-01",
        "tickers": [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "ADBE", "CSCO", "INTC", "QCOM", "TXN",
            "AVGO", "NFLX", "COST", "AMGN", "GILD", "SBUX", "ISRG", "INTU", "AMAT", "MU",
            "BKNG", "ADP", "CMCSA", "TSLA", "REGN",
        ],
    },
    # ~110 large US stocks (roughly today's S&P 100 plus large semis and software),
    # used to rank RS ratings and measure breadth. Picked today, so biased toward
    # winners; names enter the backtest once they have a year of history.
    "broad": {
        "start": "2005-01-01",
        "tickers": [
            "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
            "AVGO", "AXP", "BA", "BAC", "BKNG", "BLK", "BMY", "BRK-B", "C",
            "CAT", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS", "CVX",
            "DE", "DHR", "DIS", "DUK", "EMR", "F", "FDX", "GD", "GE", "GILD",
            "GM", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU", "ISRG", "JNJ",
            "JPM", "KO", "LIN", "LLY", "LMT", "LOW", "MA", "MCD", "MDLZ", "MDT",
            "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT", "NEE", "NFLX", "NKE",
            "NOW", "NVDA", "ORCL", "PEP", "PFE", "PG", "PM", "PYPL", "QCOM", "RTX",
            "SBUX", "SCHW", "SO", "SPG", "T", "TGT", "TMO", "TMUS", "TSLA", "TXN",
            "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT", "XOM", "MU",
            "AMAT", "LRCX", "KLAC", "ADI", "SNPS", "CDNS", "REGN", "VRTX", "PANW", "ANET",
        ],
    },
}
