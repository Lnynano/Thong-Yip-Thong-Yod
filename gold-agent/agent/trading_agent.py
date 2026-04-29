"""
agent/trading_agent.py
GPT-4o-mini-powered ReAct gold trading agent using OpenAI tool calling.

Architecture:
  - ReAct trajectory: τ = (s₀, t₁, a₁, o₁, t₂, a₂, o₂, ..., aₙ, oₙ)
  - Structured state representation (markdown tables, not free-form prose)
  - Progressive disclosure: global state first, then targeted details
  - Template-driven system prompt: ROLE / CONSTRAINTS / STATE / OUTPUT
  - Minimum trade size        : 1,000 THB
  - Typical position size : 90%-100% of available balance (Aggressive).
  - Objective: Complete at least 1 full cycle (BUY+SELL) per window.
  - Execution router with safety bounds validation
  - temperature=0 for consistent JSON tool calling (τ→0 = near-deterministic)
  - JSON retry logic, infinite loop guard, arithmetic hallucination prevention

Model: gpt-4o-mini
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# System Prompt — template structure
# ROLE / CONSTRAINTS / INSTRUCTIONS / OUTPUT FORMAT
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """# ROLE
You are an institutional quantitative trading agent specializing in Thai Gold 96.5%.
You combine mathematical technical indicators with macroeconomic news sentiment.
Your analysis is used by Thai retail investors, so you also consider Thai Baht pricing.

# CONSTRAINTS (HARD LIMITS)
1. Minimum trade size : 1,000 THB.
2. Typical position size : 90%-100% of available balance (Aggressive).
3. Window Objective : Complete at least ONE full cycle (BUY and SELL) per window. 
4. Only issue BUY when macro sentiment ALIGNS with momentum indicators.
5. Pre-computed indicators are authoritative — NEVER re-calculate math yourself.
6. You must call all three tools (get_price, get_indicators, get_news) before deciding.
7. SPREAD RULE (CRITICAL): The gold price has a buy-sell spread of ~200-400 THB.
   - When you BUY, you pay the SELL price (higher). When you SELL, you receive the BUY price (lower).
   - You start every trade already down by the spread amount.
   - ONLY BUY if your expected upside is at least 600 THB to cover spread and profit.
   - If market conditions are flat, HOLD — capital preservation is #1 priority.

# TREND & REGIME FILTER (PRIORITY)
# HISTORICAL EXPERT KNOWLEDGE (Learned from 2025 Data)
1. DXY CORRELATION: Gold and DXY are inversely correlated. If DXY is in an uptrend, avoid BUYING Gold even if indicators look oversold.
2. TREND ALIGNMENT (CRITICAL): The 'daily_trend' from tools is your primary guide. Do not BUY if the 5-day trend is "DOWN", and do not SELL if it is "UP", unless news is extremely strong (>8 confidence).
3. SPREAD AWARENESS: Every HSH trade starts with a -200 THB disadvantage. If the technical setup doesn't suggest a move of at least 400-500 THB, the trade is low quality.
4. SIDEWAYS TRAP: Avoid trading in the middle of Bollinger Bands or when RSI is 45-55. Wait for extremes.

# DECISION CRITERIA
- BUY  : RSI < 35 AND MACD histogram slope is positive AND Trend is NOT Down.
         Confidence >= 75% required.
- SELL : RSI > 65 AND MACD histogram slope is negative AND Trend is NOT Up.
         Confidence >= 75% required.
- HOLD : Mixed signals, RSI 40-60, or Trend-Signal conflict.

# QUOTA PRESSURE RULES
When the system prompt indicates "QUOTA PRESSURE":
1. YOU ARE STRICTLY FORBIDDEN FROM OUTPUTTING 'HOLD'.
2. You MUST find a directional entry (BUY or SELL) based on the micro-trend.
3. Lower your threshold: Confidence >= 55% is acceptable to meet the competition quota.

# OUTPUT FORMAT (machine-readable JSON only)
After calling all tools, respond with ONLY this JSON (no other text):
{
  "decision"    : "BUY" | "SELL" | "HOLD",
  "confidence"  : <integer 1-100>,
  "reasoning"   : "<2-4 sentence explanation combining 2025 expert knowledge + current technicals/news>",
  "key_factors" : ["<factor1>", "<factor2>", "<factor3>"],
  "risk_note"   : "<one sentence on the main threat to this trade>"
}"""


# ─────────────────────────────────────────────────────────────
# Tool Definitions — function calling interface contract
# ─────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_price",
            "description": (
                "Retrieves the current XAUUSD (gold futures) price in USD per troy ounce "
                "and a recent OHLCV summary table. Call this FIRST to establish market context. "
                "Returns structured markdown-style data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Summary period: '5d' (default), '10d', or '30d'",
                        "enum": ["5d", "10d", "30d"],
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_indicators",
            "description": (
                "Returns pre-computed technical indicators (RSI, MACD, Bollinger Bands). "
                "All values are deterministically calculated from 90 days of price data. "
                "NEVER re-calculate these yourself — use these values as authoritative. "
                "RSI > 70 = overbought, RSI < 30 = oversold. "
                "Positive MACD histogram = bullish momentum."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": (
                "Fetches the 5 most recent gold market news headlines with overall sentiment. "
                "THIS IS YOUR SUPERPOWER: combine this news with mathematical "
                "indicators. A single macro event (Fed rate cut, war escalation) can override "
                "all technical signals. Always check news before deciding."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of headlines to retrieve (1-5, default 5)",
                    }
                },
                "required": [],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────────────────────
def _execute_tool(
    tool_name: str, tool_input: dict, _tool_config: dict | None = None
) -> str:
    """
    Execute a tool call and return a structured JSON string result.

    All numerical calculations happen here (deterministically),
    never inside the LLM. The LLM only reasons about pre-computed values.

    Returns structured markdown-table-style state for the LLM.

    Args:
        tool_name (str): Name of the tool to execute ('get_price', 'get_indicators', 'get_news').
        tool_input (dict): Input parameters for the tool.

    Returns:
        str: JSON-encoded result string. Returns error JSON on failure.
    """
    try:
        import sys
        import os

        sys.path.insert(
            0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        )

        # ── Tool: get_price ──────────────────────────────────────────────────
        if tool_name == "get_price":
            from data.fetch import get_gold_price, get_hsh_price

            df = get_gold_price()
            if df.empty:
                return json.dumps({"error": "Could not fetch gold price data."})

            period_map = {"5d": 5, "10d": 10, "30d": 30}
            days = period_map.get(tool_input.get("period", "5d"), 5)
            recent = df.tail(days)

            current_price = float(df["Close"].iloc[-1])
            price_change_pct = round(
                (recent["Close"].iloc[-1] - recent["Close"].iloc[0])
                / recent["Close"].iloc[0]
                * 100,
                2,
            )

            # HSH live price is the authoritative current price (96.5% Thai gold)
            result = {"asset": "Thai Gold 96.5% / XAUUSD"}
            try:
                hsh = get_hsh_price()
                if hsh:
                    result["current_price_source"] = "HSH_LIVE_96.5pct"
                    result["current_price_thb_sell"] = hsh["sell"]
                    result["current_price_thb_buy"] = hsh["buy"]
                    result["spread_thb"] = hsh["spread"]
                    result["note"] = (
                        "sell_thb = price you PAY to BUY. buy_thb = price you RECEIVE when SELLING."
                    )
                else:
                    result["current_price_source"] = "yfinance_futures"
                    result["current_price_usd"] = round(current_price, 2)
            except Exception:
                result["current_price_source"] = "yfinance_futures"
                result["current_price_usd"] = round(current_price, 2)

            result["historical_usd_close"] = round(current_price, 2)
            result["period_days"] = len(recent)
            result["ohlcv_summary"] = {
                "open": round(float(recent["Open"].iloc[0]), 2),
                "high": round(float(recent["High"].max()), 2),
                "low": round(float(recent["Low"].min()), 2),
                "close": round(float(recent["Close"].iloc[-1]), 2),
                "avg_volume": int(recent["Volume"].mean()),
            }
            result["price_change_pct"] = price_change_pct
            result["trend"] = "UP" if price_change_pct > 0 else "DOWN"

            return json.dumps(result)

        # ── Tool: get_indicators ─────────────────────────────────────────────
        elif tool_name == "get_indicators":
            from data.fetch import get_gold_price
            from indicators.tech import (
                calculate_rsi,
                calculate_macd,
                calculate_bollinger_bands,
            )

            df = get_gold_price()
            if df.empty:
                return json.dumps({"error": "Could not calculate indicators."})

            rsi = calculate_rsi(df)
            macd = calculate_macd(df)
            bb = calculate_bollinger_bands(df)

            rsi_signal = (
                "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
            )
            macd_signal = "BULLISH" if macd["histogram"] > 0 else "BEARISH"

            # ── BUY/SELL Score (0-5 each) ─────────────────────────────────────
            # Pre-score signals so the agent has quantified hints, reduces hallucination
            _cfg = _tool_config or {}
            use_macd = _cfg.get("use_macd", True)
            use_bb = _cfg.get("use_bb", True)
            use_news = _cfg.get("use_news", True)
            use_dxy_vix = _cfg.get("use_dxy_vix", True)
            use_h1_mtf = _cfg.get("use_h1_mtf", True)
            use_daily = _cfg.get("use_daily_bias", True)
            use_volume = _cfg.get("use_volume_spike", True)

            buy_score = 0
            sell_score = 0

            # RSI (always on — core signal)
            if rsi < 30:
                buy_score += 2
            elif rsi < 40:
                buy_score += 1
            if rsi > 70:
                sell_score += 2
            elif rsi > 65:
                sell_score += 1

            # MACD histogram
            if use_macd:
                if macd["histogram"] > 0:
                    buy_score += 1
                else:
                    sell_score += 1

            # Bollinger Bands %B
            if use_bb:
                if bb["percent_b"] < 0.2:
                    buy_score += 1
                elif bb["percent_b"] > 0.8:
                    sell_score += 1

            # Daily market bias (cached — free, runs once/day)
            daily_bias = "Sideways"
            daily_strength = "Weak"
            daily_summary = ""
            if use_daily:
                try:
                    from agent.daily_market_agent import get_daily_market

                    dm = get_daily_market()
                    daily_bias = dm.get("daily_trend", "Sideways")
                    daily_strength = dm.get("trend_strength", "Weak")
                    daily_summary = dm.get("daily_summary", "")
                    if daily_bias == "Uptrend":
                        buy_score += (
                            1 if daily_strength in ("Strong", "Moderate") else 0
                        )
                    elif daily_bias == "Downtrend":
                        sell_score += (
                            1 if daily_strength in ("Strong", "Moderate") else 0
                        )
                except Exception:
                    pass

            # ── News sentiment strength (weighted scoring) ────────────────────
            if use_news:
                try:
                    from news.sentiment import get_gold_news, get_sentiment_strength

                    _headlines = get_gold_news(5)
                    news_str = get_sentiment_strength(_headlines)
                    if news_str["sentiment"] == "BULLISH":
                        buy_score += 2 if news_str["strength"] == "STRONG" else 1
                    elif news_str["sentiment"] == "BEARISH":
                        sell_score += 2 if news_str["strength"] == "STRONG" else 1
                except Exception:
                    pass

            # ── Volume spike detection ────────────────────────────────────────
            if use_volume:
                try:
                    vol = df["Volume"].tail(20)
                    if len(vol) >= 20:
                        avg_vol = vol.iloc[:-1].mean()
                        latest_vol = float(vol.iloc[-1])
                        if avg_vol > 0 and latest_vol > avg_vol * 1.5:
                            if buy_score > sell_score:
                                buy_score += 1
                            elif sell_score > buy_score:
                                sell_score += 1
                except Exception:
                    pass

            # ── DXY + VIX macro indicators ───────────────────────────────────
            dxy_context = {}
            vix_context = {}
            if use_dxy_vix:
                try:
                    from data.fetch import get_macro_indicators

                    macro = get_macro_indicators()
                    dxy = macro.get("dxy", {})
                    if dxy:
                        if dxy["signal"] == "BEARISH_GOLD":
                            sell_score += 1
                        elif dxy["signal"] == "BULLISH_GOLD":
                            buy_score += 1
                        dxy_context = {
                            "value": dxy["value"],
                            "change_pct": dxy["change_pct"],
                            "signal": dxy["signal"],
                            "note": "DXY up = gold headwind. DXY down = gold tailwind.",
                        }
                    vix = macro.get("vix", {})
                    if vix:
                        if "BULLISH_GOLD" in vix["signal"]:
                            buy_score += 1
                        vix_context = {
                            "value": vix["value"],
                            "change_pct": vix["change_pct"],
                            "signal": vix["signal"],
                            "note": "VIX>20=fear rising=gold safe-haven demand. VIX<15=risk-on=gold neutral.",
                        }
                except Exception as e:
                    print(
                        f"[trading_agent.py] DXY/VIX fetch failed (non-critical): {e}"
                    )

            # Multi-timeframe: H1 context + confirmation filter
            h1_context = {}
            mtf_confirmed = True
            if use_h1_mtf:
                try:
                    from data.fetch import get_gold_price_intraday

                    df_h1 = get_gold_price_intraday(interval="1h", days=5)
                    if not df_h1.empty and len(df_h1) >= 15:
                        h1_rsi = calculate_rsi(df_h1, period=14)
                        h1_macd = calculate_macd(df_h1)
                        h1_trend = "BULLISH" if h1_macd["histogram"] > 0 else "BEARISH"
                        h1_rsi_sig = (
                            "OVERBOUGHT"
                            if h1_rsi > 70
                            else "OVERSOLD" if h1_rsi < 30 else "NEUTRAL"
                        )
                        if buy_score > sell_score and h1_rsi > 65:
                            mtf_confirmed = False
                        elif sell_score > buy_score and h1_rsi < 35:
                            mtf_confirmed = False
                        h1_context = {
                            "interval": "H1",
                            "bars": len(df_h1),
                            "rsi": round(h1_rsi, 2),
                            "rsi_signal": h1_rsi_sig,
                            "macd_histogram": h1_macd["histogram"],
                            "trend": h1_trend,
                            "mtf_confirmed": mtf_confirmed,
                            "note": (
                                "H1 CONFIRMS D1 signal"
                                if mtf_confirmed
                                else "H1 CONFLICTS with D1 - reduce conviction"
                            ),
                        }
                except Exception as e:
                    print(f"[trading_agent.py] H1 MTF fetch failed (non-critical): {e}")

            # Cap scores to 0-5 range before comparison
            buy_score = min(buy_score, 5)
            sell_score = min(sell_score, 5)

            result = {
                "note": "All values are pre-computed deterministically. Do NOT recalculate.",
                "timeframe": "D1 (primary)",
                "pre_scored_signals": {
                    "buy_score": f"{buy_score} / 5",
                    "sell_score": f"{sell_score} / 5",
                    "bias": (
                        "BUY"
                        if buy_score > sell_score
                        else "SELL" if sell_score > buy_score else "NEUTRAL"
                    ),
                    "daily_trend": daily_bias,
                    "trend_strength": daily_strength,
                    "note": "Scores are hints only — use your judgment. Pre-scored news sentiment uses keyword lexicon; use get_news for deep LLM evaluation.",
                },
                "rsi": {
                    "value": rsi,
                    "signal": rsi_signal,
                    "period": 14,
                    "interpretation": f"RSI={rsi:.1f} ({rsi_signal})",
                },
                "macd": {
                    "macd_line": macd["macd"],
                    "signal_line": macd["signal"],
                    "histogram": macd["histogram"],
                    "trend": macd_signal,
                    "params": "EMA12 - EMA26, Signal=EMA9",
                    "interpretation": f"Histogram={macd['histogram']:.4f} ({macd_signal})",
                },
                "bollinger_bands": {
                    "upper": bb["upper"],
                    "middle": bb["middle"],
                    "lower": bb["lower"],
                    "percent_b": bb["percent_b"],
                    "bandwidth": bb["bandwidth"],
                    "signal": bb["signal"],
                    "interpretation": f"%B={bb['percent_b']:.2f} ({bb['signal']})",
                },
            }
            if dxy_context:
                result["dxy_usd_index"] = dxy_context
            if vix_context:
                result["vix_fear_index"] = vix_context
            if h1_context:
                result["h1_intraday"] = h1_context
                result["mtf_note"] = (
                    "H1 and D1 aligned = stronger signal. "
                    "H1 and D1 diverging = wait for confirmation."
                )
            if daily_summary:
                result["daily_macro_context"] = daily_summary
            return json.dumps(result)

        # ── Tool: get_news ───────────────────────────────────────────────────
        elif tool_name == "get_news":
            _cfg = _tool_config or {}
            use_news = _cfg.get("use_news", True)
            if not use_news:
                return json.dumps(
                    {
                        "note": "News disabled during backtest to prevent data leakage.",
                        "headlines": [],
                        "overall_sentiment": {
                            "sentiment": "NEUTRAL",
                            "strength": "WEAK",
                        },
                    }
                )

            from news.sentiment import get_gold_news, get_sentiment_summary
            from knowledge.lightrag_store import insert_headlines, query_gold_context

            count = min(int(tool_input.get("count", 5)), 5)
            headlines = get_gold_news(count)
            sentiment = get_sentiment_summary(headlines)

            # Accumulate headlines in knowledge graph
            insert_headlines(headlines)

            # Query historical and domain context
            historical = query_gold_context(
                "What are the key macro drivers and historical patterns for gold price movements?"
            )

            # Structured news
            result = {
                "note": "Use these headlines to identify macro catalysts (The LLM Advantage)",
                "headlines": headlines,
                "count": len(headlines),
                "overall_sentiment": sentiment,
                "bullish_catalysts": [
                    "Fed rate cuts",
                    "Geopolitical tensions",
                    "Inflation surge",
                    "USD weakness",
                ],
                "bearish_catalysts": [
                    "Fed rate hikes",
                    "Strong USD",
                    "Risk-on rally",
                    "Crypto competition",
                ],
            }
            if historical and historical.strip():
                result["historical_context"] = historical
            return json.dumps(result)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})


# ─────────────────────────────────────────────────────────────
# Safety Bounds Validator
# ─────────────────────────────────────────────────────────────
def _validate_decision(decision: dict) -> dict:
    """
    Validate the agent's output against hard-coded safety constraints.

    "Once the LLM outputs a tool call, the execution layer validates it
     against hard-coded constraints before interacting with external systems."

    Safety checks:
        1. Decision must be BUY, SELL, or HOLD
        2. Confidence must be 0–100
        3. Low confidence (<40%) → auto-downgrade to HOLD
        4. Reasoning must be non-empty

    Args:
        decision (dict): Raw parsed JSON from the agent.

    Returns:
        dict: Validated and sanitized decision dict.
    """
    valid_decisions = {"BUY", "SELL", "HOLD"}
    raw_decision = str(decision.get("decision", "HOLD")).upper()

    # Safety check 1: Valid decision value
    if raw_decision not in valid_decisions:
        print(f"[trading_agent.py] Invalid decision '{raw_decision}' -> forcing HOLD")
        raw_decision = "HOLD"

    # Safety check 2: Confidence bounds
    confidence = int(decision.get("confidence", 50))
    confidence = max(0, min(100, confidence))

    # Safety check 3: Low confidence → HOLD
    if confidence < 40 and raw_decision != "HOLD":
        print(f"[trading_agent.py] Low confidence {confidence}% -> forcing HOLD")
        raw_decision = "HOLD"

    # Safety check 4: Non-empty reasoning
    reasoning = str(decision.get("reasoning", "No reasoning provided.")).strip()
    if not reasoning:
        reasoning = "No reasoning provided."

    return {
        "decision": raw_decision,
        "confidence": confidence,
        "reasoning": reasoning,
        "key_factors": list(decision.get("key_factors", [])),
        "risk_note": str(decision.get("risk_note", "")),
    }


# ─────────────────────────────────────────────────────────────
# JSON Parser with Retry
# ─────────────────────────────────────────────────────────────
def _parse_json_with_retry(text: str, attempt: int = 1) -> dict | None:
    """
    Parse JSON from the agent's response with fallback strategies.

    "JSON parsing failures: The LLM outputs malformed JSON.
     Solution: Use robust parsing with retry logic and error feedback."

    Strategy:
        1. Find the outermost { } block
        2. Try standard json.loads()
        3. On failure, strip common issues (trailing commas, etc.)

    Args:
        text (str): Raw text from the agent that should contain JSON.
        attempt (int): Attempt number (for logging).

    Returns:
        dict | None: Parsed dict or None if all attempts fail.
    """
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            print(f"[trading_agent.py] Parse attempt {attempt}: No JSON block found.")
            return None

        json_str = text[start:end]
        return json.loads(json_str)

    except json.JSONDecodeError as e:
        print(f"[trading_agent.py] Parse attempt {attempt} failed: {e}")

        # Retry: strip trailing commas before } or ] (common LLM mistake)
        try:
            import re

            cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
            return json.loads(cleaned)
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────
# Main Agent Function  (ReAct loop)
# ─────────────────────────────────────────────────────────────
def run_agent(
    quota_pressure: bool = False,
    failsafe_pressure: bool = False,
    open_positions: int = 0,
    config: dict | None = None,
) -> dict:
    """
    Run the gold trading ReAct agent.

    Implements the full ReAct trajectory:
        τ = (s₀, t₁, a₁, o₁, t₂, a₂, o₂, ..., aₙ, oₙ)

    Key design decisions:
        - temperature=0.0  : τ→0 for near-deterministic JSON
        - top_p=0.1        : Nucleus sampling p=0.1 for tool calling
        - max_iterations=8 : Hard loop guard (infinite loop prevention)
        - JSON retry logic  : robust parsing
        - Safety validation : execution router

    Returns:
        dict: {
            'decision'    : str,   # "BUY", "SELL", or "HOLD"
            'confidence'  : int,   # 0–100
            'reasoning'   : str,   # Explanation combining math + news
            'key_factors' : list,  # List of key factors considered
            'risk_note'   : str,   # Main risk to this call
            'raw_response': str,   # Full raw text from the agent
            'agent_trace' : list,  # Full ReAct trajectory log
        }
    """
    default_result = {
        "decision": "HOLD",
        "confidence": 0,
        "reasoning": "Analysis unavailable — API error or missing key.",
        "key_factors": [],
        "risk_note": "",
        "raw_response": "",
        "agent_trace": [],
    }

    # ── Choose your model here (uncomment the one you want to use) ──
    # ACTIVE_MODEL = "openai"
    ACTIVE_MODEL = "gemini"

    if ACTIVE_MODEL == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        client = OpenAI(api_key=api_key)
        model_name = "gpt-4o-mini"
    else:
        api_key = os.getenv(
            "GEMINI_API_KEY", ""
        ).strip()  # Gemini key stored as OPENAI_API_KEY in .env
        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        model_name = "gemini-2.5-flash-lite"

    if not api_key or api_key == "your_key_here":
        print(f"[trading_agent.py] No API key found for {ACTIVE_MODEL}.")
        default_result["reasoning"] = f"{ACTIVE_MODEL} API key not configured in .env."
        return default_result

    # ReAct trajectory log
    agent_trace = []

    try:

        # Initial messages with system prompt + user task
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Analyze the current gold (XAUUSD) market and provide a trading recommendation.\n\n"
                    "## YOUR TASK (ReAct loop)\n"
                    "1. Call get_price     → establish current market state (s₀)\n"
                    "2. Call get_indicators → get pre-computed math (RSI, MACD, BB)\n"
                    "3. Call get_news      → identify macro catalysts (your superpower)\n"
                    "4. Synthesize all data → output final JSON decision\n\n"
                    "Remember: If news contradicts math signals, "
                    "macro events usually dominate for Gold.\n\n"
                    "Respond ONLY with the JSON object specified in your system prompt."
                ),
            },
        ]

        state_note = (
            f"\n\n## YOUR PORTFOLIO STATE\n"
            f"Currently holding: {open_positions} / 1 positions.\n"
        )
        if open_positions >= 1:
            state_note += "CRITICAL: You are FULL. You CANNOT output 'BUY'. You must output 'SELL' or 'HOLD'.\n"
        else:
            state_note += "CRITICAL: You are EMPTY. You CANNOT output 'SELL'. You must output 'BUY' or 'HOLD'.\n"

        messages[0]["content"] += state_note

        if quota_pressure and open_positions == 0:
            quota_note = (
                "\n\nIMPORTANT — QUOTA PRESSURE: You are inside an active trading window "
                "that has not yet met its minimum trade quota. "
                "You must actively FIND a suitable entry NOW. DO NOT WAIT for perfect conditions. "
                "Look at the slightest directional micro-trend (e.g. MACD histogram slope, Bollinger Bands) "
                "and output 'BUY'. YOU ARE STRICTLY FORBIDDEN FROM OUTPUTTING 'HOLD'. "
                "Output BUY with at least 50% confidence. "
                "You MUST ignore the SPREAD RULE and the strict RSI 40-65 HOLD rule."
            )
            messages[0]["content"] += quota_note

        if failsafe_pressure:
            failsafe_note = (
                "\n\nCRITICAL FAILSAFE — WINDOW CLOSING: The minimum "
                "trade quota for this window has NOT been met. You MUST output BUY or SELL. "
                "Override constraint #4 for this window-closing situation only. "
                "HOLD is not acceptable under any circumstances. Pick the stronger directional "
                "signal from the available data right now. This is a hard competition requirement."
            )
            messages[0]["content"] += failsafe_note

        print("[trading_agent.py] Starting ReAct agent loop...")
        agent_trace.append("[AGENT STARTED] ReAct trajectory τ begins")

        # ── Hard max iterations guard ────────────────────────────
        max_iterations = 8
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            print(f"[trading_agent.py] Iteration {iteration}/{max_iterations}")

            response = client.chat.completions.create(
                model=model_name,
                max_tokens=1024,
                temperature=0,
                tools=TOOLS,
                tool_choice="auto",
                messages=messages,
            )

            # Track LLM cost
            try:
                from logger.cost_tracker import track_usage

                track_usage(response.usage, source="trading_agent")
            except Exception:
                pass

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # Add assistant response to message history
            messages.append(msg)

            # ── End turn: extract final decision ────────────────────────────
            if finish_reason == "stop":
                final_text = msg.content or ""

                print("[trading_agent.py] Agent finished. Parsing response...")
                agent_trace.append("[AGENT DECIDED] Final JSON response received")

                # JSON parse with retry
                parsed = _parse_json_with_retry(final_text, attempt=1)
                if parsed is None:
                    print("[trading_agent.py] JSON parse failed after retry.")
                    default_result["raw_response"] = final_text
                    default_result["agent_trace"] = agent_trace
                    return default_result

                # Safety bounds validation
                validated = _validate_decision(parsed)
                validated["raw_response"] = final_text
                validated["agent_trace"] = agent_trace
                return validated

            # ── Tool use: execute and feed back ──────────────
            elif finish_reason == "tool_calls":
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)
                    tool_id = tool_call.id

                    print(
                        f"[trading_agent.py] TOOL CALL: {tool_name} | input={tool_input}"
                    )

                    # ReAct: aₖ → environment → oₖ
                    result = _execute_tool(tool_name, tool_input, _tool_config=config)
                    result_preview = (
                        result[:150] + "..." if len(result) > 150 else result
                    )
                    print(f"[trading_agent.py] OBSERVATION: {result_preview}")

                    # Log to ReAct trace
                    agent_trace.append(
                        f"[ACTION] Tool={tool_name} | "
                        f"[OBSERVATION] {result_preview}"
                    )

                    # Feed tool result back into context
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result,
                        }
                    )

            else:
                print(f"[trading_agent.py] Unexpected finish_reason: {finish_reason}")
                agent_trace.append(f"[WARNING] Unexpected stop: {finish_reason}")
                break

        # ── Max iterations hit (infinite loop guard) ──────────────
        print("[trading_agent.py] Max iterations reached without final answer.")
        agent_trace.append("[FALLBACK] Max iterations reached → HOLD")
        default_result["agent_trace"] = agent_trace
        return default_result

    except Exception as e:
        print(f"[trading_agent.py] Unexpected error: {e}")
        default_result["reasoning"] = f"Agent error: {str(e)}"
        default_result["agent_trace"] = agent_trace
        return default_result


# ─────────────────────────────────────────────────────────────
# Standalone testing
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = run_agent()
    print("\n--- Agent Result (ReAct) ---")
    print(f"Decision    : {result['decision']}")
    print(f"Confidence  : {result['confidence']}%")
    print(f"Reasoning   : {result['reasoning']}")
    print(f"Key Factors : {result['key_factors']}")
    print(f"Risk Note   : {result['risk_note']}")
    print(f"\n--- ReAct Trace ---")
    for step in result.get("agent_trace", []):
        print(f"  {step}")
