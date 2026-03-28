import yfinance as yf
import ta
import pandas as pd
import random


def fetch_price_dataframe():

    symbol = "GC=F"

    data = yf.download(
        symbol,
        period="5d",
        interval="5m",
        progress=False
    )

    if data.empty:
        print("No price data")
        return None

    return data


def compute_indicators():
    # 1️⃣ FIRST: Fetch the data to create 'df'
    df = fetch_price_dataframe()

    if df is None or len(df) < 2:
        return None

    # 2️⃣ SECOND: Clean the data
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.droplevel(1)

    # 3️⃣ THIRD: Calculate indicators
    rsi_indicator = ta.momentum.RSIIndicator(close=df["Close"], window=14)
    df["RSI"] = rsi_indicator.rsi()

    macd_indicator = ta.trend.MACD(close=df["Close"])
    df["MACD"] = macd_indicator.macd()
    df["MACD_SIGNAL"] = macd_indicator.macd_signal()

    # 4️⃣ FOURTH: Now that indicators are calculated, grab the last row
    latest = df.iloc[-1]

    # 5️⃣ FIFTH: Conversion Logic
    usd_price = float(latest["Close"])
    usd_thb = 34.0  # More realistic exchange rate

    # 🧪 WEEKEND JITTER (Simulates price movement)
    test_jitter = random.uniform(-50, 50)
    thai_baht_price = ((usd_price * 0.4729) * usd_thb) + test_jitter

    # 6️⃣ FINALLY: Return the dictionary
    indicators = {
        "price": round(thai_baht_price, 2),  # Use 2 decimals to see jitter
        "usd_spot": round(usd_price, 2),
        "rsi": float(latest["RSI"]) if not pd.isna(latest["RSI"]) else 50.0,
        "macd": float(latest["MACD"]) if not pd.isna(latest["MACD"]) else 0.0,
        "macd_signal": float(latest["MACD_SIGNAL"]) if not pd.isna(latest["MACD_SIGNAL"]) else 0.0
    }

    return indicators


if __name__ == "__main__":

    result = compute_indicators()

    print("\nLatest Indicators:\n")

    print(result)
