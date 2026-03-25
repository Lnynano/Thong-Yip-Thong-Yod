"""
data/fetch.py
Fetches live XAUUSD (Gold) price data using yfinance.
Returns the last 90 days of OHLCV as a pandas DataFrame.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def get_gold_price() -> pd.DataFrame:
    """
    Fetch the last 90 days of XAUUSD (Gold Futures) OHLCV data.

    Uses yfinance with ticker symbol 'GC=F' (COMEX Gold Futures).

    Returns:
        pd.DataFrame: DataFrame with columns [Open, High, Low, Close, Volume]
                      indexed by Date. Returns empty DataFrame on failure.
    """
    try:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=90)

        ticker = yf.Ticker("GC=F")
        df = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                            end=end_date.strftime("%Y-%m-%d"),
                            interval="1d")

        if df.empty:
            print("[fetch.py] Warning: No data returned from yfinance.")
            return pd.DataFrame()

        # Keep only standard OHLCV columns
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index.name = "Date"
        df.dropna(inplace=True)

        print(f"[fetch.py] Fetched {len(df)} rows. "
              f"Latest close: {df['Close'].iloc[-1]:.2f} USD")
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
        if df.empty:
            return 0.0
        return float(df["Close"].iloc[-1])
    except Exception as e:
        print(f"[fetch.py] Error getting latest price: {e}")
        return 0.0


# Allow standalone testing
if __name__ == "__main__":
    df = get_gold_price()
    print(df.tail())
    print(f"\nLatest price: ${get_latest_price():.2f}")
