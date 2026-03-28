# import yfinance as yf


# def fetch_gold_price():

#     symbol = "GC=F"

#     data = yf.download(
#         symbol,
#         period="1d",
#         interval="1m",
#         progress=False
#     )

#     if data.empty:
#         print("No data fetched")
#         return None

#     latest = data.iloc[-1]

#     # FIX สำหรับ MultiIndex
#     def get_value(col):
#         value = latest[col]
#         if hasattr(value, "iloc"):
#             return float(value.iloc[0])
#         return float(value)

#     price_data = {
#         "time": latest.name,
#         "open": get_value("Open"),
#         "high": get_value("High"),
#         "low": get_value("Low"),
#         "close": get_value("Close"),
#         "volume": get_value("Volume")
#     }

#     return price_data


# if __name__ == "__main__":

#     price = fetch_gold_price()

#     print("Latest Gold Price:")
#     print(price)

import requests


def fetch_thai_gold_price():
    # 1. Fetch PAXG (Gold Proxy) and USD/THB exchange rate
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        'ids': 'pax-gold,tether-fiat-thai-baht',  # PAXG = 1 oz Gold, THB = Currency
        'vs_currencies': 'usd,thb'
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        # Global Price per 1 Troy Ounce (USD)
        gold_usd = data['pax-gold']['usd']
        # Exchange Rate (USD/THB)
        usd_thb = data['tether-fiat-thai-baht']['thb']

        # 2. Conversion to Thai Gold Unit (1 Baht Weight = 15.244g at 96.5%)
        # Formula: (Global Gold USD * 0.4729) * USD/THB
        # 0.4729 is the constant to convert 1 Troy Oz (99.9%) to 1 Thai Baht (96.5%)
        thai_gold_price = (gold_usd * 0.4729) * usd_thb

        return {
            "global_spot_usd": gold_usd,
            "usd_thb": usd_thb,
            "thai_gold_baht": round(thai_gold_price, -1)  # Round to nearest 10
        }

    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    result = fetch_thai_gold_price()
    if result:
        print(f"Global Gold: ${result['global_spot_usd']}")
        print(f"Exchange Rate: {result['usd_thb']} THB/$")
        print(f"Estimated Thai Gold Price: ฿{result['thai_gold_baht']:,}")
