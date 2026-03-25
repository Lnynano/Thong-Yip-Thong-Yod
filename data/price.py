import yfinance as yf


def fetch_gold_price():

    symbol = "GC=F"

    data = yf.download(
        symbol,
        period="1d",
        interval="1m",
        progress=False
    )

    if data.empty:
        print("No data fetched")
        return None

    latest = data.iloc[-1]

    # FIX สำหรับ MultiIndex
    def get_value(col):
        value = latest[col]
        if hasattr(value, "iloc"):
            return float(value.iloc[0])
        return float(value)

    price_data = {
        "time": latest.name,
        "open": get_value("Open"),
        "high": get_value("High"),
        "low": get_value("Low"),
        "close": get_value("Close"),
        "volume": get_value("Volume")
    }

    return price_data


if __name__ == "__main__":

    price = fetch_gold_price()

    print("Latest Gold Price:")
    print(price)