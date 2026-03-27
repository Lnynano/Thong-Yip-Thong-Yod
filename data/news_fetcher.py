import json
import os

from datetime import datetime
from data.news import fetch_gold_news


def save_news_to_json():

    print("Fetching news from API...")

    news = fetch_gold_news()

    data = {
        "last_updated": datetime.utcnow().isoformat(),
        "news": news
    }

    BASE_DIR = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    NEWS_FILE = os.path.join(
        BASE_DIR,
        "data",
        "news_cache.json"
    )
    

    with open(NEWS_FILE, "w") as f:
        json.dump(data, f, indent=4)

    print("News saved to JSON")


if __name__ == "__main__":

    save_news_to_json()