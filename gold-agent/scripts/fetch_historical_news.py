"""
scripts/fetch_historical_news.py

ดึงข่าวทองคำจริงจาก GDELT Project (ฟรี ไม่ต้อง API Key)
สำหรับใช้ใน Backtest แทนข่าวจำลอง

Usage:
    python scripts/fetch_historical_news.py --start 2025-01-01 --end 2025-12-31
    python scripts/fetch_historical_news.py --start 2026-03-01 --end 2026-03-31

Output:
    data/historical_news_YYYY_MM.json  (แยกไฟล์ต่อเดือน)
"""

import argparse
import json
import os
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GOLD_QUERY = '"gold price" OR "gold market" OR "XAU" OR "gold futures" OR "bullion"'


def fetch_gdelt_headlines(date: datetime, max_articles: int = 10) -> list[str]:
    """ดึงข่าวทองคำจาก GDELT สำหรับวันที่กำหนด"""
    start_str = date.strftime("%Y%m%d") + "000000"
    end_str = date.strftime("%Y%m%d") + "235959"

    params = {
        "query": GOLD_QUERY,
        "mode": "artlist",
        "maxrecords": max_articles,
        "startdatetime": start_str,
        "enddatetime": end_str,
        "format": "json",
        "sort": "datedesc",
    }

    try:
        resp = requests.get(GDELT_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        articles = data.get("articles", [])
        headlines = [a.get("title", "").strip() for a in articles if a.get("title")]
        return headlines[:max_articles]
    except Exception as e:
        print(f"  [GDELT] Error on {date.date()}: {e}")
        return []


def score_sentiment_gemini(headlines: list[str], date_str: str) -> dict:
    """ใช้ Gemini วิเคราะห์ sentiment จาก headlines จริง"""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not headlines:
        return _keyword_sentiment(headlines)

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        headlines_text = "\n".join(f"- {h}" for h in headlines[:5])
        prompt = f"""Analyze these gold market news headlines from {date_str}:
{headlines_text}

Return ONLY this JSON (no other text):
{{
  "sentiment": "Bullish" | "Bearish" | "Neutral" | "Strongly Bullish" | "Strongly Bearish",
  "headline": "<pick the single most impactful headline>",
  "impact": "High" | "Moderate" | "Low"
}}"""

        resp = client.chat.completions.create(
            model="gemini-2.5-flash-lite",
            max_tokens=150,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.choices[0].message.content.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        print(f"  [Gemini] Sentiment error: {e}")
        return _keyword_sentiment(headlines)


def _keyword_sentiment(headlines: list[str]) -> dict:
    """Fallback: keyword-based sentiment"""
    bullish_kw = ["surge", "rise", "gain", "rally", "jump", "soar", "high", "demand", "buying", "record"]
    bearish_kw = ["fall", "drop", "decline", "plunge", "crash", "low", "sell", "loss", "weakness", "down", "pressure"]

    text = " ".join(headlines).lower()
    bull = sum(text.count(kw) for kw in bullish_kw)
    bear = sum(text.count(kw) for kw in bearish_kw)

    if bull > bear * 1.5:
        sentiment = "Bullish"
        impact = "Moderate"
    elif bear > bull * 1.5:
        sentiment = "Bearish"
        impact = "Moderate"
    else:
        sentiment = "Neutral"
        impact = "Low"

    headline = headlines[0] if headlines else "No major gold news today."
    return {"sentiment": sentiment, "headline": headline, "impact": impact}


def fetch_month_news(year: int, month: int) -> dict:
    """ดึงข่าวทั้งเดือน คืนค่าเป็น dict รายวัน"""
    # First day of month
    start = datetime(year, month, 1)
    # Last day of month
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(days=1)

    news_db = {}
    current = start
    total_days = (end - start).days + 1
    day_num = 0

    print(f"\n📰 Fetching real news for {year}-{month:02d} ({total_days} days)...")
    print(f"   Source: GDELT Project (gdeltproject.org)")
    print(f"   Sentiment: Gemini AI analysis\n")

    while current <= end:
        day_num += 1
        date_str = current.strftime("%Y-%m-%d")
        print(f"  [{day_num:2d}/{total_days}] {date_str}...", end=" ", flush=True)

        headlines = fetch_gdelt_headlines(current, max_articles=5)

        if headlines:
            result = score_sentiment_gemini(headlines, date_str)
            result["_headlines"] = headlines  # เก็บ headlines ต้นฉบับไว้ด้วย
            news_db[date_str] = result
            print(f"✅ {result['sentiment']} ({len(headlines)} headlines)")
        else:
            # ถ้าไม่มีข่าว ใช้ค่า Neutral
            news_db[date_str] = {
                "sentiment": "Neutral",
                "headline": "No significant gold news available for this date.",
                "impact": "Low",
                "_headlines": []
            }
            print("⚠️  No news found (Neutral)")

        current += timedelta(days=1)
        time.sleep(1.0)  # Rate limit: 1 req/sec สำหรับ GDELT

    return news_db


def save_news(news_db: dict, year: int, month: int):
    """บันทึกข่าวลงไฟล์ JSON"""
    os.makedirs(_DATA_DIR, exist_ok=True)
    filename = os.path.join(_DATA_DIR, f"historical_news_{year}_{month:02d}.json")

    # Save full version (with _headlines)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(news_db, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Saved: {filename}")
    print(f"   {len(news_db)} days of news data")

    # Summary
    sentiments = [v.get("sentiment", "?") for v in news_db.values()]
    from collections import Counter
    counts = Counter(sentiments)
    print(f"   Sentiment breakdown: {dict(counts)}")


def main():
    parser = argparse.ArgumentParser(description="Fetch real gold news from GDELT for backtest use")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD (e.g. 2026-03-01)")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD (e.g. 2026-12-31)")
    args = parser.parse_args()

    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")

    # Enumerate months in range
    current_month = datetime(start_dt.year, start_dt.month, 1)
    end_month = datetime(end_dt.year, end_dt.month, 1)

    while current_month <= end_month:
        year = current_month.year
        month = current_month.month

        # Check if file already exists
        filename = os.path.join(_DATA_DIR, f"historical_news_{year}_{month:02d}.json")
        if os.path.exists(filename):
            print(f"\n⏭️  Skipping {year}-{month:02d} (file already exists: {filename})")
            print(f"   Delete the file to re-fetch.")
        else:
            news_db = fetch_month_news(year, month)
            save_news(news_db, year, month)

        # Next month
        if month == 12:
            current_month = datetime(year + 1, 1, 1)
        else:
            current_month = datetime(year, month + 1, 1)

    print("\n✅ Done! All news data fetched and saved.")
    print("\nNext step: Run backtest — it will automatically use the real news files.")
    print("  python backtest.py --start 2026-03-01 --end 2026-03-31 --interval 30m")


if __name__ == "__main__":
    main()
