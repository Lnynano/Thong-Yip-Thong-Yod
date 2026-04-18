"""
agent/trading_agent.py
GPT-4o-mini-powered ReAct gold trading agent using OpenAI tool calling.

Architecture:
  - ReAct trajectory: τ = (s₀, t₁, a₁, o₁, t₂, a₂, o₂, ..., aₙ, oₙ)
  - Structured state representation (markdown tables, not free-form prose)
  - Progressive disclosure: global state first, then targeted details
  - Template-driven system prompt: ROLE / CONSTRAINTS / STATE / OUTPUT
  - System prompt with hard constraints (max drawdown 5%, position 10%)
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
You are an institutional quantitative trading agent specializing in Gold (XAUUSD).
You combine mathematical technical indicators with macroeconomic news sentiment.
Your analysis is used by Thai retail investors, so you also consider Thai Baht pricing.

# CONSTRAINTS (HARD LIMITS)
1. Maximum drawdown limit    : 5% of portfolio value per trade
2. Maximum position size     : 10% of capital per trade
3. Only issue BUY when macro sentiment ALIGNS with momentum indicators
4. Pre-computed indicators are authoritative — NEVER re-calculate math yourself
5. You must call all three tools (get_price, get_indicators, get_news) before deciding

# ANALYSIS PROCESS (ReAct loop)
Step 1 [OBSERVE s₀]: Market state is injected via tool results
Step 2 [THINK  t₁]:  Reason about what data you need
Step 3 [ACT    a₁]:  Call get_price → get_indicators → get_news (progressive disclosure)
Step 4 [OBSERVE o₁]: Review each tool result carefully
Step 5 [DECIDE    ]: Synthesize math + news → output final JSON

# THE LLM ADVANTAGE
Traditional algorithms are great at math (RSI, MACD).
But Gold is heavily driven by Macroeconomic News (Fed rates, inflation, war).
You are the only system capable of reading a news headline, understanding its
geopolitical impact, and combining it with mathematical indicators.

Example: If RSI=75 (overbought) BUT news says "Fed cuts rates by 50bps"
→ Override the overbought signal and BUY, because rate cuts are massively bullish for Gold.

# MACRO CONTEXT (DXY + VIX)
get_indicators also returns DXY and VIX — use them:
- DXY (US Dollar Index): Gold has INVERSE correlation with USD.
  DXY rising → dollar strong → gold headwind (bearish)
  DXY falling → dollar weak → gold tailwind (bullish)
- VIX (Fear Index): Gold is a safe-haven asset.
  VIX > 20 → fear rising → gold safe-haven demand rises (bullish)
  VIX > 30 → high fear   → very bullish for gold
  VIX < 15 → complacency → reduced safe-haven demand (neutral/bearish)

# DECISION CRITERIA
- BUY  : RSI < 40 AND/OR MACD histogram positive AND/OR bullish macro news
         Confidence >= 65% required
- SELL : RSI > 65 AND/OR MACD histogram negative AND/OR bearish macro news
         Confidence >= 65% required
- HOLD : Mixed signals, RSI 40-65, contradicting indicators, low news conviction

# OUTPUT FORMAT (machine-readable JSON only)
After calling all tools, respond with ONLY this JSON (no other text):
{
  "decision"    : "BUY" | "SELL" | "HOLD",
  "confidence"  : <integer 1-100>,
  "reasoning"   : "<2-4 sentence explanation combining math + news>",
  "key_factors" : ["<factor1>", "<factor2>", "<factor3>"],
  "risk_note"   : "<one sentence on the main risk to this call>"
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
def _execute_tool(tool_name: str, tool_input: dict) -> str:
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
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
                / recent["Close"].iloc[0] * 100, 2
            )

            # HSH live price is the authoritative current price (96.5% Thai gold)
            result = {"asset": "Thai Gold 96.5% / XAUUSD"}
            try:
                hsh = get_hsh_price()
                if hsh:
                    result["current_price_source"]   = "HSH_LIVE_96.5pct"
                    result["current_price_thb_sell"] = hsh["sell"]
                    result["current_price_thb_buy"]  = hsh["buy"]
                    result["spread_thb"]             = hsh["spread"]
                    result["note"] = "sell_thb = price you PAY to BUY. buy_thb = price you RECEIVE when SELLING."
                else:
                    result["current_price_source"] = "yfinance_futures"
                    result["current_price_usd"]    = round(current_price, 2)
            except Exception:
                result["current_price_source"] = "yfinance_futures"
                result["current_price_usd"]    = round(current_price, 2)

            result["historical_usd_close"] = round(current_price, 2)
            result["period_days"]          = len(recent)
            result["ohlcv_summary"] = {
                "open" : round(float(recent["Open"].iloc[0]), 2),
                "high" : round(float(recent["High"].max()), 2),
                "low"  : round(float(recent["Low"].min()), 2),
                "close": round(float(recent["Close"].iloc[-1]), 2),
                "avg_volume": int(recent["Volume"].mean()),
            }
            result["price_change_pct"] = price_change_pct
            result["trend"]            = "UP" if price_change_pct > 0 else "DOWN"

            return json.dumps(result)

        # ── Tool: get_indicators ─────────────────────────────────────────────
        elif tool_name == "get_indicators":
            from data.fetch import get_gold_price
            from indicators.tech import calculate_rsi, calculate_macd, calculate_bollinger_bands
            df = get_gold_price()
            if df.empty:
                return json.dumps({"error": "Could not calculate indicators."})

            rsi  = calculate_rsi(df)
            macd = calculate_macd(df)
            bb   = calculate_bollinger_bands(df)

            rsi_signal  = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
            macd_signal = "BULLISH" if macd["histogram"] > 0 else "BEARISH"

            # ── BUY/SELL Score (0-5 each) ─────────────────────────────────────
            # Pre-score signals so the agent has quantified hints, reduces hallucination
            buy_score  = 0
            sell_score = 0

            # RSI
            if rsi < 30:   buy_score  += 2   # oversold = strong buy
            elif rsi < 45: buy_score  += 1
            if rsi > 70:   sell_score += 2   # overbought = strong sell
            elif rsi > 60: sell_score += 1

            # MACD histogram
            if macd["histogram"] > 0:  buy_score  += 1
            else:                      sell_score += 1

            # Bollinger Bands %B
            if bb["percent_b"] < 0.2:  buy_score  += 1   # near lower band
            elif bb["percent_b"] > 0.8: sell_score += 1  # near upper band

            # MACD crossover (macd line vs signal line)
            if macd["macd"] > macd["signal"]:  buy_score  += 1
            else:                               sell_score += 1

            # Daily market bias (cached — free, runs once/day)
            daily_bias = "Sideways"
            daily_strength = "Weak"
            try:
                from agent.daily_market_agent import get_daily_market
                dm = get_daily_market()
                daily_bias     = dm.get("daily_trend", "Sideways")
                daily_strength = dm.get("trend_strength", "Weak")
                daily_summary  = dm.get("daily_summary", "")
                if daily_bias == "Uptrend":
                    buy_score  += 1 if daily_strength in ("Strong", "Moderate") else 0
                elif daily_bias == "Downtrend":
                    sell_score += 1 if daily_strength in ("Strong", "Moderate") else 0
            except Exception:
                daily_summary = ""

            # ── News sentiment strength (weighted scoring) ────────────────────
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
            try:
                vol = df["Volume"].tail(20)
                if len(vol) >= 20:
                    avg_vol = vol.iloc[:-1].mean()
                    latest_vol = float(vol.iloc[-1])
                    if avg_vol > 0 and latest_vol > avg_vol * 1.5:
                        # Volume spike = something big happening, boost dominant signal
                        if buy_score > sell_score:
                            buy_score += 1
                        elif sell_score > buy_score:
                            sell_score += 1
            except Exception:
                pass

            # ── DXY + VIX macro indicators ───────────────────────────────────
            dxy_context = {}
            vix_context = {}
            try:
                from data.fetch import get_macro_indicators
                macro = get_macro_indicators()

                dxy = macro.get("dxy", {})
                if dxy:
                    if dxy["signal"] == "BEARISH_GOLD":
                        sell_score += 1
                    elif dxy["signal"] == "BULLISH_GOLD":
                        buy_score  += 1
                    dxy_context = {
                        "value"     : dxy["value"],
                        "change_pct": dxy["change_pct"],
                        "signal"    : dxy["signal"],
                        "note"      : "DXY up = gold headwind. DXY down = gold tailwind.",
                    }

                vix = macro.get("vix", {})
                if vix:
                    if "BULLISH_GOLD" in vix["signal"]:
                        buy_score += 1
                    vix_context = {
                        "value"     : vix["value"],
                        "change_pct": vix["change_pct"],
                        "signal"    : vix["signal"],
                        "note"      : "VIX>20=fear rising=gold safe-haven demand. VIX<15=risk-on=gold neutral.",
                    }
            except Exception as e:
                print(f"[trading_agent.py] DXY/VIX fetch failed (non-critical): {e}")

            # Multi-timeframe: H1 context + confirmation filter
            h1_context = {}
            mtf_confirmed = True   # assume confirmed if H1 unavailable
            try:
                from data.fetch import get_gold_price_intraday
                df_h1 = get_gold_price_intraday(interval="1h", days=5)
                if not df_h1.empty and len(df_h1) >= 15:
                    h1_rsi  = calculate_rsi(df_h1, period=14)
                    h1_macd = calculate_macd(df_h1)
                    h1_trend = "BULLISH" if h1_macd["histogram"] > 0 else "BEARISH"
                    h1_rsi_sig = ("OVERBOUGHT" if h1_rsi > 70
                                  else "OVERSOLD" if h1_rsi < 30
                                  else "NEUTRAL")

                    # MTF confirmation: D1 and H1 must agree
                    # If D1 says buy (buy_score > sell_score) but H1 RSI is overbought -> conflict
                    # If D1 says sell (sell_score > buy_score) but H1 RSI is oversold -> conflict
                    if buy_score > sell_score and h1_rsi > 65:
                        mtf_confirmed = False   # D1 bullish but H1 already stretched
                    elif sell_score > buy_score and h1_rsi < 35:
                        mtf_confirmed = False   # D1 bearish but H1 already oversold

                    h1_context = {
                        "interval": "H1",
                        "bars": len(df_h1),
                        "rsi": round(h1_rsi, 2),
                        "rsi_signal": h1_rsi_sig,
                        "macd_histogram": h1_macd["histogram"],
                        "trend": h1_trend,
                        "mtf_confirmed": mtf_confirmed,
                        "note": ("H1 CONFIRMS D1 signal" if mtf_confirmed
                                 else "H1 CONFLICTS with D1 - reduce conviction"),
                    }
            except Exception as e:
                print(f"[trading_agent.py] H1 MTF fetch failed (non-critical): {e}")

            # Cap scores to 0-5 range before comparison
            buy_score  = min(buy_score, 5)
            sell_score = min(sell_score, 5)

            result = {
                "note": "All values are pre-computed deterministically. Do NOT recalculate.",
                "timeframe": "D1 (primary)",
                "pre_scored_signals": {
                    "buy_score":       f"{buy_score} / 5",
                    "sell_score":      f"{sell_score} / 5",
                    "bias":            "BUY" if buy_score > sell_score else "SELL" if sell_score > buy_score else "NEUTRAL",
                    "daily_trend":     daily_bias,
                    "trend_strength":  daily_strength,
                    "note": "Scores are hints only — use your judgment. News can override math.",
                },
                "rsi": {
                    "value"  : rsi,
                    "signal" : rsi_signal,
                    "period" : 14,
                    "interpretation": f"RSI={rsi:.1f} ({rsi_signal})",
                },
                "macd": {
                    "macd_line" : macd["macd"],
                    "signal_line": macd["signal"],
                    "histogram" : macd["histogram"],
                    "trend"     : macd_signal,
                    "params"    : "EMA12 - EMA26, Signal=EMA9",
                    "interpretation": f"Histogram={macd['histogram']:.4f} ({macd_signal})",
                },
                "bollinger_bands": {
                    "upper"     : bb["upper"],
                    "middle"    : bb["middle"],
                    "lower"     : bb["lower"],
                    "percent_b" : bb["percent_b"],
                    "bandwidth" : bb["bandwidth"],
                    "signal"    : bb["signal"],
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
                "bullish_catalysts": ["Fed rate cuts", "Geopolitical tensions", "Inflation surge", "USD weakness"],
                "bearish_catalysts": ["Fed rate hikes", "Strong USD", "Risk-on rally", "Crypto competition"],
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
        "decision"   : raw_decision,
        "confidence" : confidence,
        "reasoning"  : reasoning,
        "key_factors": list(decision.get("key_factors", [])),
        "risk_note"  : str(decision.get("risk_note", "")),
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
            cleaned = re.sub(r',\s*([}\]])', r'\1', json_str)
            return json.loads(cleaned)
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────
# Main Agent Function  (ReAct loop)
# ─────────────────────────────────────────────────────────────
def run_agent(quota_pressure: bool = False, failsafe_pressure: bool = False) -> dict:
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
        "decision"    : "HOLD",
        "confidence"  : 0,
        "reasoning"   : "Analysis unavailable — API error or missing key.",
        "key_factors" : [],
        "risk_note"   : "",
        "raw_response": "",
        "agent_trace" : [],
    }

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        print("[trading_agent.py] No OPENAI_API_KEY found.")
        default_result["reasoning"] = "OPENAI_API_KEY not configured. Set it in your .env file."
        return default_result

    # ReAct trajectory log
    agent_trace = []

    try:
        client = OpenAI(api_key=api_key)

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

        if quota_pressure:
            quota_note = (
                "\n\nIMPORTANT — QUOTA PRESSURE: You are inside an active trading window "
                "that has not yet met its minimum trade quota. If your analysis shows ANY "
                "directional bias (even moderate), output BUY or SELL with at least 50% "
                "confidence instead of HOLD. Meeting the window quota is a competition requirement."
            )
            messages[0]["content"] += quota_note

        if failsafe_pressure:
            failsafe_note = (
                "\n\nCRITICAL FAILSAFE — WINDOW CLOSING IN UNDER 10 MINUTES: The minimum "
                "trade quota for this window has NOT been met. You MUST output BUY or SELL. "
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
                model="gpt-4o-mini",
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
                    tool_name  = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)
                    tool_id    = tool_call.id

                    print(f"[trading_agent.py] TOOL CALL: {tool_name} | input={tool_input}")

                    # ReAct: aₖ → environment → oₖ
                    result = _execute_tool(tool_name, tool_input)
                    result_preview = result[:150] + "..." if len(result) > 150 else result
                    print(f"[trading_agent.py] OBSERVATION: {result_preview}")

                    # Log to ReAct trace
                    agent_trace.append(
                        f"[ACTION] Tool={tool_name} | "
                        f"[OBSERVATION] {result_preview}"
                    )

                    # Feed tool result back into context
                    messages.append({
                        "role"        : "tool",
                        "tool_call_id": tool_id,
                        "content"     : result,
                    })

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
