"""
data/fetch.py
Fetches live XAUUSD (Gold) price data using yfinance.
Returns the last 90 days of OHLCV as a pandas DataFrame.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# Stores the last successful fetch time for display in the UI
_last_fetched_at: str = "Never"


def get_gold_price() -> pd.DataFrame:
    """
    Fetch the last 90 days of XAUUSD (Gold Futures) OHLCV data.

    Uses yfinance with ticker symbol 'GC=F' (COMEX Gold Futures).
    Stores a human-readable fetch timestamp accessible via get_fetch_time().

    Returns:
        pd.DataFrame: DataFrame with columns [Open, High, Low, Close, Volume]
                      indexed by Date. Returns empty DataFrame on failure.
    """
    global _last_fetched_at

    try:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=90)

        ticker = yf.Ticker("GC=F")
        df = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d",
        )

        if df.empty:
            print("[fetch.py] Warning: No data returned from yfinance.")
            return pd.DataFrame()

        # Keep only standard OHLCV columns
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index.name = "Date"
        df.dropna(inplace=True)

        # Record timestamp of this successful fetch
        _last_fetched_at = datetime.now().strftime("%H:%M:%S")

        print(f"[fetch.py] Fetched {len(df)} rows. "
              f"Latest close: {df['Close'].iloc[-1]:.2f} USD  (at {_last_fetched_at})")
        return df

    except Exception as e:
        print(f"[fetch.py] Error fetching gold price: {e}")
        return pd.DataFrame()


def get_latest_price() -> float:
    """
    Get just the most recent gold closing price.

    Returns:
        float: Latest gold price in USD per troy oz. Returns 0.0 on failure.
    """
    try:
        df = get_gold_price()
        return float(df["Close"].iloc[-1]) if not df.empty else 0.0
    except Exception as e:
        print(f"[fetch.py] Error getting latest price: {e}")
        return 0.0


def get_fetch_time() -> str:
    """
    Return the timestamp of the last successful data fetch.

    Returns:
        str: Time string like "14:32:05", or "Never" if not yet fetched.
    """
    return _last_fetched_at


# Allow standalone testing
if __name__ == "__main__":
    df = get_gold_price()
    print(df.tail())
    print(f"\nLatest price : ${get_latest_price():.2f}")
    print(f"Fetched at   : {get_fetch_time()}")
