import os
import json

from dotenv import load_dotenv
from openai import OpenAI

from data.historical_price import fetch_daily_market_data
from data.news_sentiment_reader import load_news_sentiment

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def analyze_daily_market():

    prices = fetch_daily_market_data()

    if not prices:

        print("No historical data")

        return

    news_sentiment = load_news_sentiment()

    prompt = f"""
You are a professional gold market analyst.

Analyze the past 24 hours of gold prices.

Prices:
{prices}

News Sentiment:
{news_sentiment}

Your job:

1. Detect overall trend
2. Detect turning point
3. Describe market behavior

Return JSON:

{{
 "daily_trend": "Uptrend | Downtrend | Sideways",
 "turning_point_index": number,
 "trend_strength": "Strong | Moderate | Weak",
 "daily_summary": "short explanation"
}}
"""

    response = client.chat.completions.create(

        model="gpt-4o-mini",

        messages=[

            {
                "role": "user",
                "content": prompt
            }

        ],

        response_format={
            "type": "json_object"
        }

    )

    result = response.choices[0].message.content

    save_daily_market(result)


def save_daily_market(result):

    BASE_DIR = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    file_path = os.path.join(
        BASE_DIR,
        "data",
        "daily_market.json"
    )

    data = json.loads(result)

    with open(file_path, "w") as f:

        json.dump(data, f, indent=4)

    print("Daily market summary saved")