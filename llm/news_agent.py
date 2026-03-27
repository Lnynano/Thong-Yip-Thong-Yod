import os
import json

from dotenv import load_dotenv
from openai import OpenAI

from data.news_reader import load_cached_news

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def format_news(news_list):

    text = ""

    for i, news in enumerate(news_list):

        text += f"{i+1}. {news['title']}\n"

    return text


def analyze_news_sentiment():

    news = load_cached_news()

    if not news:
        print("No news to analyze")
        return

    news_text = format_news(news)

    prompt = f"""
You are a professional financial news analyst.

Analyze the following news headlines
and determine overall sentiment for GOLD market.

Return JSON:

{{
 "sentiment": "Bullish | Bearish | Neutral",
 "confidence": "High | Medium | Low",
 "reason": "short explanation"
}}

News:

{news_text}
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

    save_news_sentiment(result)


def save_news_sentiment(result):

    BASE_DIR = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    file_path = os.path.join(
        BASE_DIR,
        "data",
        "news_sentiment.json"
    )

    data = json.loads(result)

    with open(file_path, "w") as f:

        json.dump(data, f, indent=4)

    print("News sentiment saved")