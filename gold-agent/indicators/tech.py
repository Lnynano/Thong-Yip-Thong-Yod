"""
indicators/tech.py
Technical indicator calculations.

Implements the following formulas:
  - EMA:  EMAₜ = α·Pₜ + (1-α)·EMAₜ₋₁,  where α = 2/(N+1)
  - MACD: MACD = EMA₁₂ - EMA₂₆
  - RSI:  RSI  = 100 - 100 / (1 + RS),  RS = SMMA(Gains,n) / SMMA(Losses,n)

Additional indicator:
  - Bollinger Bands: middle ± 2 × std(close, period=20)
    (complements RSI and MACD — signals volatility squeezes)

Design principle:
  "Do not rely on LLMs for numerical calculations. Pre-compute all
   indicators deterministically and pass the results as state."
"""

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────────────────────
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate the Relative Strength Index (RSI) using Wilder's smoothing.

    Formula:
        RSI = 100 - 100 / (1 + RS)
        RS  = SMMA(Gains, n) / SMMA(Losses, n)

    Interpretation:
        RSI > 70: Overbought → potential SELL signal
        RSI < 30: Oversold   → potential BUY signal
        RSI 30–70: Neutral momentum

    Args:
        df (pd.DataFrame): DataFrame with at least a 'Close' column.
        period (int): Lookback period. Default is 14.

    Returns:
        float: The most recent RSI value (0–100). Returns 50.0 on failure.
    """
    try:
        if df.empty or "Close" not in df.columns:
            print("[tech.py] RSI: Empty DataFrame or missing 'Close' column.")
            return 50.0   # ✅ FIX: was 0.0

        if len(df) < period:
            print(f"[tech.py] RSI: Not enough data (<{period}).")
            return 50.0   # ✅ HARDEN: insufficient data


        close = df["Close"].copy()
        delta = close.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        # Wilder's SMMA: EWM with alpha = 1/period
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        rsi_value = float(rsi.iloc[-1])

        if np.isnan(rsi_value):
            print("[tech.py] RSI: NaN detected.")
            return 50.0   # ✅ HARDEN

        print(f"[tech.py] RSI({period}): {rsi_value:.2f}")
        return round(rsi_value, 2)

    except Exception as e:
        print(f"[tech.py] Error calculating RSI: {e}")
        return 50.0


# ─────────────────────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────────────────────
def calculate_macd(df: pd.DataFrame,
                   fast: int = 12,
                   slow: int = 26,
                   signal: int = 9) -> dict:
    """
    Calculate the MACD indicator.

    Formulas:
        EMAₜ   = α·Pₜ + (1-α)·EMAₜ₋₁    where α = 2/(N+1)
        MACD   = EMA₁₂  - EMA₂₆
        Signal = EMA(MACD, 9)
        Histogram = MACD - Signal

    Interpretation:
        MACD crossing above Signal: bullish (BUY signal)
        MACD crossing below Signal: bearish (SELL signal)
        Positive histogram: bullish momentum building
        Negative histogram: bearish momentum building

    Args:
        df (pd.DataFrame): DataFrame with at least a 'Close' column.
        fast (int): Fast EMA period (default 12).
        slow (int): Slow EMA period (default 26).
        signal (int): Signal line EMA period (default 9).

    Returns:
        dict: {
            'macd'     : float,  # MACD line value
            'signal'   : float,  # Signal line value
            'histogram': float   # Histogram (MACD - Signal)
        }
        Returns zeros on failure.
    """
    default = {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    try:
        if df.empty or "Close" not in df.columns:
            print("[tech.py] MACD: Empty DataFrame or missing 'Close' column.")
            return default

        close = df["Close"].copy()

        # EMA formula: α = 2/(N+1)
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        result = {
            "macd": round(float(macd_line.iloc[-1]), 4),
            "signal": round(float(signal_line.iloc[-1]), 4),
            "histogram": round(float(histogram.iloc[-1]), 4),
        }

        print(f"[tech.py] MACD({fast},{slow},{signal}): "
              f"MACD={result['macd']}, Signal={result['signal']}, "
              f"Histogram={result['histogram']}")
        return result

    except Exception as e:
        print(f"[tech.py] Error calculating MACD: {e}")
        return default


# ─────────────────────────────────────────────────────────────
# Bollinger Bands  (complements RSI/MACD)
# ─────────────────────────────────────────────────────────────
def calculate_bollinger_bands(df: pd.DataFrame,
                               period: int = 20,
                               num_std: float = 2.0) -> dict:
    """
    Calculate Bollinger Bands — a volatility indicator.

    Formula:
        Middle Band = SMA(Close, period=20)
        Upper Band  = Middle Band + 2 × std(Close, period=20)
        Lower Band  = Middle Band - 2 × std(Close, period=20)
        %B          = (Close - Lower) / (Upper - Lower)  [0=at lower, 1=at upper]
        Bandwidth   = (Upper - Lower) / Middle            [volatility measure]

    Interpretation:
        Price near Upper Band  → overbought (confirms RSI > 70)
        Price near Lower Band  → oversold   (confirms RSI < 30)
        Narrow bandwidth       → volatility squeeze → breakout incoming
        Wide bandwidth         → high volatility market

    This indicator complements RSI and MACD by adding a volatility dimension.
    Pre-compute all values, pass as structured state to LLM.

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.
        period (int): Rolling window period (default 20).
        num_std (float): Number of standard deviations (default 2.0).

    Returns:
        dict: {
            'upper'     : float,  # Upper band
            'middle'    : float,  # Middle band (SMA)
            'lower'     : float,  # Lower band
            'percent_b' : float,  # %B position (0–1)
            'bandwidth' : float,  # Band width as fraction of middle
            'signal'    : str,    # 'OVERBOUGHT', 'OVERSOLD', or 'NEUTRAL'
        }
        Returns zeros on failure.
    """
    default = {
        "upper": 0.0, "middle": 0.0, "lower": 0.0,
        "percent_b": 0.5, "bandwidth": 0.0, "signal": "NEUTRAL",
    }

    try:
        if df.empty or "Close" not in df.columns or len(df) < period:
            return default

        close = df["Close"].copy()

        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = middle + (num_std * std)
        lower = middle - (num_std * std)

        current_close = float(close.iloc[-1])
        upper_val = float(upper.iloc[-1])
        middle_val = float(middle.iloc[-1])
        lower_val = float(lower.iloc[-1])

        band_range = upper_val - lower_val
        percent_b = (current_close - lower_val) / band_range if band_range > 0 else 0.5
        bandwidth = band_range / middle_val if middle_val > 0 else 0.0

        # Signal based on %B position
        if percent_b >= 0.80:
            signal = "OVERBOUGHT"
        elif percent_b <= 0.20:
            signal = "OVERSOLD"
        else:
            signal = "NEUTRAL"

        result = {
            "upper": round(upper_val, 2),
            "middle": round(middle_val, 2),
            "lower": round(lower_val, 2),
            "percent_b": round(percent_b, 4),
            "bandwidth": round(bandwidth, 4),
            "signal": signal,
        }

        print(f"[tech.py] Bollinger({period},{num_std}): "
              f"Upper={result['upper']}, Mid={result['middle']}, "
              f"Lower={result['lower']}, %B={result['percent_b']:.2f} [{signal}]")
        return result

    except Exception as e:
        print(f"[tech.py] Error calculating Bollinger Bands: {e}")
        return default


# ─────────────────────────────────────────────────────────────
# Confluence Score  (0–10 scale for UI display)
# ─────────────────────────────────────────────────────────────
def calculate_confluence_score(df: pd.DataFrame, news_sentiment: str = "NEUTRAL") -> float:
    """
    Combine RSI, MACD, Bollinger Bands, and news sentiment into a single
    0–10 confluence score.

    Scoring:
      RSI < 30  (oversold)   : +2   |  RSI > 70 (overbought): -2
      RSI < 40               : +1   |  RSI > 60             : -1
      MACD histogram > 0     : +1.5 |  histogram < 0        : -1.5
      BB %B < 0.30           : +1.5 |  %B > 0.70            : -1.5
      News BULLISH           : +1.5 |  News BEARISH          : -1.5

    Raw range: [-6.5, +6.5]  → mapped linearly to [0, 10].

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column (≥30 rows).
        news_sentiment (str): "BULLISH", "BEARISH", or "NEUTRAL".

    Returns:
        float: Score from 0.0 (extremely bearish) to 10.0 (extremely bullish).
    """
    try:
        rsi  = calculate_rsi(df)
        macd = calculate_macd(df)
        bb   = calculate_bollinger_bands(df)

        raw = 0.0

        # RSI component
        if rsi < 30:
            raw += 2.0
        elif rsi < 40:
            raw += 1.0
        elif rsi > 70:
            raw -= 2.0
        elif rsi > 60:
            raw -= 1.0

        # MACD component
        if macd["histogram"] > 0:
            raw += 1.5
        else:
            raw -= 1.5

        # Bollinger Bands %B component
        if bb["percent_b"] < 0.20:
            raw += 1.5
        elif bb["percent_b"] > 0.80:
            raw -= 1.5

        # News sentiment component
        if news_sentiment == "BULLISH":
            raw += 1.5
        elif news_sentiment == "BEARISH":
            raw -= 1.5

        # Map [-6.5, +6.5] → [0, 10]
        score = (raw + 6.5) / 13.0 * 10.0
        score = max(0.0, min(10.0, score))
        return round(score, 1)

    except Exception as e:
        print(f"[tech.py] Error calculating confluence score: {e}")
        return 5.0


# ─────────────────────────────────────────────────────────────
# Market Regime Detection
# ─────────────────────────────────────────────────────────────
def calculate_market_regime(df: pd.DataFrame) -> str:
    """
    Classify the current market regime from price action.

    Rules (evaluated in order):
      1. VOLATILE    : BB bandwidth > 0.04  (high volatility — checked first)
      2. TRENDING UP : MACD histogram > 0 AND price > SMA20
      3. TRENDING DOWN: MACD histogram < 0 AND price < SMA20
      4. RANGING     : everything else

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column (≥20 rows).

    Returns:
        str: "TRENDING UP", "TRENDING DOWN", "RANGING", or "VOLATILE"
    """
    try:
        macd = calculate_macd(df)
        bb   = calculate_bollinger_bands(df)

        current_price = float(df["Close"].iloc[-1])
        sma20 = bb["middle"]

        bandwidth = bb["bandwidth"]

        if bandwidth > 0.04:
            return "VOLATILE"
        if macd["histogram"] > 0 and current_price > sma20:
            return "TRENDING UP"
        if macd["histogram"] < 0 and current_price < sma20:
            return "TRENDING DOWN"
        return "RANGING"

    except Exception as e:
        print(f"[tech.py] Error calculating market regime: {e}")
        return "RANGING"


# ─────────────────────────────────────────────────────────────
# Standalone testing
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data.fetch import get_gold_price

    df = get_gold_price()
    if not df.empty:
        print("\n--- Technical Indicators ---")
        print(f"RSI  : {calculate_rsi(df)}")
        print(f"MACD : {calculate_macd(df)}")
        print(f"BBands: {calculate_bollinger_bands(df)}")
