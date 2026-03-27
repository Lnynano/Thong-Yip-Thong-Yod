import json
import os


def load_daily_market():

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

    if not os.path.exists(file_path):

        return {
            "daily_trend": "Sideways",
            "trend_strength": "Weak",
            "daily_summary": "No daily data yet"
        }

    with open(file_path, "r") as f:

        return json.load(f)