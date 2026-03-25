"""
logger/trade_log.py
Records every analysis run to a CSV file for the dashboard log table.
"""

import os
import csv
import pandas as pd
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "analysis_log.csv")

COLUMNS = ["Timestamp", "Decision", "Confidence %", "Price USD",
           "Price THB (baht-wt)", "RSI", "MACD", "Sharpe", "Reasoning"]


def log_analysis(decision: str, confidence: int, price_usd: str,
                 price_thb: str, rsi: str, macd: str,
                 sharpe: str, reasoning: str) -> None:
    """Append one analysis result row to the CSV log file."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        write_header = not os.path.exists(LOG_FILE)
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(COLUMNS)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                decision,
                confidence,
                price_usd,
                price_thb,
                rsi,
                macd,
                sharpe,
                reasoning[:80] + "..." if len(reasoning) > 80 else reasoning,
            ])
    except Exception as e:
        print(f"[trade_log.py] Failed to write log: {e}")


def get_recent_logs(n: int = 50) -> pd.DataFrame:
    """Return the last n rows from the CSV log as a DataFrame."""
    try:
        if not os.path.exists(LOG_FILE):
            return pd.DataFrame(columns=COLUMNS)
        df = pd.read_csv(LOG_FILE, encoding="utf-8")
        return df.tail(n).iloc[::-1].reset_index(drop=True)
    except Exception as e:
        print(f"[trade_log.py] Failed to read log: {e}")
        return pd.DataFrame(columns=COLUMNS)


def clear_log() -> None:
    """Delete the log CSV file."""
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
            print("[trade_log.py] Log cleared.")
    except Exception as e:
        print(f"[trade_log.py] Failed to clear log: {e}")
