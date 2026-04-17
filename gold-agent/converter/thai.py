"""
converter/thai.py
Converts XAUUSD (gold price per troy oz in USD) to Thai Baht denominations.

Thai gold standard:
  - 1 troy oz        = 31.1035 grams
  - 1 baht-weight    = 15.244 grams
  - Thai gold purity = 96.5%  (standard for Thai gold shops)

Exchange rate:
  - Fetched live from open.er-api.com (free, no API key required)
  - Falls back to USD_THB_RATE in .env if the live fetch fails
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

TROY_OZ_TO_GRAMS      = 31.1035
GRAMS_PER_BAHT_WEIGHT = 15.244
THAI_GOLD_PURITY      = 0.965
DEFAULT_USD_THB_RATE  = 34.5


def fetch_live_usd_thb_rate() -> float:
    """
    Fetch the live USD/THB exchange rate from open.er-api.com.

    Free API — no key required. Falls back to USD_THB_RATE in .env
    if the request fails or times out.

    Returns:
        float: Current USD to THB rate.
    """
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") == "success":
            rate = float(data["rates"]["THB"])
            print(f"[thai.py] Live USD/THB rate fetched: {rate:.4f}")
            return rate
        raise ValueError("API returned non-success result")

    except Exception as e:
        print(f"[thai.py] Live rate fetch failed ({e}). Falling back to .env value.")
        return get_env_usd_thb_rate()


def get_env_usd_thb_rate() -> float:
    """
    Read the USD/THB rate from the .env file (USD_THB_RATE).

    Falls back to DEFAULT_USD_THB_RATE (34.5) if not set or invalid.

    Returns:
        float: USD to THB exchange rate.
    """
    try:
        rate = float(os.getenv("USD_THB_RATE", str(DEFAULT_USD_THB_RATE)))
        return rate if rate > 0 else DEFAULT_USD_THB_RATE
    except (ValueError, TypeError):
        return DEFAULT_USD_THB_RATE


def convert_to_thb(usd_price: float, usd_thb_rate: float = None) -> dict:
    """
    Convert gold price from USD per troy oz to various Thai Baht units.

    Applies 96.5% purity for the Thai gold shop price.

    Calculation chain:
        thb_per_oz               = usd_price × rate
        thb_per_gram             = thb_per_oz / 31.1035
        thb_per_baht_weight      = thb_per_gram × 15.244          (100% pure)
        thb_per_baht_weight_thai = thb_per_gram × 15.244 × 0.965  (Thai 96.5%)

    Args:
        usd_price (float): Gold price in USD per troy ounce.
        usd_thb_rate (float, optional): Exchange rate override.
                                        If None, fetches live rate automatically.

    Returns:
        dict: {
            'usd_per_oz'               : float,
            'usd_thb_rate'             : float,
            'rate_source'              : str,   # 'live' or 'env'
            'thb_per_oz'               : float,
            'thb_per_gram'             : float,
            'thb_per_baht_weight'      : float,
            'thb_per_baht_weight_thai' : float,  # ← Thai gold shop price
            'purity'                   : float,
        }
    """
    default = {
        "usd_per_oz": 0.0, "usd_thb_rate": 0.0, "rate_source": "none",
        "thb_per_oz": 0.0, "thb_per_gram": 0.0,
        "thb_per_baht_weight": 0.0, "thb_per_baht_weight_thai": 0.0,
        "purity": THAI_GOLD_PURITY,
    }

    try:
        if usd_price <= 0:
            return default

        if usd_thb_rate is not None:
            rate   = usd_thb_rate
            source = "manual"
        else:
            rate   = fetch_live_usd_thb_rate()
            source = "live"

        thb_per_oz               = usd_price * rate
        thb_per_gram             = thb_per_oz / TROY_OZ_TO_GRAMS
        thb_per_baht_weight      = thb_per_gram * GRAMS_PER_BAHT_WEIGHT
        thb_per_baht_weight_thai = thb_per_baht_weight * THAI_GOLD_PURITY

        print(
            f"[thai.py] ${usd_price:.2f}/oz -> "
            f"{thb_per_gram:.2f} THB/g -> "
            f"{thb_per_baht_weight_thai:.2f} THB/bw (96.5%)  [rate={rate:.4f} {source}]"
        )

        return {
            "usd_per_oz"               : round(usd_price, 2),
            "usd_thb_rate"             : round(rate, 4),
            "rate_source"              : source,
            "thb_per_oz"               : round(thb_per_oz, 2),
            "thb_per_gram"             : round(thb_per_gram, 2),
            "thb_per_baht_weight"      : round(thb_per_baht_weight, 2),
            "thb_per_baht_weight_thai" : round(thb_per_baht_weight_thai, 2),
            "purity"                   : THAI_GOLD_PURITY,
        }

    except Exception as e:
        print(f"[thai.py] Conversion error: {e}")
        return default


# Allow standalone testing
if __name__ == "__main__":
    result = convert_to_thb(2350.0)
    print("\n--- Gold Price Conversion ---")
    print(f"USD per troy oz              : ${result['usd_per_oz']:,.2f}")
    print(f"USD/THB rate ({result['rate_source']:6})      : {result['usd_thb_rate']}")
    print(f"THB per gram (100%)          : {result['thb_per_gram']:,.2f}")
    print(f"THB per baht-weight (96.5%)  : {result['thb_per_baht_weight_thai']:,.2f}")
