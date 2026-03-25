"""
logger/trade_log.py
Records every analysis run to a CSV file for review and tracking.

Each row captures:
  - Timestamp
  - Decision (BUY / SELL / HOLD)
  - Confidence %
  - Gold price in USD and THB
  - RSI value and signal
  - MACD direction
  - Sharpe ratio
  - Claude's reasoning (first 120 chars)
"""

import os
import csv
import pandas as pd
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), "analysis_log.csv")

COLUMNS = [
    "Timestamp",
    "Decision",
    "Confidence %",
    "Price USD",
    "Price THB (baht-wt)",
    "RSI",
    "MACD",
    "Sharpe",
    "Reasoning",
]


def _ensure_file():
    """Create the CSV file with headers if it doesn't exist yet."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)


def log_analysis(
    decision: str,
    confidence: int,
    price_usd: str,
    price_thb: str,
    rsi: str,
    macd: str,
    sharpe: str,
    reasoning: str,
) -> None:
    """
    Append one analysis result as a new row in the log CSV.

    Args:
        decision    : "BUY", "SELL", or "HOLD"
        confidence  : integer 0–100
        price_usd   : formatted USD price string
        price_thb   : formatted THB price string
        rsi         : RSI display string
        macd        : MACD display string
        sharpe      : Sharpe ratio display string
        reasoning   : Claude's reasoning text (truncated to 120 chars)
    """
    try:
        _ensure_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        short_reasoning = reasoning.replace("\n", " ").strip()[:120]

        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                decision,
                f"{confidence}%",
                price_usd,
                price_thb,
                rsi,
                macd,
                sharpe,
                short_reasoning,
            ])

        print(f"[trade_log.py] Logged: {timestamp} | {decision} | {confidence}%")

    except Exception as e:
        print(f"[trade_log.py] Failed to write log: {e}")


def get_recent_logs(n: int = 50) -> pd.DataFrame:
    """
    Read the most recent N rows from the log CSV.

    Args:
        n (int): Number of most recent rows to return. Default 50.

    Returns:
        pd.DataFrame: Log entries, most recent first.
                      Returns empty DataFrame if log doesn't exist yet.
    """
    try:
        _ensure_file()
        df = pd.read_csv(LOG_FILE, encoding="utf-8")
        if df.empty:
            return df
        return df.tail(n).iloc[::-1].reset_index(drop=True)

    except Exception as e:
        print(f"[trade_log.py] Failed to read log: {e}")
        return pd.DataFrame(columns=COLUMNS)


def clear_log() -> str:
    """
    Delete all log entries (reset the CSV to headers only).

    Returns:
        str: Confirmation message.
    """
    try:
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
        print("[trade_log.py] Log cleared.")
        return "Log cleared."
    except Exception as e:
        return f"Failed to clear log: {e}"


def get_log_stats() -> dict:
    """
    Return basic stats from the full log history.

    Returns:
        dict: {
            'total'    : int,   # total entries
            'buy_count': int,
            'sell_count': int,
            'hold_count': int,
            'last_run' : str,   # timestamp of last entry
        }
    """
    try:
        _ensure_file()
        df = pd.read_csv(LOG_FILE, encoding="utf-8")
        if df.empty:
            return {"total": 0, "buy_count": 0, "sell_count": 0, "hold_count": 0, "last_run": "—"}

        counts = df["Decision"].value_counts()
        return {
            "total"     : len(df),
            "buy_count" : int(counts.get("BUY",  0)),
            "sell_count": int(counts.get("SELL", 0)),
            "hold_count": int(counts.get("HOLD", 0)),
            "last_run"  : df["Timestamp"].iloc[-1],
        }
    except Exception as e:
        print(f"[trade_log.py] Stats error: {e}")
        return {"total": 0, "buy_count": 0, "sell_count": 0, "hold_count": 0, "last_run": "—"}


# Allow standalone testing
if __name__ == "__main__":
    # Write a test entry
    log_analysis(
        decision="BUY", confidence=72,
        price_usd="$2,345.00", price_thb="฿39,200.00",
        rsi="38.5  —  Oversold 🟢", macd="Histogram: +0.12  —  ▲ Bullish",
        sharpe="0.85  (Acceptable)",
        reasoning="RSI is oversold and MACD histogram is positive. Fed rate cut news supports bullish momentum.",
    )

    df = get_recent_logs()
    print(df)
    print("\nStats:", get_log_stats())
