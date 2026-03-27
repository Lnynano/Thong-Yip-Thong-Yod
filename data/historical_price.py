import yfinance as yf


def fetch_daily_market_data():

    symbol = "GC=F"

    data = yf.download(
        symbol,
        period="1d",
        interval="30m",
        progress=False
    )

    if data.empty:

        print("No historical data")

        return None

    # FIX MultiIndex
    if hasattr(data.columns, "levels"):

        data.columns = data.columns.droplevel(1)

    closes = data["Close"].tolist()

    return closes