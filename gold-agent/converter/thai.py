"""
converter/thai.py
Converts XAUUSD (gold price per troy oz in USD) to Thai Baht denominations.

Based on Slide 21 of the course:
  "In Thailand, Gold is priced in Baht per Baht-weight (15.244 grams)
   at 96.5% purity."

Conversions:
  - USD/troy oz  → THB/troy oz         (multiply by USD/THB rate)
  - THB/troy oz  → THB/gram            (1 troy oz = 31.1035 grams)
  - THB/gram     → THB/baht-weight     (1 baht-weight = 15.244 grams)
  - All Thai gold prices apply 96.5% purity factor (Slide 21)

Purity explanation:
  Thai gold (ทองคำไทย) sold in jewelry shops is 96.5% pure gold (not 99.9%).
  So the effective gold content per baht-weight = 15.244g × 0.965 = 14.71046g
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Conversion constants
TROY_OZ_TO_GRAMS = 31.1035          # 1 troy ounce = 31.1035 grams (international standard)
GRAMS_PER_BAHT_WEIGHT = 15.244      # 1 Thai baht-weight (บาท) = 15.244 grams
THAI_GOLD_PURITY = 0.965            # Thai gold is 96.5% pure (Slide 21)
DEFAULT_USD_THB_RATE = 34.5         # Fallback exchange rate


def get_usd_thb_rate() -> float:
    """
    Read the USD/THB exchange rate from environment variables.

    Falls back to DEFAULT_USD_THB_RATE (34.5) if not set.

    Returns:
        float: USD to THB exchange rate.
    """
    try:
        rate_str = os.getenv("USD_THB_RATE", str(DEFAULT_USD_THB_RATE))
        rate = float(rate_str)
        if rate <= 0:
            raise ValueError("Exchange rate must be positive.")
        return rate
    except (ValueError, TypeError) as e:
        print(f"[thai.py] Invalid USD_THB_RATE in .env: {e}. "
              f"Using default {DEFAULT_USD_THB_RATE}.")
        return DEFAULT_USD_THB_RATE


def convert_to_thb(usd_price: float, usd_thb_rate: float = None) -> dict:
    """
    Convert gold price from USD per troy oz to various Thai Baht units.

    Applies the 96.5% purity factor for Thai gold as specified in Slide 21:
    "In Thailand, Gold is priced in Baht per Baht-weight (15.244 grams)
     at 96.5% purity."

    Calculation chain:
        1. thb_per_oz      = usd_price × usd_thb_rate
        2. thb_per_gram    = thb_per_oz / 31.1035
        3. thb_per_bw_pure = thb_per_gram × 15.244        (100% pure, international)
        4. thb_per_bw_thai = thb_per_gram × 15.244 × 0.965 (96.5% Thai gold)

    Args:
        usd_price (float): Gold price in USD per troy ounce (e.g., 2350.00).
        usd_thb_rate (float, optional): USD to THB exchange rate.
                                        If None, reads from .env or uses default.

    Returns:
        dict: {
            'usd_per_oz'              : float,  # Input price
            'usd_thb_rate'            : float,  # Exchange rate used
            'thb_per_oz'              : float,  # THB per troy ounce
            'thb_per_gram'            : float,  # THB per gram (100% pure)
            'thb_per_baht_weight'     : float,  # THB per baht-weight (100% pure)
            'thb_per_baht_weight_thai': float,  # THB per baht-weight (96.5% Thai purity)
            'purity'                  : float,  # Purity factor (0.965)
        }
        Returns zeros on failure.
    """
    default = {
        "usd_per_oz": 0.0,
        "usd_thb_rate": 0.0,
        "thb_per_oz": 0.0,
        "thb_per_gram": 0.0,
        "thb_per_baht_weight": 0.0,
        "thb_per_baht_weight_thai": 0.0,
        "purity": THAI_GOLD_PURITY,
    }

    try:
        if usd_price <= 0:
            print("[thai.py] Invalid USD price (must be > 0).")
            return default

        # Use provided rate or read from env
        rate = usd_thb_rate if usd_thb_rate is not None else get_usd_thb_rate()

        # Step 1: USD/oz → THB/oz
        thb_per_oz = usd_price * rate

        # Step 2: THB/oz → THB/gram (1 troy oz = 31.1035g)
        thb_per_gram = thb_per_oz / TROY_OZ_TO_GRAMS

        # Step 3: THB/gram → THB/baht-weight (international 100% pure)
        thb_per_baht_weight = thb_per_gram * GRAMS_PER_BAHT_WEIGHT

        # Step 4: Apply 96.5% purity for Thai gold (Slide 21)
        thb_per_baht_weight_thai = thb_per_baht_weight * THAI_GOLD_PURITY

        result = {
            "usd_per_oz": round(usd_price, 2),
            "usd_thb_rate": round(rate, 4),
            "thb_per_oz": round(thb_per_oz, 2),
            "thb_per_gram": round(thb_per_gram, 2),
            "thb_per_baht_weight": round(thb_per_baht_weight, 2),
            "thb_per_baht_weight_thai": round(thb_per_baht_weight_thai, 2),
            "purity": THAI_GOLD_PURITY,
        }

        print(
            f"[thai.py] ${usd_price:.2f}/oz → "
            f"฿{result['thb_per_gram']:.2f}/g → "
            f"฿{result['thb_per_baht_weight']:.2f}/bw (pure) → "
            f"฿{result['thb_per_baht_weight_thai']:.2f}/bw (96.5% Thai)  "
            f"[rate: {rate}]"
        )
        return result

    except Exception as e:
        print(f"[thai.py] Error converting price: {e}")
        return default


def format_thb(amount: float) -> str:
    """
    Format a THB amount with Thai Baht symbol and thousands separators.

    Args:
        amount (float): Amount in Thai Baht.

    Returns:
        str: Formatted string like "฿32,450.50".
    """
    return f"฿{amount:,.2f}"


# ─────────────────────────────────────────────────────────────
# Standalone testing
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_price = 2350.0   # Example gold price in USD/oz
    result = convert_to_thb(test_price)

    print("\n--- Gold Price Conversion (Slide 21 formulas) ---")
    print(f"USD per troy oz           : ${result['usd_per_oz']:,.2f}")
    print(f"USD/THB rate              : {result['usd_thb_rate']}")
    print(f"THB per troy oz           : {format_thb(result['thb_per_oz'])}")
    print(f"THB per gram              : {format_thb(result['thb_per_gram'])}")
    print(f"THB per baht-wt (100%)    : {format_thb(result['thb_per_baht_weight'])}")
    print(f"THB per baht-wt (96.5%)   : {format_thb(result['thb_per_baht_weight_thai'])}  ← Thai gold shops")
    print(f"\nPurity factor             : {result['purity'] * 100:.1f}%  (Thai gold standard)")
    print(f"Effective gold per bw     : {GRAMS_PER_BAHT_WEIGHT * THAI_GOLD_PURITY:.5f} grams")
