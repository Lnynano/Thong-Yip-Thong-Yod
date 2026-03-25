"""
agent/claude_agent.py
Claude-powered ReAct gold trading agent using Anthropic tool calling.

Implements the exact architecture described in the course slides:

  Slide 7  — ReAct trajectory: τ = (s₀, t₁, a₁, o₁, t₂, a₂, o₂, ..., aₙ, oₙ)
  Slide 9  — Structured state representation (markdown tables, not free-form prose)
  Slide 10 — Progressive disclosure: global state first, then targeted details
  Slide 11 — Template-driven system prompt: ROLE / CONSTRAINTS / STATE / OUTPUT
  Slide 25 — System prompt with hard constraints (max drawdown 5%, position 10%)
  Slide 26 — Execution router with safety bounds validation
  Slide 31 — temperature=0 for consistent JSON tool calling (τ→0 = near-deterministic)
  Slide 33 — JSON retry logic, infinite loop guard, arithmetic hallucination prevention

Model: claude-sonnet-4-20250514
"""

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# System Prompt — Slide 25 template structure
# ROLE / CONSTRAINTS / INSTRUCTIONS / OUTPUT FORMAT
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """# ROLE
You are an institutional quantitative trading agent specializing in Gold (XAUUSD).
You combine mathematical technical indicators with macroeconomic news sentiment.
Your analysis is used by Thai retail investors, so you also consider Thai Baht pricing.

# CONSTRAINTS (HARD LIMITS — from Slide 25-26)
1. Maximum drawdown limit    : 5% of portfolio value per trade
2. Maximum position size     : 10% of capital per trade
3. Only issue BUY when macro sentiment ALIGNS with momentum indicators
4. Pre-computed indicators are authoritative — NEVER re-calculate math yourself
5. You must call all three tools (get_price, get_indicators, get_news) before deciding

# ANALYSIS PROCESS (ReAct loop — Slide 7)
Step 1 [OBSERVE s₀]: Market state is injected via tool results
Step 2 [THINK  t₁]:  Reason about what data you need
Step 3 [ACT    a₁]:  Call get_price → get_indicators → get_news (progressive disclosure)
Step 4 [OBSERVE o₁]: Review each tool result carefully
Step 5 [DECIDE    ]: Synthesize math + news → output final JSON

# THE LLM ADVANTAGE (Slide 24)
Traditional algorithms are great at math (RSI, MACD).
But Gold is heavily driven by Macroeconomic News (Fed rates, inflation, war).
You are the only system capable of reading a news headline, understanding its
geopolitical impact, and combining it with mathematical indicators.

Example (Slide 24): If RSI=75 (overbought) BUT news says "Fed cuts rates by 50bps"
→ Override the overbought signal and BUY, because rate cuts are massively bullish for Gold.

# DECISION CRITERIA
- BUY  : RSI < 40 AND/OR MACD histogram positive AND/OR bullish macro news
         Confidence > 60% required
- SELL : RSI > 65 AND/OR MACD histogram negative AND/OR bearish macro news
         Confidence > 60% required
- HOLD : Mixed signals, RSI 40-65, contradicting indicators, low news conviction

# OUTPUT FORMAT (Slide 11 — machine-readable JSON only)
After calling all tools, respond with ONLY this JSON (no other text):
{
  "decision"    : "BUY" | "SELL" | "HOLD",
  "confidence"  : <integer 1-100>,
  "reasoning"   : "<2-4 sentence explanation combining math + news>",
  "key_factors" : ["<factor1>", "<factor2>", "<factor3>"],
  "risk_note"   : "<one sentence on the main risk to this call>"
}"""


# ─────────────────────────────────────────────────────────────
# Tool Definitions — Slide 13 (function calling interface contract)
# ─────────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "get_price",
        "description": (
            "Retrieves the current XAUUSD (gold futures) price in USD per troy ounce "
            "and a recent OHLCV summary table. Call this FIRST to establish market context. "
            "Returns structured markdown-style data per Slide 9."
        ),
        "input_schema": {
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
    {
        "name": "get_indicators",
        "description": (
            "Returns pre-computed technical indicators (RSI, MACD, Bollinger Bands). "
            "All values are deterministically calculated from 90 days of price data. "
            "Per Slide 23: NEVER re-calculate these yourself — use these values as authoritative. "
            "RSI > 70 = overbought, RSI < 30 = oversold. "
            "Positive MACD histogram = bullish momentum."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_news",
        "description": (
            "Fetches the 5 most recent gold market news headlines with overall sentiment. "
            "THIS IS YOUR SUPERPOWER (Slide 24): combine this news with mathematical "
            "indicators. A single macro event (Fed rate cut, war escalation) can override "
            "all technical signals. Always check news before deciding."
        ),
        "input_schema": {
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
]


# ─────────────────────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────────────────────
def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a tool call and return a structured JSON string result.

    Per Slide 23: All numerical calculations happen here (deterministically),
    never inside the LLM. The LLM only reasons about pre-computed values.

    Per Slide 9: Returns structured markdown-table-style state for the LLM.

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
            from data.fetch import get_gold_price
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

            # Structured state per Slide 9 (markdown-friendly)
            result = {
                "asset": "XAUUSD (Gold Futures)",
                "current_price_usd": round(current_price, 2),
                "period_days": len(recent),
                "ohlcv_summary": {
                    "open" : round(float(recent["Open"].iloc[0]), 2),
                    "high" : round(float(recent["High"].max()), 2),
                    "low"  : round(float(recent["Low"].min()), 2),
                    "close": round(float(recent["Close"].iloc[-1]), 2),
                    "avg_volume": int(recent["Volume"].mean()),
                },
                "price_change_pct": price_change_pct,
                "trend": "UP" if price_change_pct > 0 else "DOWN",
            }
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

            # Structured state per Slide 9 & 23
            result = {
                "note": "All values are pre-computed deterministically. Do NOT recalculate.",
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
            return json.dumps(result)

        # ── Tool: get_news ───────────────────────────────────────────────────
        elif tool_name == "get_news":
            from news.sentiment import get_gold_news, get_sentiment_summary
            count = min(int(tool_input.get("count", 5)), 5)
            headlines = get_gold_news(count)
            sentiment = get_sentiment_summary(headlines)

            # Structured news per Slide 16 (Day in Life Part 2)
            result = {
                "note": "Use these headlines to identify macro catalysts (Slide 24: The LLM Advantage)",
                "headlines": headlines,
                "count": len(headlines),
                "overall_sentiment": sentiment,
                "bullish_catalysts": ["Fed rate cuts", "Geopolitical tensions", "Inflation surge", "USD weakness"],
                "bearish_catalysts": ["Fed rate hikes", "Strong USD", "Risk-on rally", "Crypto competition"],
            }
            return json.dumps(result)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})


# ─────────────────────────────────────────────────────────────
# Safety Bounds Validator  (Slide 26)
# ─────────────────────────────────────────────────────────────
def _validate_decision(decision: dict) -> dict:
    """
    Validate the agent's output against hard-coded safety constraints.

    From Slide 26 (Execution Engine and Safety Bounds):
        "Once the LLM outputs a tool call, the execution layer validates it
         against hard-coded constraints before interacting with external systems."

    Safety checks:
        1. Decision must be BUY, SELL, or HOLD
        2. Confidence must be 0–100
        3. Low confidence (<40%) → auto-downgrade to HOLD
        4. Reasoning must be non-empty

    Args:
        decision (dict): Raw parsed JSON from Claude.

    Returns:
        dict: Validated and sanitized decision dict.
    """
    valid_decisions = {"BUY", "SELL", "HOLD"}
    raw_decision = str(decision.get("decision", "HOLD")).upper()

    # Safety check 1: Valid decision value
    if raw_decision not in valid_decisions:
        print(f"[claude_agent.py] Invalid decision '{raw_decision}' → forcing HOLD")
        raw_decision = "HOLD"

    # Safety check 2: Confidence bounds
    confidence = int(decision.get("confidence", 50))
    confidence = max(0, min(100, confidence))

    # Safety check 3: Low confidence → HOLD (Slide 26 principle)
    if confidence < 40 and raw_decision != "HOLD":
        print(f"[claude_agent.py] Low confidence {confidence}% → forcing HOLD")
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
# JSON Parser with Retry  (Slide 33)
# ─────────────────────────────────────────────────────────────
def _parse_json_with_retry(text: str, attempt: int = 1) -> dict | None:
    """
    Parse JSON from Claude's response with fallback strategies.

    From Slide 33 (Common Pitfalls):
        "JSON parsing failures: The LLM outputs malformed JSON.
         Solution: Use robust parsing with retry logic and error feedback."

    Strategy:
        1. Find the outermost { } block
        2. Try standard json.loads()
        3. On failure, strip common issues (trailing commas, etc.)

    Args:
        text (str): Raw text from Claude that should contain JSON.
        attempt (int): Attempt number (for logging).

    Returns:
        dict | None: Parsed dict or None if all attempts fail.
    """
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            print(f"[claude_agent.py] Parse attempt {attempt}: No JSON block found.")
            return None

        json_str = text[start:end]
        return json.loads(json_str)

    except json.JSONDecodeError as e:
        print(f"[claude_agent.py] Parse attempt {attempt} failed: {e}")

        # Retry: strip trailing commas before } or ] (common LLM mistake)
        try:
            import re
            cleaned = re.sub(r',\s*([}\]])', r'\1', json_str)
            return json.loads(cleaned)
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────
# Main Agent Function  (ReAct loop — Slide 7)
# ─────────────────────────────────────────────────────────────
def run_agent() -> dict:
    """
    Run the Claude gold trading ReAct agent.

    Implements the full ReAct trajectory from Slide 7:
        τ = (s₀, t₁, a₁, o₁, t₂, a₂, o₂, ..., aₙ, oₙ)

    Key design decisions from slides:
        - temperature=0.0  : τ→0 for near-deterministic JSON (Slide 31)
        - top_p=0.1        : Nucleus sampling p=0.1 for tool calling (Slide 31)
        - max_iterations=8 : Hard loop guard (Slide 33: infinite loop prevention)
        - JSON retry logic  : Slide 33: robust parsing
        - Safety validation : Slide 26: execution router

    Returns:
        dict: {
            'decision'    : str,   # "BUY", "SELL", or "HOLD"
            'confidence'  : int,   # 0–100
            'reasoning'   : str,   # Explanation combining math + news
            'key_factors' : list,  # List of key factors considered
            'risk_note'   : str,   # Main risk to this call
            'raw_response': str,   # Full raw text from Claude
            'agent_trace' : list,  # Full ReAct trajectory log (Slide 32)
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

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        print("[claude_agent.py] No ANTHROPIC_API_KEY found.")
        default_result["reasoning"] = "ANTHROPIC_API_KEY not configured. Set it in your .env file."
        return default_result

    # ReAct trajectory log (Slide 32: Live Reasoning Traces)
    agent_trace = []

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Initial user message with structured state per Slide 10
        # (Progressive disclosure: global view first, then targeted detail via tools)
        messages = [
            {
                "role": "user",
                "content": (
                    "Analyze the current gold (XAUUSD) market and provide a trading recommendation.\n\n"
                    "## YOUR TASK (ReAct loop — Slide 7)\n"
                    "1. Call get_price     → establish current market state (s₀)\n"
                    "2. Call get_indicators → get pre-computed math (RSI, MACD, BB)\n"
                    "3. Call get_news      → identify macro catalysts (your superpower)\n"
                    "4. Synthesize all data → output final JSON decision\n\n"
                    "Remember (Slide 24): If news contradicts math signals, "
                    "macro events usually dominate for Gold.\n\n"
                    "Respond ONLY with the JSON object specified in your system prompt."
                ),
            }
        ]

        print("[claude_agent.py] Starting ReAct agent loop (Slide 7)...")
        agent_trace.append("[AGENT STARTED] ReAct trajectory τ begins")

        # ── Hard max iterations guard (Slide 33) ────────────────────────────
        max_iterations = 8
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            print(f"[claude_agent.py] Iteration {iteration}/{max_iterations}")

            # temperature=0 and top_p=0.1 for consistent JSON (Slide 31)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0,          # τ→0: near-deterministic (Slide 31)
                top_p=0.1,              # Nucleus p=0.1: limit to high-prob tokens (Slide 31)
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            # Add assistant response to message history
            messages.append({"role": "assistant", "content": response.content})

            # ── End turn: extract final decision ────────────────────────────
            if response.stop_reason == "end_turn":
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text

                print("[claude_agent.py] Agent finished. Parsing response...")
                agent_trace.append("[AGENT DECIDED] Final JSON response received")

                # JSON parse with retry (Slide 33)
                parsed = _parse_json_with_retry(final_text, attempt=1)
                if parsed is None:
                    print("[claude_agent.py] JSON parse failed after retry.")
                    default_result["raw_response"] = final_text
                    default_result["agent_trace"] = agent_trace
                    return default_result

                # Safety bounds validation (Slide 26)
                validated = _validate_decision(parsed)
                validated["raw_response"] = final_text
                validated["agent_trace"] = agent_trace
                return validated

            # ── Tool use: execute and feed back (Slides 8, 16) ──────────────
            elif response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        tool_name  = block.name
                        tool_input = block.input
                        tool_id    = block.id

                        print(f"[claude_agent.py] TOOL CALL: {tool_name} | input={tool_input}")

                        # Slide 7: aₖ → environment → oₖ
                        result = _execute_tool(tool_name, tool_input)
                        result_preview = result[:150] + "..." if len(result) > 150 else result
                        print(f"[claude_agent.py] OBSERVATION: {result_preview}")

                        # Log to ReAct trace (Slide 32: Live Reasoning Traces)
                        agent_trace.append(
                            f"[ACTION] Tool={tool_name} | "
                            f"[OBSERVATION] {result_preview}"
                        )

                        tool_results.append({
                            "type"       : "tool_result",
                            "tool_use_id": tool_id,
                            "content"    : result,
                        })

                # Feed observations back into context (Slide 7: oₖ → cₖ₊₁)
                messages.append({"role": "user", "content": tool_results})

            else:
                print(f"[claude_agent.py] Unexpected stop_reason: {response.stop_reason}")
                agent_trace.append(f"[WARNING] Unexpected stop: {response.stop_reason}")
                break

        # ── Max iterations hit (Slide 33: infinite loop guard) ──────────────
        print("[claude_agent.py] Max iterations reached without final answer.")
        agent_trace.append("[FALLBACK] Max iterations reached → HOLD")
        default_result["agent_trace"] = agent_trace
        return default_result

    except anthropic.AuthenticationError:
        print("[claude_agent.py] Invalid ANTHROPIC_API_KEY.")
        default_result["reasoning"] = "Invalid API key — check your ANTHROPIC_API_KEY in .env."
        default_result["agent_trace"] = agent_trace
        return default_result

    except anthropic.RateLimitError:
        print("[claude_agent.py] Rate limit exceeded.")
        default_result["reasoning"] = "API rate limit exceeded — please wait and retry."
        default_result["agent_trace"] = agent_trace
        return default_result

    except Exception as e:
        print(f"[claude_agent.py] Unexpected error: {e}")
        default_result["reasoning"] = f"Agent error: {str(e)}"
        default_result["agent_trace"] = agent_trace
        return default_result


# ─────────────────────────────────────────────────────────────
# Standalone testing
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = run_agent()
    print("\n--- Agent Result (ReAct Slide 7) ---")
    print(f"Decision    : {result['decision']}")
    print(f"Confidence  : {result['confidence']}%")
    print(f"Reasoning   : {result['reasoning']}")
    print(f"Key Factors : {result['key_factors']}")
    print(f"Risk Note   : {result['risk_note']}")
    print(f"\n--- ReAct Trace (Slide 32: Live Reasoning Traces) ---")
    for step in result.get("agent_trace", []):
        print(f"  {step}")
