"""
agent/daily_market_agent.py
Daily macro market context agent — runs once per day, caches result.

Analyzes 90-day gold price data + recent news to produce a daily market bias
(Uptrend / Downtrend / Sideways) and trend strength. This context is injected
into the main ReAct agent's get_indicators tool result so Claude has a macro
view without needing extra API calls every 5 minutes.

Storage strategy (auto-detected):
  - MONGODB_URI set  →  MongoDB "daily_market" collection
  - Not set          →  local data/daily_market.json

Cache TTL: 1 day — re-runs automatically after midnight Thai time.
Model: claude-haiku (cheap, fast, sufficient for trend summary)
"""

import json
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

_THAI_TZ      = timezone(timedelta(hours=7))
_CACHE_FILE   = os.path.join(os.path.dirname(__file__), "..", "data", "daily_market.json")
_DEFAULT      = {
    "daily_trend":    "Sideways",
    "trend_strength": "Weak",
    "turning_point":  "None detected",
    "daily_summary":  "No daily market analysis available yet.",
    "generated_date": "",
}


# ─────────────────────────────────────────────────────────────
# Storage helpers (MongoDB or JSON fallback)
# ─────────────────────────────────────────────────────────────
def _get_col():
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client["gold_agent"]["daily_market"]
    except Exception as e:
        print(f"[daily_market_agent.py] MongoDB connect failed: {e}")
        return None


def _load_cache() -> dict:
    col = _get_col()
    if col is not None:
        try:
            doc = col.find_one({"_id": "main"})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception:
            pass
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(data: dict) -> None:
    col = _get_col()
    if col is not None:
        try:
            col.replace_one({"_id": "main"}, {"_id": "main", **data}, upsert=True)
            return
        except Exception as e:
            print(f"[daily_market_agent.py] MongoDB save failed: {e}")
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[daily_market_agent.py] JSON save failed: {e}")


# ─────────────────────────────────────────────────────────────
# Cache validity check
# ─────────────────────────────────────────────────────────────
def _is_cache_valid(cache: dict) -> bool:
    """Return True if cache was generated today (Thai date)."""
    today = datetime.now(_THAI_TZ).strftime("%Y-%m-%d")
    return cache.get("generated_date", "") == today


# ─────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────
def _run_analysis() -> dict:
    """Call Claude Haiku to analyze macro gold trend for today."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("[daily_market_agent.py] No API key — skipping analysis.")
        return _DEFAULT

    try:
        from openai import OpenAI
        from data.fetch import get_gold_price
        from news.sentiment import get_gold_news

        df = get_gold_price()
        if df.empty:
            return _DEFAULT

        # Last 30 closing prices for macro trend
        prices = df["Close"].tail(30).round(2).tolist()
        news   = get_gold_news(5)
        news_text = "\n".join(f"- {h}" for h in news)

        prompt = f"""You are a professional gold market analyst specializing in Thai retail gold (สนค).

Analyze the past 30 days of XAUUSD closing prices and recent news.

Prices (oldest → newest):
{prices}

Recent news headlines:
{news_text}

Return JSON only, no other text:
{{
  "daily_trend":    "Uptrend" | "Downtrend" | "Sideways",
  "trend_strength": "Strong" | "Moderate" | "Weak",
  "turning_point":  "<brief description of any recent trend reversal, or 'None detected'>",
  "daily_summary":  "<2 sentences: current market state and key driver>"
}}"""

        client   = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model      = "gpt-4o-mini",
            max_tokens = 256,
            temperature= 0,
            messages   = [{"role": "user", "content": prompt}],
        )
        text   = response.choices[0].message.content.strip()
        start  = text.find("{")
        end    = text.rfind("}") + 1
        result = json.loads(text[start:end])
        result["generated_date"] = datetime.now(_THAI_TZ).strftime("%Y-%m-%d")
        print(f"[daily_market_agent.py] Analysis complete: {result['daily_trend']} / {result['trend_strength']}")
        return result

    except Exception as e:
        print(f"[daily_market_agent.py] Analysis failed: {e}")
        return _DEFAULT


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────
def get_daily_market() -> dict:
    """
    Return today's macro market context.

    Uses cached result if already generated today (Thai date).
    Re-runs analysis if cache is stale (new day).

    Returns:
        dict: {
            "daily_trend"    : "Uptrend" | "Downtrend" | "Sideways",
            "trend_strength" : "Strong" | "Moderate" | "Weak",
            "turning_point"  : str,
            "daily_summary"  : str,
            "generated_date" : "YYYY-MM-DD",
        }
    """
    cache = _load_cache()
    if _is_cache_valid(cache):
        print(f"[daily_market_agent.py] Cache hit → {cache.get('daily_trend')} / {cache.get('trend_strength')}")
        return cache

    print("[daily_market_agent.py] Cache stale — running daily analysis...")
    result = _run_analysis()
    _save_cache(result)
    return result


if __name__ == "__main__":
    data = get_daily_market()
    print("\n--- Daily Market Context ---")
    print(f"Trend    : {data['daily_trend']} ({data['trend_strength']})")
    print(f"Turning  : {data['turning_point']}")
    print(f"Summary  : {data['daily_summary']}")
    print(f"Generated: {data['generated_date']}")
