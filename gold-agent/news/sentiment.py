"""
news/sentiment.py
Fetches gold-related news headlines from NewsAPI.
Falls back to realistic mock headlines if the API key is missing or the
request fails, ensuring the application always runs.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Mock headlines used as fallback when NewsAPI is unavailable
MOCK_HEADLINES = [
    "Gold prices surge amid global economic uncertainty and inflation fears",
    "Central banks increase gold reserves as dollar weakens",
    "Fed signals potential rate cuts, boosting gold demand",
    "Geopolitical tensions drive safe-haven buying in gold market",
    "Gold ETF inflows hit six-month high as investors seek protection",
]


def get_gold_news(max_headlines: int = 5) -> list[str]:
    """
    Fetch the latest gold-related news headlines from NewsAPI.

    Requires NEWS_API_KEY in the .env file. If the key is missing or the
    request fails, returns mock headlines so the application continues running.

    Args:
        max_headlines (int): Maximum number of headlines to return. Default is 5.

    Returns:
        list[str]: List of headline strings (real or mock).
    """
    api_key = os.getenv("NEWS_API_KEY", "").strip()

    if not api_key or api_key == "your_key_here":
        print("[sentiment.py] No NEWS_API_KEY found. Using mock headlines.")
        return MOCK_HEADLINES[:max_headlines]

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
            return MOCK_HEADLINES[:max_headlines]

        headlines = []
        for article in articles[:max_headlines]:
            title = article.get("title", "").strip()
            if title and title != "[Removed]":
                headlines.append(title)

        if not headlines:
            return MOCK_HEADLINES[:max_headlines]

        print(f"[sentiment.py] Fetched {len(headlines)} real headlines.")
        return headlines

    except requests.exceptions.Timeout:
        print("[sentiment.py] NewsAPI request timed out. Using mock headlines.")
        return MOCK_HEADLINES[:max_headlines]

    except requests.exceptions.HTTPError as e:
        print(f"[sentiment.py] NewsAPI HTTP error: {e}. Using mock headlines.")
        return MOCK_HEADLINES[:max_headlines]

    except Exception as e:
        print(f"[sentiment.py] Error fetching news: {e}. Using mock headlines.")
        return MOCK_HEADLINES[:max_headlines]


def get_sentiment_summary(headlines: list[str]) -> str:
    """
    Generate a simple rule-based sentiment summary from headlines.

    Counts bullish vs bearish keywords to infer market sentiment.

    Args:
        headlines (list[str]): List of news headline strings.

    Returns:
        str: One of "BULLISH", "BEARISH", or "NEUTRAL".
    """
    bullish_keywords = [
        "surge", "rise", "gain", "rally", "jump", "soar", "high",
        "demand", "buying", "boost", "positive", "growth", "record",
    ]
    bearish_keywords = [
        "fall", "drop", "decline", "plunge", "crash", "low", "sell",
        "loss", "weakness", "down", "negative", "risk", "pressure",
    ]

    combined = " ".join(headlines).lower()
    bull_count = sum(combined.count(kw) for kw in bullish_keywords)
    bear_count = sum(combined.count(kw) for kw in bearish_keywords)

    if bull_count > bear_count:
        return "BULLISH"
    elif bear_count > bull_count:
        return "BEARISH"
    else:
        return "NEUTRAL"


# Allow standalone testing
if __name__ == "__main__":
    headlines = get_gold_news()
    print("\nHeadlines:")
    for i, h in enumerate(headlines, 1):
        print(f"  {i}. {h}")
    print(f"\nSentiment: {get_sentiment_summary(headlines)}")
