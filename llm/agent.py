import os
import json

from dotenv import load_dotenv
from openai import OpenAI

from data.news_reader import load_cached_news
from indicators.indicators import compute_indicators
from data.price_memory import get_price_history
from data.price_memory import split_history

from indicators.trend_features import (
    calculate_slope,
    calculate_trend,
    calculate_volatility,
    calculate_momentum
)

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def format_news(news_list):

    combined_text = ""

    for i, news in enumerate(news_list):

        combined_text += (
            f"{i+1}. {news['title']}\n"
        )

    return combined_text


def ask_llm():

    news = load_cached_news()

    indicators = compute_indicators()

    news_text = format_news(news)

    price_history = get_price_history()

    past_20, recent_10 = split_history()

    # =========================
    # FEATURE CALCULATION
    # =========================

    recent_slope = calculate_slope(recent_10)

    recent_trend = calculate_trend(recent_10)

    recent_volatility = calculate_volatility(recent_10)

    recent_momentum = calculate_momentum(recent_10)

    past_slope = calculate_slope(past_20)

    past_trend = calculate_trend(past_20)

    past_volatility = calculate_volatility(past_20)

    # =========================
    # SMART BUY SCORING SYSTEM
    # =========================

    buy_score = 0

    # 1️⃣ Buy the Dip (ซื้อของถูก)

    if indicators["rsi"] < 45:

        buy_score += 1

    # 2️⃣ Trend Following (สำคัญมาก)

    if (
        indicators["rsi"] >= 45
        and indicators["rsi"] <= 70
        and recent_trend == "UP"
        and recent_momentum > 0
    ):

        buy_score += 1

    # 3️⃣ MACD confirmation

    if indicators['macd'] > indicators['macd_signal']:

        buy_score += 1

    # 4️⃣ Strong momentum bonus

    if recent_momentum > 0:

        buy_score += 1

    # =========================
    # MARKET CONDITION
    # =========================

    if buy_score >= 3:

        market_condition = "Strong BUY Bias"

    elif buy_score == 2:

        market_condition = "Moderate BUY Bias"

    elif buy_score == 1:

        market_condition = "Neutral"

    else:

        market_condition = "Risky for BUY"

    # =========================
    # SELL BIAS CHECK
    # =========================

    sell_bias = "Neutral"

    if indicators["rsi"] > 70:

        sell_bias = "Overbought"

    elif recent_trend == "DOWN":

        sell_bias = "Downtrend Risk"

    # =========================
    # PROMPT
    # =========================

    prompt = f"""
You are an intelligent gold trading AI.

Your goal is to maximize profit by reacting to market movement.

You should not be afraid to BUY during strong uptrends.

=========================

Market Data:

Price: {indicators['price']}
RSI: {indicators['rsi']}
MACD: {indicators['macd']}
MACD Signal: {indicators['macd_signal']}

=========================

Recent Market Behavior:

Recent Trend: {recent_trend}
Recent Slope: {recent_slope}
Recent Volatility: {recent_volatility}
Recent Momentum: {recent_momentum}

Past Trend: {past_trend}

=========================

Market Bias:

BUY Bias: {market_condition}
SELL Bias: {sell_bias}

=========================

Recent News:

{news_text}

=========================

Trading Strategy:

1. Buy the Dip:
   If RSI < 45 → Strong BUY opportunity.

2. Trend Following:
   If BUY Bias is Strong or Moderate
   AND Trend is UP
   → BUY is allowed even if RSI is 50–65.

3. Sell Conditions:
   If RSI > 60 → good for SELL.
   If Trend becomes DOWN → Consider SELL.

4. Avoid HOLD too long.
   Trade when signals are meaningful.

=========================

Return JSON only:

{{
 "action": "BUY | SELL | HOLD",
 "reason": "short explanation"
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

    text = response.choices[0].message.content

    return text