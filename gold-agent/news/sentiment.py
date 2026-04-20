"""
news/sentiment.py
Fetches gold-related news headlines from NewsAPI.
Falls back to a rotating pool of mock headlines if the API key is missing,
so the app always shows different headlines each refresh.

Sentiment scoring uses GPT-4o-mini for nuanced analysis.
Falls back to keyword counting if the API call fails.
"""

import json
import os
import random
import hashlib
import time

from openai import OpenAI
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Sentiment cache — avoid duplicate API calls within same refresh cycle ──
# If the same headlines are seen again within 10 minutes, return cached result.
_sentiment_cache: dict = {"key": None, "value": None, "ts": 0.0}
_headlines_cache: dict = {"value": None, "ts": 0.0}
_CACHE_TTL = 600  # 10 minutes
_HEADLINES_TTL = 300  # 5 minutes — matches dashboard refresh interval

# Large pool of realistic mock headlines — 5 are randomly picked each refresh
# so users never see the same set twice when no API key is configured.
MOCK_HEADLINE_POOL = [
    "Gold prices surge amid global economic uncertainty and inflation fears",
    "Central banks increase gold reserves as dollar weakens",
    "Fed signals potential rate cuts, boosting gold demand",
    "Geopolitical tensions drive safe-haven buying in gold market",
    "Gold ETF inflows hit six-month high as investors seek protection",
    "US dollar weakness pushes gold to three-month high",
    "Goldman Sachs raises gold price target to $3,000 by year-end",
    "Middle East tensions fuel surge in safe-haven gold buying",
    "IMF warns of global recession risk — gold seen as key hedge",
    "Gold holds steady as traders await Fed interest rate decision",
    "Chinese central bank adds to gold reserves for fifth straight month",
    "Inflation data surprise sends gold futures sharply higher",
    "Gold miners report record profits as bullion prices climb",
    "BRICS nations accelerate de-dollarization, boosting gold demand",
    "Gold hits record high as US debt ceiling fears intensify",
    "Analysts warn of gold correction after overbought RSI reading",
    "Physical gold demand in Asia remains robust despite high prices",
    "Strong US jobs data dampens gold rally, dollar recovers",
    "Silver outperforms gold as industrial demand picks up",
    "Gold prices under pressure as Fed holds rates higher for longer",
]


def get_gold_news(max_headlines: int = 5) -> list[str]:
    """
    Fetch the latest gold-related news headlines from NewsAPI.

    If NEWS_API_KEY is missing or the request fails, returns a random
    selection from MOCK_HEADLINE_POOL so every refresh shows different headlines.

    Args:
        max_headlines (int): Maximum number of headlines to return. Default 5.

    Returns:
        list[str]: List of headline strings (real or mock).
    """
    if _headlines_cache["value"] is not None and time.time() - _headlines_cache["ts"] < _HEADLINES_TTL:
        print("[sentiment.py] Cache hit -> returning cached headlines (saved NewsAPI call)")
        return _headlines_cache["value"]

    api_key = os.getenv("NEWS_API_KEY", "").strip()

    if not api_key or api_key == "your_key_here":
        print("[sentiment.py] No NEWS_API_KEY. Using rotating mock headlines.")
        return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))

    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "gold price OR gold market OR XAU",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": max_headlines,
            "apiKey": api_key,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        articles = data.get("articles", [])

        if not articles:
            print("[sentiment.py] No articles returned. Using mock headlines.")
            return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))

        headlines = [
            a.get("title", "").strip()
            for a in articles[:max_headlines]
            if a.get("title", "").strip() and a.get("title") != "[Removed]"
        ]

        if not headlines:
            return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))

        print(f"[sentiment.py] Fetched {len(headlines)} real headlines.")
        _headlines_cache["value"] = headlines
        _headlines_cache["ts"] = time.time()
        return headlines

    except requests.exceptions.Timeout:
        print("[sentiment.py] NewsAPI timed out. Using mock headlines.")
    except requests.exceptions.HTTPError as e:
        print(f"[sentiment.py] NewsAPI HTTP error: {e}. Using mock headlines.")
    except Exception as e:
        print(f"[sentiment.py] Error fetching news: {e}. Using mock headlines.")

    return random.sample(MOCK_HEADLINE_POOL, min(max_headlines, len(MOCK_HEADLINE_POOL)))


def _keyword_sentiment(headlines: list[str]) -> str:
    """Rule-based fallback: count bullish vs bearish keywords."""
    bullish_kw = [
        "surge", "rise", "gain", "rally", "jump", "soar", "high",
        "demand", "buying", "boost", "positive", "growth", "record", "higher",
    ]
    bearish_kw = [
        "fall", "drop", "decline", "plunge", "crash", "low", "sell",
        "loss", "weakness", "down", "negative", "risk", "pressure", "correction",
    ]
    combined = " ".join(headlines).lower()
    bull = sum(combined.count(kw) for kw in bullish_kw)
    bear = sum(combined.count(kw) for kw in bearish_kw)
    if bull > bear:
        return "BULLISH"
    elif bear > bull:
        return "BEARISH"
    return "NEUTRAL"


def get_sentiment_strength(headlines: list[str]) -> dict:
    """
    Return sentiment label + strength based on keyword unanimity.

    Strength reflects how many headlines agree:
      5/5 or 4/5 same direction -> STRONG
      3/5 same direction        -> MODERATE
      otherwise                 -> WEAK

    Returns:
        dict: {"sentiment": str, "strength": str, "bull_count": int, "bear_count": int}
    """
    bullish_kw = [
        "surge", "rally", "high", "gain", "rise", "up", "buy", "bull",
        "record", "demand", "safe-haven", "haven", "inflation", "gold surges",
    ]
    bearish_kw = [
        "fall", "drop", "decline", "plunge", "crash", "low", "sell",
        "loss", "weakness", "down", "negative", "risk", "pressure", "correction",
    ]

    bull_count = 0
    bear_count = 0
    for h in headlines:
        h_lower = h.lower()
        b = sum(1 for kw in bullish_kw if kw in h_lower)
        s = sum(1 for kw in bearish_kw if kw in h_lower)
        if b > s:
            bull_count += 1
        elif s > b:
            bear_count += 1

    total = len(headlines) if headlines else 1
    dominant = max(bull_count, bear_count)
    ratio = dominant / total

    if ratio >= 0.8:
        strength = "STRONG"
    elif ratio >= 0.6:
        strength = "MODERATE"
    else:
        strength = "WEAK"

    if bull_count > bear_count:
        sentiment = "BULLISH"
    elif bear_count > bull_count:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"
        strength = "WEAK"

    return {
        "sentiment": sentiment,
        "strength": strength,
        "bull_count": bull_count,
        "bear_count": bear_count,
    }


def get_sentiment_summary(headlines: list[str]) -> str:
    """
    Score gold news sentiment using GPT-4o-mini.

    Sends headlines to GPT-4o-mini (temperature=0) and asks for a JSON
    sentiment label. Falls back to keyword counting if the API key is
    missing or the call fails.

    Args:
        headlines (list[str]): List of news headline strings.

    Returns:
        str: "BULLISH", "BEARISH", or "NEUTRAL".
    """
    # ── Cache check: same headlines within TTL -> skip API call ──────────────
    cache_key = hashlib.md5("|".join(headlines).encode()).hexdigest()
    now = time.time()
    if (_sentiment_cache["key"] == cache_key and
            now - _sentiment_cache["ts"] < _CACHE_TTL):
        print(f"[sentiment.py] Cache hit -> {_sentiment_cache['value']} (saved 1 Haiku call)")
        return _sentiment_cache["value"]

    # ── Choose your model here (uncomment the one you want to use) ──
    #ACTIVE_MODEL = "openai"
    ACTIVE_MODEL = "gemini"

    if ACTIVE_MODEL == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        client = OpenAI(api_key=api_key)
        model_name = "gpt-4o-mini"
    else:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        client = OpenAI(api_key=api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        model_name = "gemini-2.5-flash-lite"

    if not api_key:
        return _keyword_sentiment(headlines)

    try:
        headlines_text = "\n".join(f"- {h}" for h in headlines)
        prompt = (
            f"Analyze these gold market news headlines:\n{headlines_text}\n\n"
            "Return JSON only, no other text: "
            '{"sentiment": "BULLISH" or "BEARISH" or "NEUTRAL", "reasoning": "<1 sentence>"}'
        )
        response = client.chat.completions.create(
            model=model_name,
            max_tokens=100,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )

        # Track LLM cost
        try:
            from logger.cost_tracker import track_usage
            track_usage(response.usage, source="sentiment")
        except Exception:
            pass

        raw = response.choices[0].message.content.strip() if response.choices else ""
        if not raw:
            print("[sentiment.py] Empty response from GPT — falling back to keywords.")
            result = _keyword_sentiment(headlines)
            _sentiment_cache.update({"key": cache_key, "value": result, "ts": now})
            return result
        # Extract JSON even if the model wraps it in markdown code fences
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        data = json.loads(raw[start:end] if start != -1 else raw)
        label = data.get("sentiment", "").upper()
        if label in ("BULLISH", "BEARISH", "NEUTRAL"):
            print(f"[sentiment.py] GPT sentiment: {label}")
            _sentiment_cache.update({"key": cache_key, "value": label, "ts": now})
            return label
        result = _keyword_sentiment(headlines)
        _sentiment_cache.update({"key": cache_key, "value": result, "ts": now})
        return result

    except Exception as e:
        print(f"[sentiment.py] GPT sentiment failed ({e}). Falling back to keywords.")
        return _keyword_sentiment(headlines)


# Allow standalone testing
if __name__ == "__main__":
    headlines = get_gold_news()
    print("\nHeadlines:")
    for i, h in enumerate(headlines, 1):
        print(f"  {i}. {h}")
    print(f"\nSentiment: {get_sentiment_summary(headlines)}")
