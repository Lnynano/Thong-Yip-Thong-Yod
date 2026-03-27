import json
import os


def load_news_sentiment():

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

    if not os.path.exists(file_path):

        return {
            "sentiment": "Neutral",
            "confidence": "Low",
            "reason": "No sentiment yet"
        }

    with open(file_path, "r") as f:

        return json.load(f)