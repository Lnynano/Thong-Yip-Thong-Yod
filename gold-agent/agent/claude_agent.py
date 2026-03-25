"""
agent/claude_agent.py
Claude-powered ReAct gold trading agent using Anthropic tool calling.

The agent:
  1. Thinks (ReAct reasoning loop)
  2. Calls tools: get_price, get_indicators, get_news
  3. Observes results
  4. Decides: BUY / SELL / HOLD with confidence % and reasoning

Model: claude-sonnet-4-20250514 (as specified in project requirements)
"""

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

# --- System prompt: Gold trading expert persona ---
SYSTEM_PROMPT = """You are a professional gold trading analyst with 20 years of experience
in commodity markets and technical analysis. Your role is to analyze gold (XAUUSD) price data
and provide actionable trading recommendations for Thai retail investors.

You have access to the following tools:
- get_price: Retrieve the current gold price and recent OHLCV data summary
- get_indicators: Get RSI and MACD technical indicators
- get_news: Fetch recent gold market news headlines

Your analysis process (ReAct loop):
1. THINK: Consider what information you need
2. ACT: Call the appropriate tool(s)
3. OBSERVE: Review the data returned
4. DECIDE: Based on all data, provide your recommendation

Your final response MUST be a JSON object with exactly these fields:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": <integer 0-100>,
  "reasoning": "<detailed explanation in 2-4 sentences>",
  "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
}

Decision criteria:
- BUY: RSI < 40, MACD histogram positive, bullish news sentiment, price near support
- SELL: RSI > 65, MACD histogram negative, bearish news, price near resistance
- HOLD: Mixed signals, RSI 40-65, uncertain momentum

Always consider both technical and fundamental (news) factors.
Be conservative — capital preservation is paramount for retail investors."""

# --- Tool definitions for Claude ---
TOOLS = [
    {
        "name": "get_price",
        "description": (
            "Retrieves the current XAUUSD (gold) price in USD per troy ounce "
            "along with a 5-day summary of recent OHLCV (Open, High, Low, Close, Volume) data. "
            "Use this first to establish the current market context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "How many recent days to summarize (default: '5d')",
                    "enum": ["1d", "5d", "10d", "30d"],
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_indicators",
        "description": (
            "Calculates RSI (14-period) and MACD (12,26,9) technical indicators "
            "from the last 90 days of gold price data. "
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
            "Fetches the 5 most recent gold market news headlines. "
            "Use this to gauge fundamental sentiment and market-moving events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of headlines to retrieve (1-5)",
                }
            },
            "required": [],
        },
    },
]


def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a tool call and return the result as a JSON string.

    This function imports from sibling modules to avoid circular imports.

    Args:
        tool_name (str): Name of the tool to execute.
        tool_input (dict): Input parameters for the tool.

    Returns:
        str: JSON-encoded result string.
    """
    try:
        import sys
        import os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

        if tool_name == "get_price":
            from data.fetch import get_gold_price
            df = get_gold_price()
            if df.empty:
                return json.dumps({"error": "Could not fetch gold price data."})

            period_map = {"1d": 1, "5d": 5, "10d": 10, "30d": 30}
            days = period_map.get(tool_input.get("period", "5d"), 5)
            recent = df.tail(days)

            result = {
                "current_price_usd": round(float(df["Close"].iloc[-1]), 2),
                "period_summary": {
                    "days": len(recent),
                    "open": round(float(recent["Open"].iloc[0]), 2),
                    "high": round(float(recent["High"].max()), 2),
                    "low": round(float(recent["Low"].min()), 2),
                    "close": round(float(recent["Close"].iloc[-1]), 2),
                    "avg_volume": int(recent["Volume"].mean()),
                    "price_change_pct": round(
                        (recent["Close"].iloc[-1] - recent["Close"].iloc[0])
                        / recent["Close"].iloc[0] * 100, 2
                    ),
                },
            }
            return json.dumps(result)

        elif tool_name == "get_indicators":
            from data.fetch import get_gold_price
            from indicators.tech import calculate_rsi, calculate_macd
            df = get_gold_price()
            if df.empty:
                return json.dumps({"error": "Could not calculate indicators."})

            rsi = calculate_rsi(df)
            macd = calculate_macd(df)

            rsi_signal = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
            macd_trend = "BULLISH" if macd["histogram"] > 0 else "BEARISH"

            result = {
                "rsi": {"value": rsi, "signal": rsi_signal, "period": 14},
                "macd": {
                    "macd_line": macd["macd"],
                    "signal_line": macd["signal"],
                    "histogram": macd["histogram"],
                    "trend": macd_trend,
                    "params": "12,26,9",
                },
            }
            return json.dumps(result)

        elif tool_name == "get_news":
            from news.sentiment import get_gold_news, get_sentiment_summary
            count = min(int(tool_input.get("count", 5)), 5)
            headlines = get_gold_news(count)
            sentiment = get_sentiment_summary(headlines)
            result = {
                "headlines": headlines,
                "count": len(headlines),
                "overall_sentiment": sentiment,
            }
            return json.dumps(result)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})


def run_agent() -> dict:
    """
    Run the Claude gold trading ReAct agent.

    Uses tool calling to gather price, indicators, and news data,
    then produces a BUY/SELL/HOLD recommendation with confidence and reasoning.

    Returns:
        dict: {
            'decision'   : str,   # "BUY", "SELL", or "HOLD"
            'confidence' : int,   # 0–100
            'reasoning'  : str,   # Explanation text
            'key_factors': list,  # List of key factors considered
            'raw_response': str,  # Full raw text from Claude
        }
        Returns a safe default dict on failure.
    """
    default_result = {
        "decision": "HOLD",
        "confidence": 0,
        "reasoning": "Analysis unavailable — API error or missing key.",
        "key_factors": [],
        "raw_response": "",
    }

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        print("[claude_agent.py] No ANTHROPIC_API_KEY found.")
        default_result["reasoning"] = "ANTHROPIC_API_KEY not configured."
        return default_result

    try:
        client = anthropic.Anthropic(api_key=api_key)

        messages = [
            {
                "role": "user",
                "content": (
                    "Please analyze the current gold market and provide a trading recommendation. "
                    "Use all available tools to gather price data, technical indicators, and news. "
                    "Respond ONLY with a valid JSON object as specified in your instructions."
                ),
            }
        ]

        print("[claude_agent.py] Starting ReAct agent loop...")
        max_iterations = 10
        iteration = 0

        # ReAct loop: think → act → observe → decide
        while iteration < max_iterations:
            iteration += 1
            print(f"[claude_agent.py] Iteration {iteration}/{max_iterations}")

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            # Add assistant response to message history
            messages.append({"role": "assistant", "content": response.content})

            # If Claude is done (no more tool calls), extract final answer
            if response.stop_reason == "end_turn":
                # Extract text from response
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text

                print(f"[claude_agent.py] Agent finished. Parsing response...")

                # Parse JSON from Claude's response
                try:
                    # Find JSON object in response (may have extra text)
                    start = final_text.find("{")
                    end = final_text.rfind("}") + 1
                    if start >= 0 and end > start:
                        json_str = final_text[start:end]
                        parsed = json.loads(json_str)

                        return {
                            "decision": str(parsed.get("decision", "HOLD")).upper(),
                            "confidence": int(parsed.get("confidence", 50)),
                            "reasoning": str(parsed.get("reasoning", "")),
                            "key_factors": list(parsed.get("key_factors", [])),
                            "raw_response": final_text,
                        }
                    else:
                        print("[claude_agent.py] No JSON found in response.")
                        default_result["raw_response"] = final_text
                        return default_result

                except json.JSONDecodeError as e:
                    print(f"[claude_agent.py] JSON parse error: {e}")
                    default_result["raw_response"] = final_text
                    return default_result

            # Handle tool use calls
            elif response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        print(f"[claude_agent.py] Calling tool: {tool_name} "
                              f"with input: {tool_input}")

                        result = _execute_tool(tool_name, tool_input)
                        print(f"[claude_agent.py] Tool result: {result[:200]}...")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result,
                        })

                # Feed tool results back to the conversation
                messages.append({"role": "user", "content": tool_results})

            else:
                # Unexpected stop reason
                print(f"[claude_agent.py] Unexpected stop_reason: {response.stop_reason}")
                break

        print("[claude_agent.py] Max iterations reached without final answer.")
        return default_result

    except anthropic.AuthenticationError:
        print("[claude_agent.py] Invalid ANTHROPIC_API_KEY.")
        default_result["reasoning"] = "Invalid API key — check your ANTHROPIC_API_KEY."
        return default_result

    except anthropic.RateLimitError:
        print("[claude_agent.py] Rate limit exceeded.")
        default_result["reasoning"] = "API rate limit exceeded — please wait and retry."
        return default_result

    except Exception as e:
        print(f"[claude_agent.py] Unexpected error: {e}")
        default_result["reasoning"] = f"Agent error: {str(e)}"
        return default_result


# Allow standalone testing
if __name__ == "__main__":
    result = run_agent()
    print("\n--- Agent Result ---")
    print(f"Decision   : {result['decision']}")
    print(f"Confidence : {result['confidence']}%")
    print(f"Reasoning  : {result['reasoning']}")
    print(f"Key Factors: {result['key_factors']}")
