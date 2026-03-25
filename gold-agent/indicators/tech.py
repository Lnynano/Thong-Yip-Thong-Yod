"""
indicators/tech.py
Technical indicator calculations: RSI (14-period) and MACD (12, 26, 9).
All functions accept a pandas DataFrame with a 'Close' column.
"""

import pandas as pd
import numpy as np


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate the Relative Strength Index (RSI) using Wilder's smoothing method.

    RSI measures the speed and change of price movements on a 0-100 scale.
    - RSI > 70: Overbought (potential sell signal)
    - RSI < 30: Oversold (potential buy signal)

    Args:
        df (pd.DataFrame): DataFrame with at least a 'Close' column.
        period (int): Lookback period. Default is 14.

    Returns:
        float: The most recent RSI value (0–100). Returns 50.0 on failure.
    """
    try:
        if df.empty or "Close" not in df.columns:
            print("[tech.py] RSI: Empty DataFrame or missing 'Close' column.")
            return 50.0

        close = df["Close"].copy()
        delta = close.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        # Wilder's smoothed moving average (EWM with alpha = 1/period)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        rsi_value = float(rsi.iloc[-1])
        print(f"[tech.py] RSI({period}): {rsi_value:.2f}")
        return round(rsi_value, 2)

    except Exception as e:
        print(f"[tech.py] Error calculating RSI: {e}")
        return 50.0


def calculate_macd(df: pd.DataFrame,
                   fast: int = 12,
                   slow: int = 26,
                   signal: int = 9) -> dict:
    """
    Calculate the MACD (Moving Average Convergence Divergence) indicator.

    MACD = EMA(fast) - EMA(slow)
    Signal = EMA(MACD, signal)
    Histogram = MACD - Signal

    Interpretation:
    - MACD crossing above Signal: bullish signal
    - MACD crossing below Signal: bearish signal
    - Positive histogram: bullish momentum
    - Negative histogram: bearish momentum

    Args:
        df (pd.DataFrame): DataFrame with at least a 'Close' column.
        fast (int): Fast EMA period. Default is 12.
        slow (int): Slow EMA period. Default is 26.
        signal (int): Signal line EMA period. Default is 9.

    Returns:
        dict: {
            'macd': float,       # MACD line value
            'signal': float,     # Signal line value
            'histogram': float   # Difference (MACD - Signal)
        }
        Returns zeros on failure.
    """
    default = {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    try:
        if df.empty or "Close" not in df.columns:
            print("[tech.py] MACD: Empty DataFrame or missing 'Close' column.")
            return default

        close = df["Close"].copy()

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


def get_signal_summary(df: pd.DataFrame) -> dict:
    """
    Compute both RSI and MACD and return a combined summary dict.

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column.

    Returns:
        dict: Combined RSI and MACD values with interpretation strings.
    """
    rsi = calculate_rsi(df)
    macd = calculate_macd(df)

    # Simple interpretation
    if rsi > 70:
        rsi_signal = "OVERBOUGHT"
    elif rsi < 30:
        rsi_signal = "OVERSOLD"
    else:
        rsi_signal = "NEUTRAL"

    macd_signal = "BULLISH" if macd["histogram"] > 0 else "BEARISH"

    return {
        "rsi": rsi,
        "rsi_signal": rsi_signal,
        "macd": macd["macd"],
        "macd_signal_line": macd["signal"],
        "macd_histogram": macd["histogram"],
        "macd_signal": macd_signal,
    }


# Allow standalone testing
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data.fetch import get_gold_price

    df = get_gold_price()
    if not df.empty:
        print("\nRSI:", calculate_rsi(df))
        print("MACD:", calculate_macd(df))
        print("Summary:", get_signal_summary(df))
