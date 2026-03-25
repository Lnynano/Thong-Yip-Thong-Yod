import math


def calculate_slope(prices):

    if len(prices) < 2:
        return 0

    return prices[-1] - prices[0]


def calculate_trend(prices):

    slope = calculate_slope(prices)

    if slope > 0:
        return "UP"

    elif slope < 0:
        return "DOWN"

    return "SIDEWAYS"


def calculate_volatility(prices):

    if len(prices) < 2:
        return 0

    mean = sum(prices) / len(prices)

    variance = sum(
        (p - mean) ** 2
        for p in prices
    ) / len(prices)

    return math.sqrt(variance)


def calculate_momentum(prices):

    if len(prices) < 2:
        return 0

    return prices[-1] - prices[-2]