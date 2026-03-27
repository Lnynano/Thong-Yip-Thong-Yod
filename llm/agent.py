import os
import json

from dotenv import load_dotenv
from openai import OpenAI

##from data.news_reader import load_cached_news
from indicators.indicators import compute_indicators
from data.price_memory import get_price_history
from data.price_memory import split_history
from data.news_sentiment_reader import load_news_sentiment
from data.daily_market_reader import load_daily_market

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

def ask_llm(status):

    news = load_news_sentiment()

    daily_market = load_daily_market()

    indicators = compute_indicators()

    past_20, recent_10 = split_history()

    price_history = get_price_history()

    MIN_REQUIRED_MEMORY = 60

    if len(price_history) < MIN_REQUIRED_MEMORY:

        print(
            f"Waiting for enough data: "
            f"{len(price_history)}/{MIN_REQUIRED_MEMORY}"
        )

        return json.dumps({
            "action": "HOLD",
            "reason": "Waiting for enough price memory"
        })

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
    # global BIAS CHECK
    # =========================

    global_bias = "Neutral"

    if daily_market["daily_trend"] == "Uptrend":

        global_bias = "Prefer BUY"

    elif daily_market["daily_trend"] == "Downtrend":

        global_bias = "Prefer SELL"

    # =========================
    # PROMPT
    # =========================

    prompt = f"""
You are an intelligent gold trading AI.

Your goal is to maximize profit by reacting to market movement.

You should not be afraid to BUY during strong uptrends.

you can hold only 1 gold a time.

you have 2 helper agent there info is very useful

=========================

helper agent NO.1
Daily Market Overview:

Daily Trend: {daily_market["daily_trend"]}
Trend Strength: {daily_market["trend_strength"]}

Summary:
{daily_market["daily_summary"]}

=========================

helper agent NO.2
News Sentiment:

Sentiment: {news["sentiment"]}
Confidence: {news["confidence"]}

Reason:
{news["reason"]}

=========================

CURRENT PORTFOLIO STATUS:

Gold Held: {status["gold"]}

Cash Available: {status["cash"]}

Last Buy Price: {status["last_buy_price"]}

Current Profit (%): {status["profit_percent"]}

Cooldown Remaining: {status["cooldown"]}

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
20 Recent gold value(from 2min past value to now) : {recent_10}

Past Trend: {past_trend}
40 past gold value(2min ago) : {past_20}
=========================

Market Bias:

BUY Bias: {market_condition}
SELL Bias: {sell_bias}

Global Bias: {global_bias}

=========================

Trading Strategy:

1. Buy the Dip:
   If RSI < 45 → Strong BUY opportunity.

2. Sell Conditions:
   If RSI > 60 → good for SELL.
   If Trend becomes DOWN → Consider SELL.

3. Avoid HOLD too long.
   Trade when signals are meaningful.

=========================

SKILL

TREND FOLLOWING SKILL:

If the market is in an Uptrend
and price continues to rise steadily:

You are allowed to BUY even if RSI is between 55–65.

Do not wait too long during strong uptrends but it have to be clearly uptrends.
Strong trends should be followed.



REBOUND ENTRY SKILL:

If the market was falling
and then shows a small upward bounce:

This is a possible rebound entry.

Conditions:

Recent Trend was DOWN
Momentum turns positive
Price starts increasing again

→ Consider BUY.



MOMENTUM RIDE SKILL:

If momentum is strong
and trend is UP:

Prefer HOLD rather than SELL.

Ride the trend longer.
Do not sell too early.

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

    print("Daily Market Overview:")
    print(daily_market["daily_trend"])
    print(daily_market["trend_strength"])
    print(daily_market["daily_summary"])

    print("price history")
    print(recent_10)
    print(past_20)

    text = response.choices[0].message.content

    return text