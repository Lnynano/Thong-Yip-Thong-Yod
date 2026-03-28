import yfinance as yf
import requests


# =========================
# USD/THB rate
# =========================

usd_thb_cache = 34.0


def get_usd_thb():

    global usd_thb_cache

    url = "https://api.coingecko.com/api/v3/simple/price"

    params = {
        "ids": "tether",
        "vs_currencies": "thb"
    }

    try:

        r = requests.get(
            url,
            params=params,
            timeout=5
        )

        data = r.json()

        if "tether" in data:

            usd_thb_cache = data["tether"]["thb"]

    except:

        print("⚠️ Using cached USD/THB")

    return usd_thb_cache


# =========================
# Fetch price
# =========================

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

    def get_value(col):

        value = latest[col]

        if hasattr(value, "iloc"):

            return float(value.iloc[0])

        return float(value)

    usd_close = get_value("Close")

    usd_thb = get_usd_thb()

    # ⭐ Convert to Thai Baht

    thai_close = (
        usd_close * 0.4729
    ) * usd_thb

    print(
        "USD:",
        usd_close,
        "| THB:",
        thai_close
    )

    price_data = {

        "time": latest.name,

        "open": get_value("Open"),

        "high": get_value("High"),

        "low": get_value("Low"),

        "close": round(
            thai_close,
            2
        ),

        "volume": get_value("Volume")

    }

    return price_data


if __name__ == "__main__":

    price = fetch_gold_price()

    print("\nLatest Thai Gold Price:")

    print(price)