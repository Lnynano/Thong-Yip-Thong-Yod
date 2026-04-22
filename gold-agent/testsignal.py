"""
testsignal.py
─────────────────────────────────────────────────────────────────────────────
Manual signal tester for the Gold Trading Agent.

HOW TO USE:
  1. Edit the CONFIG section below to match the scenario you want to test
  2. Run:  python testsignal.py
  3. Check Discord for the notification

SCENARIOS:
  - SCENARIO = "live"      → Run real AI analysis (no override)
  - SCENARIO = "buy"       → Force buy_score=5, sell_score=0 → AI should BUY
  - SCENARIO = "sell"      → Force buy_score=0, sell_score=5 → AI should SELL
  - SCENARIO = "failsafe"  → Same as live but with failsafe_pressure=True
  - SCENARIO = "quota"     → Same as live but with quota_pressure=True
  - SCENARIO = "manual"    → Completely bypass AI, send custom Discord message
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ═══════════════════════════════════════════════════════════════════════════
#  ⚙️  CONFIG — Edit this section before running!
# ═══════════════════════════════════════════════════════════════════════════

SCENARIO = "manual"      # "live" | "buy" | "sell" | "sell_force" | "failsafe" | "quota" | "manual"

# ── Manual mode: used only when SCENARIO = "manual" ──────────────────────
MANUAL_DECISION   = "SELL"           # "BUY" | "SELL" | "HOLD"
MANUAL_CONFIDENCE = 80               # 0-100
MANUAL_PRICE_THB  = 72910.0          # Current gold price in THB
MANUAL_REASONING  = "Test signal: Manually triggered SELL for system validation."
MANUAL_WILL_TRADE = True             # True = will send @everyone + "PLACE ORDER NOW"

# ── Force score overrides: used for "buy" / "sell" scenarios ─────────────
FORCE_BUY_SCORE  = 0                 # 0-5
FORCE_SELL_SCORE = 5                # 0-5

# ── Agent options (used in all non-manual scenarios) ─────────────────────
SEND_DISCORD = True                  # Send notification to Discord?
SHOW_FULL_TRACE = False              # Print full ReAct trajectory?

# ═══════════════════════════════════════════════════════════════════════════


def _patch_scores(buy: int, sell: int):
    """Monkey-patch the trading_agent to force specific scores."""
    import agent.trading_agent as ta
    _orig_execute = ta._execute_tool

    def _patched_execute(tool_name, tool_input, _tool_config=None):
        result_str = _orig_execute(tool_name, tool_input, _tool_config)
        if tool_name == "get_indicators":
            try:
                result = json.loads(result_str)
                result["pre_scored_signals"]["buy_score"]  = f"{buy} / 5"
                result["pre_scored_signals"]["sell_score"] = f"{sell} / 5"
                bias = "BUY" if buy > sell else "SELL" if sell > buy else "NEUTRAL"
                result["pre_scored_signals"]["bias"] = bias
                return json.dumps(result)
            except Exception:
                pass
        return result_str

    ta._execute_tool = _patched_execute
    print(f"[testsignal] Score override applied: buy={buy}/5  sell={sell}/5")


def run_live(quota_pressure=False, failsafe_pressure=False):
    from agent.trading_agent import run_agent
    print(f"[testsignal] Running LIVE analysis (quota={quota_pressure}, failsafe={failsafe_pressure})...")
    return run_agent(quota_pressure=quota_pressure, failsafe_pressure=failsafe_pressure)


def run_forced(buy_score: int, sell_score: int, failsafe: bool = False):
    _patch_scores(buy_score, sell_score)
    from agent.trading_agent import run_agent
    print(f"[testsignal] Running FORCED scenario: buy={buy_score}/5  sell={sell_score}/5  failsafe={failsafe}...")
    return run_agent(failsafe_pressure=failsafe)


def get_current_price() -> float:
    """Fetch live HSH gold price for Discord notification."""
    try:
        from data.fetch import get_hsh_price
        hsh = get_hsh_price()
        return hsh.get("sell", 0.0) if hsh else 0.0
    except Exception:
        return 0.0


def send_discord(result: dict, will_trade: bool = False):
    from notifier.discord_notify import send_signal
    price = get_current_price() or MANUAL_PRICE_THB
    ok = send_signal(
        decision   = result["decision"],
        confidence = result["confidence"],
        price_thb  = price,
        reasoning  = result.get("reasoning", ""),
        will_trade = will_trade,
    )
    return ok


def print_result(result: dict):
    print("\n" + "=" * 60)
    print("  TEST SIGNAL RESULT")
    print("=" * 60)
    print(f"  Decision   : {result['decision']}")
    print(f"  Confidence : {result['confidence']}%")
    print(f"  Reasoning  : {result.get('reasoning', '')[:300]}")
    print(f"  Risk Note  : {result.get('risk_note', '')}")
    if SHOW_FULL_TRACE and result.get("agent_trace"):
        print("\n  REACT TRACE:")
        for step in result["agent_trace"]:
            print(f"    {step}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"  GOLD AGENT — SIGNAL TESTER")
    print(f"  Scenario : {SCENARIO.upper()}")
    print("=" * 60 + "\n")

    result = None

    if SCENARIO == "manual":
        # Completely bypass AI — build result manually
        result = {
            "decision"   : MANUAL_DECISION,
            "confidence" : MANUAL_CONFIDENCE,
            "reasoning"  : MANUAL_REASONING,
            "risk_note"  : "Manual test — not based on live data.",
            "agent_trace": [],
        }
        print(f"[testsignal] Manual signal: {MANUAL_DECISION} @ {MANUAL_CONFIDENCE}%")

    elif SCENARIO == "buy":
        result = run_forced(FORCE_BUY_SCORE, 0)

    elif SCENARIO == "sell":
        result = run_forced(0, FORCE_SELL_SCORE)

    elif SCENARIO == "sell_force":
        # Most reliable way to get SELL: force scores + failsafe pressure
        result = run_forced(0, FORCE_SELL_SCORE, failsafe=True)

    elif SCENARIO == "failsafe":
        result = run_live(failsafe_pressure=True)

    elif SCENARIO == "quota":
        result = run_live(quota_pressure=True)

    else:  # "live"
        result = run_live()

    print_result(result)

    # ── Discord notification ───────────────────────────────────────────────
    if SEND_DISCORD:
        print("\n[testsignal] Sending Discord notification...")
        will_trade = MANUAL_WILL_TRADE if SCENARIO == "manual" else (result["decision"] in ("BUY", "SELL") and result["confidence"] >= 65)
        ok = send_discord(result, will_trade=will_trade)
        if ok:
            print("[testsignal] OK - Discord sent successfully!")
        else:
            print("[testsignal] FAILED - Discord failed (check DISCORD_WEBHOOK_URL in .env)")
    else:
        print("\n[testsignal] SEND_DISCORD=False — skipping notification.")


if __name__ == "__main__":
    main()
