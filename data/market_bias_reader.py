import json
import os


def load_market_bias():

    BASE_DIR = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    file_path = os.path.join(
        BASE_DIR,
        "data",
        "market_bias.json"
    )

    if not os.path.exists(file_path):

        return {
            "market_bias": "Neutral",
            "trend_strength": "Weak",
            "volatility_level": "Medium",
            "summary": "No data yet"
        }

    with open(file_path, "r") as f:

        return json.load(f)