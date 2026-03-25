import yfinance as yf
import ta


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

    df = fetch_price_dataframe()

    if df is None:
        return None

    # FIX MultiIndex
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.droplevel(1)

    # RSI
    rsi_indicator = ta.momentum.RSIIndicator(
        close=df["Close"],
        window=14
    )

    df["RSI"] = rsi_indicator.rsi()

    # MACD
    macd_indicator = ta.trend.MACD(
        close=df["Close"]
    )

    df["MACD"] = macd_indicator.macd()
    df["MACD_SIGNAL"] = macd_indicator.macd_signal()

    # เอาแถวล่าสุด
    latest = df.iloc[-1]

    indicators = {
        "price": float(latest["Close"]),
        "rsi": float(latest["RSI"]),
        "macd": float(latest["MACD"]),
        "macd_signal": float(latest["MACD_SIGNAL"])
    }

    return indicators


if __name__ == "__main__":

    result = compute_indicators()

    print("\nLatest Indicators:\n")

    print(result)