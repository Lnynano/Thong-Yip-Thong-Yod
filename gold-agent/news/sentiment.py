"""
news/sentiment.py
Fetches gold-related news headlines from NewsAPI.
Falls back to a rotating pool of mock headlines if the API key is missing,
so the app always shows different headlines each refresh.

Sentiment scoring uses Claude Haiku for nuanced analysis.
Falls back to keyword counting if the API call fails.
"""

import json
import os
import random

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

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


def get_sentiment_summary(headlines: list[str]) -> str:
    """
    Score gold news sentiment using Claude Haiku.

    Sends headlines to Claude Haiku (temperature=0) and asks for a JSON
    sentiment label. Falls back to keyword counting if the API key is
    missing or the call fails.

    Args:
        headlines (list[str]): List of news headline strings.

    Returns:
        str: "BULLISH", "BEARISH", or "NEUTRAL".
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _keyword_sentiment(headlines)

    try:
        client = anthropic.Anthropic()
        headlines_text = "\n".join(f"- {h}" for h in headlines)
        prompt = (
            f"Analyze these gold market news headlines:\n{headlines_text}\n\n"
            "Return JSON only, no other text: "
            '{"sentiment": "BULLISH" or "BEARISH" or "NEUTRAL", "reasoning": "<1 sentence>"}'
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text)
        label = data.get("sentiment", "").upper()
        if label in ("BULLISH", "BEARISH", "NEUTRAL"):
            print(f"[sentiment.py] Claude sentiment: {label}")
            return label
        return _keyword_sentiment(headlines)

    except Exception as e:
        print(f"[sentiment.py] Claude sentiment failed ({e}). Falling back to keywords.")
        return _keyword_sentiment(headlines)


# Allow standalone testing
if __name__ == "__main__":
    headlines = get_gold_news()
    print("\nHeadlines:")
    for i, h in enumerate(headlines, 1):
        print(f"  {i}. {h}")
    print(f"\nSentiment: {get_sentiment_summary(headlines)}")
