import yfinance as yf
import ta
import requests
import pandas as pd

from core.mode_controller import get_mode
from data.price_memory import get_price_history


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

        print("⚠ Using cached USD/THB")

    return usd_thb_cache


# =========================
# REAL MODE → Yahoo fetch
# =========================

def fetch_real_dataframe():

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

    if hasattr(data.columns, "levels"):

        data.columns = data.columns.droplevel(1)

    return data


# =========================
# TEST MODE → memory fetch
# =========================

def fetch_memory_dataframe():

    prices = get_price_history()

    if len(prices) < 20:

        return None

    df = pd.DataFrame({

        "Close": prices

    })

    return df


# =========================
# Compute Indicators
# =========================

def compute_indicators():

    mode = get_mode()

    # =========================
    # SELECT DATA SOURCE
    # =========================

    if mode == "TEST":

        df = fetch_memory_dataframe()

        if df is None:

            print("Waiting memory...")

            return {

                "price": None,
                "rsi": 50,
                "macd": 0,
                "macd_signal": 0

            }

    else:

        df = fetch_real_dataframe()

        if df is None:

            return None

    # =========================
    # USD → THB convert
    # =========================

    usd_thb = get_usd_thb()

    df["THAI_PRICE"] = (

        df["Close"]
        * 0.4729
        * usd_thb

    )

    # =========================
    # RSI
    # =========================

    rsi_indicator = ta.momentum.RSIIndicator(

        close=df["THAI_PRICE"],
        window=14

    )

    df["RSI"] = rsi_indicator.rsi()

    # =========================
    # MACD
    # =========================

    macd_indicator = ta.trend.MACD(

        close=df["THAI_PRICE"]

    )

    df["MACD"] = macd_indicator.macd()

    df["MACD_SIGNAL"] = (

        macd_indicator.macd_signal()

    )

    latest = df.iloc[-1]

    thai_price = float(

        latest["THAI_PRICE"]

    )

    print(

        "Mode:",
        mode

    )

    print(

        "USD Gold:",
        float(latest["Close"])

    )

    print(

        "USD/THB:",
        usd_thb

    )

    print(

        "Thai Price:",
        thai_price

    )

    indicators = {

        "price": round(
            thai_price,
            2
        ),

        "rsi": float(
            latest["RSI"]
        ),

        "macd": float(
            latest["MACD"]
        ),

        "macd_signal": float(
            latest["MACD_SIGNAL"]
        )

    }

    return indicators


# =========================
# TEST RUN
# =========================

if __name__ == "__main__":

    result = compute_indicators()

    print("\nLatest Indicators:\n")

    print(result)