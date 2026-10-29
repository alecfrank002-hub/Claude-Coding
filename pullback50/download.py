"""Download (or refresh) daily prices for the universe plus SPY.

    python -m pullback50.download            # only tickers not cached yet
    python -m pullback50.download --refresh  # re-download everything (e.g. to add recent days)
"""

import sys

from . import data

if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    u = data.universe(refresh=refresh)
    data.download(u["all"] + ["SPY"], refresh=refresh)
