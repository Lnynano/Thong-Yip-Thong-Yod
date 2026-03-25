import json
import os


def load_cached_news():

    BASE_DIR = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    news_file = os.path.join(
        BASE_DIR,
        "data",
        "news_cache.json"
    )

    if not os.path.exists(news_file):

        print("No cached news found")

        return []

    with open(news_file, "r") as f:

        news = json.load(f)

    print("Loaded news from cache")

    return news