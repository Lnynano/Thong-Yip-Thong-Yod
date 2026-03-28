# data/historical_price_loader.py

import yfinance as yf
import random


def load_random_day_prices():

    symbol = "GC=F"

    print("Loading historical prices...")

    # ดึง 7 วันย้อนหลัง

    data = yf.download(
        symbol,
        period="7d",
        interval="30s",
        progress=False
    )

    if data.empty:

        print("No historical data")

        return []

    prices = data["Close"].tolist()

    # เลือกช่วงสุ่ม 2880 จุด (1 วัน)

    if len(prices) >= 2880:

        start = random.randint(
            0,
            len(prices) - 2880
        )

        day_prices = prices[
            start:start + 2880
        ]

        print("Random day selected")

        return day_prices

    return prices