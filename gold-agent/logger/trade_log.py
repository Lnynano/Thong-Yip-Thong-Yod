"""
logger/trade_log.py
Records every analysis run for the dashboard log table.

Storage strategy (auto-detected):
  - MONGODB_URI set      →  MongoDB Atlas collection "trade_log" (persistent across deploys)
  - MONGODB_URI not set  →  local data/analysis_log.csv (dev fallback)
"""

import os
import csv
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Thai timezone UTC+7
_THAI_TZ = timezone(timedelta(hours=7))

load_dotenv()

LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "analysis_log.csv")

COLUMNS = ["Timestamp", "Decision", "Confidence %", "Price USD",
           "Price THB (baht-wt)", "RSI", "MACD", "Sharpe", "Reasoning"]

# ─────────────────────────────────────────────────────────────
# MongoDB client (lazy init — only when MONGODB_URI is set)
# ─────────────────────────────────────────────────────────────
_mongo_client = None
_mongo_db     = None


def _get_mongo_collection():
    """Return MongoDB trade_log collection, or None if MONGODB_URI is not set."""
    global _mongo_client, _mongo_db
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return None
    try:
        if _mongo_client is None:
            from pymongo import MongoClient
            _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            _mongo_db     = _mongo_client["gold_agent"]
            print("[trade_log.py] Connected to MongoDB Atlas.")
        return _mongo_db["trade_log"]
    except Exception as e:
        print(f"[trade_log.py] MongoDB connection failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────
def log_analysis(decision: str, confidence: int, price_usd: str,
                 price_thb: str, rsi: str, macd: str,
                 sharpe: str, reasoning: str) -> None:
    """Append one analysis result to MongoDB or CSV fallback."""
    timestamp = datetime.now(_THAI_TZ).strftime("%Y-%m-%d %H:%M")
    short_reason = reasoning[:500] + "..." if len(reasoning) > 500 else reasoning

    # ── MongoDB ──────────────────────────────────────────────
    col = _get_mongo_collection()
    if col is not None:
        try:
            col.insert_one({
                "Timestamp":           timestamp,
                "Decision":            decision,
                "Confidence %":        confidence,
                "Price USD":           price_usd,
                "Price THB (baht-wt)": price_thb,
                "RSI":                 rsi,
                "MACD":                macd,
                "Sharpe":              sharpe,
                "Reasoning":           short_reason,
            })
            return
        except Exception as e:
            print(f"[trade_log.py] MongoDB insert failed, using CSV: {e}")

    # ── CSV fallback ─────────────────────────────────────────
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        write_header = not os.path.exists(LOG_FILE)
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(COLUMNS)
            writer.writerow([
                timestamp, decision, confidence,
                price_usd, price_thb, rsi, macd, sharpe, short_reason,
            ])
    except Exception as e:
        print(f"[trade_log.py] CSV write failed: {e}")


# ─────────────────────────────────────────────────────────────
# Professor's Trade Log API (competition requirement)
# ─────────────────────────────────────────────────────────────
_TRADE_LOG_API_URL = "https://goldtrade-logs-api.poonnatuch.workers.dev/logs"


def send_trade_log(action: str, price_thb: float, reason: str,
                   confidence: int = 0) -> dict:
    """
    POST the agent decision to the professor's GoldTrade Logs API.

    Required by competition rules — every signal must be logged.
    Silent on failure (non-blocking).

    Args:
        action     : "BUY", "SELL", or "HOLD"
        price_thb  : current gold price (THB per baht-weight)
        reason     : agent reasoning (truncated to 200 chars)
        confidence : agent confidence 0-100

    Returns:
        dict: API response on success, or {"error": "..."} on failure.
    """
    api_key = os.getenv("TRADE_LOG_API_KEY", "").strip()
    if not api_key:
        print("[trade_log.py] TRADE_LOG_API_KEY not set — skipping professor log")
        return {"error": "TRADE_LOG_API_KEY not set"}

    payload = {
        "action":        action.upper(),
        "price":         price_thb,
        "reason":        reason[:500],
        "confidence":    confidence,
        "signal_source": "gold_agent_gpt4o_mini",
    }

    try:
        resp = requests.post(
            _TRADE_LOG_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=5,
        )
        data = resp.json()
        if resp.status_code == 201:
            print(f"[trade_log.py] Professor log OK: {action} @ {price_thb:,.0f} THB "
                  f"(id={data.get('data', {}).get('id', '?')})")
        else:
            print(f"[trade_log.py] Professor log FAILED {resp.status_code}: {data}")
        return data
    except Exception as e:
        print(f"[trade_log.py] Professor log error: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────
def get_recent_logs(n: int = 50) -> pd.DataFrame:
    """Return the last n rows from MongoDB or CSV fallback as a DataFrame."""

    # ── MongoDB ──────────────────────────────────────────────
    col = _get_mongo_collection()
    if col is not None:
        try:
            docs = list(col.find({}, {"_id": 0})
                           .sort("Timestamp", -1)
                           .limit(n))
            if docs:
                return pd.DataFrame(docs, columns=COLUMNS)
        except Exception as e:
            print(f"[trade_log.py] MongoDB read failed, using CSV: {e}")

    # ── CSV fallback ─────────────────────────────────────────
    try:
        if not os.path.exists(LOG_FILE):
            return pd.DataFrame(columns=COLUMNS)
        df = pd.read_csv(LOG_FILE, encoding="utf-8")
        return df.tail(n).iloc[::-1].reset_index(drop=True)
    except Exception as e:
        print(f"[trade_log.py] CSV read failed: {e}")
        return pd.DataFrame(columns=COLUMNS)


# ─────────────────────────────────────────────────────────────
# Clear
# ─────────────────────────────────────────────────────────────
def clear_log() -> None:
    """Delete all log entries from MongoDB or CSV fallback."""

    # ── MongoDB ──────────────────────────────────────────────
    col = _get_mongo_collection()
    if col is not None:
        try:
            result = col.delete_many({})
            print(f"[trade_log.py] MongoDB log cleared ({result.deleted_count} docs).")
            return
        except Exception as e:
            print(f"[trade_log.py] MongoDB clear failed: {e}")

    # ── CSV fallback ─────────────────────────────────────────
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
            print("[trade_log.py] CSV log cleared.")
    except Exception as e:
        print(f"[trade_log.py] CSV clear failed: {e}")
